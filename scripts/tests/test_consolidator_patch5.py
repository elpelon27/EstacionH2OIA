#!/usr/bin/env python3
"""
test_consolidator_patch5.py — Tests SOUL FASE 3 Parche 5 (Consolidador v2).

Cubre las decisiones del Líder (2026-09-10):
- D-5.1: watermark en consolidation_watermark (no relee lo consolidado)
- D-5.2: lee Session DB de Hermes (sessions + messages), no conversations.db
- D-5.3: consolidation_log preservado (entrada histórica intacta)
- --dry-run no escribe nada; --live escribe log + watermark
- Guardarraíl: max sesiones/mensajes por corrida

Aislamiento: usa copias temporales de las DBs (tmpdir); NO toca producción.
"""

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import consolidator  # noqa: E402

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.abspath(os.path.join(SCRIPTS_DIR, "..", ".."))


class ConsolidatorPatch5Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="consolidator_test_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        # Copia de hermes_memory.db (para no tocar la real)
        self.memory_db = os.path.join(self.tmp, "hermes_memory.db")
        real_memory = os.path.join(BASE_DIR, "data", "hermes_memory.db")
        shutil.copy(real_memory, self.memory_db)
        # Guardamos el watermark real para restaurarlo al final
        real_conn = sqlite3.connect(real_memory)
        self.real_wm = real_conn.execute(
            "SELECT last_consolidated_id FROM consolidation_watermark WHERE id=1"
        ).fetchone()
        real_conn.close()

        # Session DB sintética (mismo schema que /home/skynet/.hermes/state.db)
        self.session_db = os.path.join(self.tmp, "state.db")
        sc = sqlite3.connect(self.session_db)
        sc.executescript(
            """
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY, source TEXT NOT NULL, user_id TEXT,
                session_key TEXT, chat_id TEXT, chat_type TEXT, thread_id TEXT,
                display_name TEXT, origin_json TEXT, expiry_finalized INTEGER DEFAULT 0,
                model TEXT, model_config TEXT, system_prompt TEXT,
                parent_session_id TEXT, started_at REAL NOT NULL, ended_at REAL,
                end_reason TEXT, message_count INTEGER DEFAULT 0,
                tool_call_count INTEGER DEFAULT 0
            );
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
                role TEXT NOT NULL, content TEXT, tool_call_id TEXT,
                tool_calls TEXT, tool_name TEXT, effect_disposition TEXT,
                timestamp REAL NOT NULL, token_count INTEGER, finish_reason TEXT,
                reasoning TEXT, reasoning_content TEXT, reasoning_details TEXT,
                codex_reasoning_items TEXT, codex_message_items TEXT,
                platform_message_id TEXT, observed INTEGER DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1, compacted INTEGER NOT NULL DEFAULT 0,
                api_content TEXT, display_kind TEXT, display_metadata TEXT
            );
            INSERT INTO sessions (id, source, display_name, started_at)
                VALUES ('s_test_1', 'cli', 'Test Session', 1700000000.0);
            INSERT INTO messages (session_id, role, content, timestamp, active, compacted)
                VALUES ('s_test_1', 'user', 'Hola, soy Luis y prefiero respuestas breves', 1700000001.0, 1, 0);
            INSERT INTO messages (session_id, role, content, timestamp, active, compacted)
                VALUES ('s_test_1', 'assistant', 'Entendido, Luis.', 1700000002.0, 1, 0);
            INSERT INTO messages (session_id, role, content, timestamp, active, compacted)
                VALUES ('s_test_1', 'tool', 'resultado tool', 1700000003.0, 1, 0);
            """
        )
        sc.commit()
        sc.close()

        # Parcheamos las rutas del módulo hacia los temporales
        self._patches = []
        for attr, value in (("MEMORY_DB", self.memory_db), ("SESSION_DB", self.session_db)):
            p = mock.patch.object(consolidator, attr, value)
            p.start()
            self._patches.append(p)

        # Aislamos también VAULT_DIR para que dry/live no ensucien el vault real
        self.vault_dir = os.path.join(self.tmp, "vault")
        p = mock.patch.object(consolidator, "VAULT_DIR", self.vault_dir)
        p.start()
        self._patches.append(p)

    def tearDown(self):
        for p in self._patches:
            p.stop()
        # El watermark de la DB real nunca se toca (los tests escriben en la
        # copia), pero verificamos por seguridad que quedó intacto.
        real_conn = sqlite3.connect(os.path.join(BASE_DIR, "data", "hermes_memory.db"))
        current = real_conn.execute(
            "SELECT last_consolidated_id FROM consolidation_watermark WHERE id=1"
        ).fetchone()
        real_conn.close()
        self.assertEqual(current, self.real_wm)

    # --- Helpers -----------------------------------------------------------

    def memory_conn(self):
        return sqlite3.connect(self.memory_db)

    def set_watermark(self, last_id, status="ok"):
        c = self.memory_conn()
        c.execute(
            "UPDATE consolidation_watermark SET last_consolidated_id=?, status=? WHERE id=1",
            (last_id, status),
        )
        c.commit()
        c.close()

    def get_watermark(self):
        c = self.memory_conn()
        row = c.execute(
            "SELECT last_consolidated_id, status FROM consolidation_watermark WHERE id=1"
        ).fetchone()
        c.close()
        return row

    def log_count(self):
        c = self.memory_conn()
        n = c.execute("SELECT COUNT(*) FROM consolidation_log").fetchone()[0]
        c.close()
        return n

    # --- D-5.2: lee la Session DB correcta ---------------------------------

    def test_reads_hermes_session_db(self):
        """Lee sessions+messages de la Session DB y excluye roles no-conversación."""
        sessions, new_max = consolidator.get_unconsolidated_sessions(0, 10, 100)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["session_id"], "s_test_1")
        # solo user/assistant: el mensaje tool debe quedar excluido
        roles = [m["role"] for m in sessions[0]["messages"]]
        self.assertEqual(sorted(roles), ["assistant", "user"])
        self.assertGreater(new_max, 0)

    def test_watermark_filters_already_consolidated(self):
        """D-5.1: watermark > 0 excluye mensajes ya consolidados."""
        c = sqlite3.connect(self.session_db)
        max_id = c.execute("SELECT MAX(id) FROM messages").fetchone()[0]
        c.close()
        self.set_watermark(max_id)  # todo consolidado
        sessions, new_max = consolidator.get_unconsolidated_sessions(max_id, 10, 100)
        self.assertEqual(sessions, [])
        self.assertEqual(new_max, max_id)

    def test_guardrail_session_cap(self):
        """Guardarraíl: max_sessions limita las sesiones leídas."""
        c = sqlite3.connect(self.session_db)
        for i in range(5):
            c.execute(
                "INSERT INTO sessions (id, source, display_name, started_at) "
                "VALUES (?, 'cli', ?, ?)",
                (f"s_{i}", f"S{i}", 1700000100.0 + i),
            )
            c.execute(
                "INSERT INTO messages (session_id, role, content, timestamp) "
                "VALUES (?, 'user', ?, ?)",
                (f"s_{i}", f"contenido {i}" * 5, 1700000100.0 + i),
            )
        c.commit()
        c.close()
        sessions, _ = consolidator.get_unconsolidated_sessions(0, 3, 100)
        self.assertEqual(len(sessions), 3)

    # --- D-5.3: consolidation_log preservado --------------------------------

    def test_consolidation_log_history_preserved(self):
        """La entrada histórica del 2026-08-25 (id=2) debe seguir intacta."""
        c = self.memory_conn()
        hist = c.execute(
            "SELECT * FROM consolidation_log WHERE run_at LIKE '2026-08-25%'"
        ).fetchall()
        c.close()
        self.assertEqual(len(hist), 1, "entrada histórica D-5.3 debe existir")
        self.assertEqual(hist[0][2], 1)  # sessions_processed

    # --- Dry-run no escribe nada --------------------------------------------

    def test_dry_run_writes_nothing(self):
        wm_before = self.get_watermark()
        log_before = self.log_count()
        fake_facts = [{"fact": "Luis prefiere respuestas breves", "confidence": "certain"}]

        with (
            mock.patch.object(consolidator, "extract_facts_with_ollama", return_value=fake_facts),
            mock.patch.object(consolidator, "index_in_qdrant", side_effect=AssertionError("dry-run no debe indexar")),
            mock.patch.object(consolidator, "write_to_obsidian", side_effect=AssertionError("dry-run no debe escribir obsidian")),
        ):
            result = consolidator.run_consolidation(live=False, max_sessions=10, max_messages=100)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["facts"], 1)
        self.assertEqual(self.get_watermark(), wm_before, "dry-run no debe tocar watermark")
        self.assertEqual(self.log_count(), log_before, "dry-run no debe escribir consolidation_log")
        self.assertFalse(os.path.exists(self.vault_dir), "dry-run no debe escribir vault")

    # --- --live escribe log + watermark --------------------------------------

    def test_live_writes_log_and_watermark(self):
        wm_before = self.get_watermark()
        log_before = self.log_count()
        fake_facts = [{"fact": "Luis vende botellones", "confidence": "certain"}]

        with (
            mock.patch.object(consolidator, "extract_facts_with_ollama", return_value=fake_facts),
            mock.patch.object(consolidator, "index_in_qdrant", return_value=1) as m_idx,
            mock.patch.object(consolidator, "write_to_obsidian", return_value=1),
        ):
            result = consolidator.run_consolidation(live=True, max_sessions=10, max_messages=100)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["live"], True)
        m_idx.assert_called()

        # Watermark avanzó al max message.id visto
        c = sqlite3.connect(self.session_db)
        max_id = c.execute("SELECT MAX(id) FROM messages WHERE role IN ('user','assistant')").fetchone()[0]
        c.close()
        wm = self.get_watermark()
        self.assertEqual(wm[0], max_id, "watermark debe apuntar al último message.id consolidado")
        self.assertEqual(wm[1], "ok")
        self.assertNotEqual(wm[0], wm_before[0])

        # consolidation_log tiene una entrada nueva (la histórica sigue)
        self.assertEqual(self.log_count(), log_before + 1)

        # --live no relee lo ya consolidado
        sessions2, new_max2 = consolidator.get_unconsolidated_sessions(wm[0], 10, 100)
        self.assertEqual(sessions2, [])

    def test_live_no_work_when_watermark_current(self):
        """Con watermark al día, --live escribe log de 0 y no avanza watermark."""
        c = sqlite3.connect(self.session_db)
        max_id = c.execute("SELECT MAX(id) FROM messages").fetchone()[0]
        c.close()
        self.set_watermark(max_id)
        wm_before = self.get_watermark()
        log_before = self.log_count()
        result = consolidator.run_consolidation(live=True, max_sessions=10, max_messages=100)
        self.assertEqual(result["status"], "no_work")
        self.assertEqual(self.get_watermark(), wm_before)
        self.assertEqual(self.log_count(), log_before, "no_work no debe loguear corrida vacía")

    # --- Modo por defecto ----------------------------------------------------

    def test_default_mode_is_dry_run(self):
        """Sin flags, el parser debe quedar en dry-run."""
        with mock.patch("sys.argv", ["consolidator.py"]):
            import importlib
            ns = None
            parser_args = None
            # reconstruimos el parseo de main() sin ejecutar run_consolidation
            with mock.patch.object(consolidator, "run_consolidation") as m_run:
                consolidator.main()
                parser_args = m_run.call_args[0]
        self.assertFalse(parser_args[0], "default debe ser dry-run (live=False)")


if __name__ == "__main__":
    unittest.main(verbosity=2)