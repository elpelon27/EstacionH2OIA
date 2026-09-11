#!/usr/bin/env python3
"""
test_warming_patch7.py — Tests SOUL FASE 3 Parche 7 (Warming predictivo v2).

Cubre las decisiones del Líder (2026-09-10):
- D-7.1: warming automático DESACTIVADO hasta 21 días de cron_runs; solo --force
- D-7.2: top-10 memorias se cargan en Redis
- D-7.3: TTL respeta 7200s
- D-7.4: sin eventos de agentes hermanos (nada los consume)

Aislamiento: Redis real (claves hermes:warm:test_* con TTL corto de limpieza);
DB en tmpdir. El test de TTL usa un monkeypatch del TTL para no esperar 2h.
"""

import os
import sys
import tempfile
import time
import unittest
from datetime import UTC, datetime, timedelta
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import warming  # noqa: E402

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.abspath(os.path.join(SCRIPTS_DIR, "..", ".."))


class WarmingPatch7Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="warming_test_")
        self.memory_db = os.path.join(self.tmp, "hermes_memory.db")
        conn = sqlite3_dummy = __import__("sqlite3").connect(self.memory_db)
        conn.executescript(
            """
            CREATE TABLE cron_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cron_name TEXT NOT NULL,
                executed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                success BOOLEAN NOT NULL,
                duration_ms INTEGER,
                output_hash TEXT,
                error TEXT
            );
            CREATE TABLE warming_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT,
                chunks_prefetched INTEGER,
                cache_hits INTEGER,
                cache_misses INTEGER,
                miss_rate REAL,
                run_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.commit()
        conn.close()

        self._patches = []
        p = mock.patch.object(warming, "MEMORY_DB", self.memory_db)
        p.start()
        self._patches.append(p)

        self.fake_chunks = [
            {"id": f"test_{i}", "payload": {"fact": f"hecho {i}"}}
            for i in range(10)
        ]

    def tearDown(self):
        for p in self._patches:
            p.stop()
        # Autolimpieza: los tests escriben claves hermes:warm:test_* en Redis real
        try:
            import redis

            r = redis.Redis(host=warming.REDIS_HOST, port=warming.REDIS_PORT,
                            decode_responses=True)
            for k in r.keys("hermes:warm:test_*"):
                r.delete(k)
        except Exception:
            pass
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- D-7.1: auto desactivado hasta 21 días ------------------------------

    def test_auto_disabled_before_21_days(self):
        """Hoy (2026-09-10, inicio del acumulo) el auto DEBE estar inactivo."""
        ready, reason = warming.auto_activation_ready()
        self.assertFalse(ready)
        self.assertIn("DESACTIVADO", reason)

    def test_auto_ready_after_21_days(self):
        """Tras 21 días desde AUTO_ACTIVATION_START, el auto es activable."""
        future = warming.AUTO_ACTIVATION_START + timedelta(days=22)
        with mock.patch.object(warming, "AUTO_ACTIVATION_START", warming.AUTO_ACTIVATION_START - timedelta(days=22)):
            ready, _ = warming.auto_activation_ready()
        self.assertTrue(ready)
        self.assertIsNotNone(future)

    def test_no_force_skips_warming_now(self):
        """Sin --force y auto desactivado: warming OMITIDO, nada en Redis."""
        with (
            mock.patch.object(warming, "get_top_chunks_from_qdrant",
                              side_effect=AssertionError("no debe leer Qdrant sin --force/auto")),
            mock.patch.object(warming, "prefetch_to_redis",
                              side_effect=AssertionError("no debe cachear sin --force/auto")),
        ):
            result = warming.run_warming(dry_run=False, force=False)
        self.assertEqual(result["status"], "auto_disabled")
        self.assertEqual(result["chunks"], 0)

    # --- D-7.2: top-10 en Redis con --force ----------------------------------

    def test_force_loads_top10_in_redis(self):
        """--force carga exactamente top-10 chunks en Redis."""
        with mock.patch.object(warming, "get_top_chunks_from_qdrant", return_value=self.fake_chunks):
            result = warming.run_warming(dry_run=False, force=True)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["trigger"], "force")
        self.assertEqual(result["chunks"], 10)

        # Verificar en Redis real que las 10 claves existen
        import redis

        r = redis.Redis(host=warming.REDIS_HOST, port=warming.REDIS_PORT, decode_responses=True)
        keys = sorted(k for k in r.keys("hermes:warm:test_*"))
        self.assertEqual(len(keys), 10, "deben haber exactamente 10 claves warm test")
        # limpieza
        for k in keys:
            r.delete(k)

    def test_force_dry_run_touches_nothing(self):
        """--force --dry-run no escribe Redis ni warming_log."""
        import redis

        r = redis.Redis(host=warming.REDIS_HOST, port=warming.REDIS_PORT, decode_responses=True)
        before = len(r.keys("hermes:warm:test_*"))
        with mock.patch.object(warming, "get_top_chunks_from_qdrant", return_value=self.fake_chunks):
            result = warming.run_warming(dry_run=True, force=True)
        after = len(r.keys("hermes:warm:test_*"))
        self.assertEqual(result["chunks"], 10)
        self.assertEqual(before, after, "dry-run no debe escribir en Redis")

    # --- D-7.3: TTL 7200s -----------------------------------------------------

    def test_ttl_is_7200(self):
        """El TTL escrito en Redis debe ser exactamente 7200s (D-7.3)."""
        self.assertEqual(warming.WARMING_TTL, 7200)
        with mock.patch.object(warming, "get_top_chunks_from_qdrant", return_value=self.fake_chunks):
            warming.run_warming(dry_run=False, force=True)
        import redis

        r = redis.Redis(host=warming.REDIS_HOST, port=warming.REDIS_PORT, decode_responses=True)
        keys = sorted(k for k in r.keys("hermes:warm:test_*"))
        self.assertEqual(len(keys), 10)
        for k in keys:
            ttl = r.ttl(k)
            self.assertTrue(7190 <= ttl <= 7200, f"TTL {ttl} debe ser ~7200")
            r.delete(k)

    def test_warming_log_event_type_forced(self):
        """--force registra event_type='forced_manual' en warming_log."""
        with mock.patch.object(warming, "get_top_chunks_from_qdrant", return_value=self.fake_chunks):
            warming.run_warming(dry_run=False, force=True)
        import sqlite3

        c = sqlite3.connect(self.memory_db)
        rows = c.execute(
            "SELECT event_type, chunks_prefetched FROM warming_log"
        ).fetchall()
        c.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "forced_manual")
        self.assertEqual(rows[0][1], 10)

    # --- D-7.4: sin eventos de agentes hermanos -------------------------------

    def test_no_sibling_agent_events_consumed(self):
        """D-7.4: el módulo no consume fuente de eventos de agentes hermanos."""
        import ast

        source = open(warming.__file__).read()
        tree = ast.parse(source)
        # Ningún identificador de código (no docstrings) menciona bus/hermanos
        code_names = [
            node.id for node in ast.walk(tree)
            if isinstance(node, ast.Name)
        ] + [
            node.attr for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
        ] + [
            node.name for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        for bad in ("sibling", "event_bus", "hermano", "agent_event"):
            self.assertNotIn(
                bad,
                " ".join(code_names).lower(),
                f"el código no debe consumir '{bad}' (D-7.4: FASE 4+)",
            )
        # Y warming_log solo recibe triggers propios: force/pattern
        self.assertIn("forced_manual", source)
        self.assertIn("pattern_detected", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)