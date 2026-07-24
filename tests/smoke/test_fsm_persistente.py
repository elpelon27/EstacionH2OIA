#!/usr/bin/env python3
"""Smoke test P0-1: FSM persistente en SQLite.

Valida que los estados FSM (conversation_state) y order_totals
sobreviven un reinicio simulado de uvicorn (cache en memoria vaciada).

Escenarios:
1. _set_state → limpiar cache → _get_state recupera de SQLite
2. _save_order_totals → limpiar cache → _get_order_totals recupera de SQLite
3. _clear_state → _get_state devuelve {"state": None}
4. _clear_order_totals → _get_order_totals devuelve None
5. Estado awaiting_payment persiste y se recupera correctamente
6. Estado awaiting_confirmation persiste y se recupera correctamente
7. _set_state con datos extra (total, qty_bot, qty_hielo) persiste correctamente

Run: python3 tests/smoke/test_fsm_persistente.py
"""

import os
import sys
import json
import time
import shutil
import sqlite3

# Path setup
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "api"))

# Backup de la BD real antes de tocar nada
DB_PATH = os.getenv("SQLITE_PATH", os.path.join(PROJECT_ROOT, "data", "conversations.db"))
BACKUP_PATH = DB_PATH + ".backup_fsm_test"

if os.path.exists(DB_PATH):
    shutil.copy2(DB_PATH, BACKUP_PATH)
    print(f"[setup] Backup de BD real: {BACKUP_PATH}")

# Usar BD de test
TEST_DB = os.path.join(PROJECT_ROOT, "data", "test_fsm.db")
if os.path.exists(TEST_DB):
    os.unlink(TEST_DB)
os.environ["SQLITE_PATH"] = TEST_DB

# Importar despues de setear SQLITE_PATH
import bridge

# Forzar init_db con la BD de test
bridge.SQLITE_PATH = TEST_DB
bridge._init_db()

passed = 0
failed = 0


def test(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        print(f"  FAIL: {name}")


def simular_reinicio():
    """Simula reinicio de uvicorn: vacia caches en memoria."""
    bridge._conversation_state.clear()
    bridge._last_order_totals.clear()


print("\n=== Test P0-1: FSM Persistente en SQLite ===\n")

# Test 1: _set_state → reinicio → _get_state recupera
print("[1] Persistencia basica de _set_state / _get_state")
bridge._set_state("hash_test_1", {"state": "awaiting_payment"})
test("Estado en cache tras _set_state", bridge._get_state("hash_test_1")["state"] == "awaiting_payment")
simular_reinicio()
recuperado = bridge._get_state("hash_test_1")
test("Estado recuperado de SQLite tras reinicio simulado", recuperado["state"] == "awaiting_payment")

# Test 2: _save_order_totals → reinicio → _get_order_totals recupera
print("\n[2] Persistencia de _save_order_totals / _get_order_totals")
bridge._save_order_totals("hash_test_2", total=5.20, qty_bot=4, qty_hielo=1)
test("Totales en cache tras _save_order_totals", bridge._get_order_totals("hash_test_2")["total"] == 5.20)
simular_reinicio()
tot = bridge._get_order_totals("hash_test_2")
test("Totales recuperados de SQLite tras reinicio", tot is not None and tot["total"] == 5.20)
test("qty_bot recuperado", tot is not None and tot["qty_bot"] == 4)
test("qty_hielo recuperado", tot is not None and tot["qty_hielo"] == 1)

# Test 3: _clear_state borra de SQLite + cache
print("\n[3] _clear_state elimina de SQLite y cache")
bridge._set_state("hash_test_3", {"state": "awaiting_confirmation"})
bridge._clear_state("hash_test_3")
test("Cache vacia tras _clear_state", bridge._get_state("hash_test_3")["state"] is None)
simular_reinicio()
test("SQLite vacia tras _clear_state + reinicio", bridge._get_state("hash_test_3")["state"] is None)

# Test 4: _clear_order_totals
print("\n[4] _clear_order_totals elimina de SQLite y cache")
bridge._save_order_totals("hash_test_4", total=3.00, qty_bot=3, qty_hielo=0)
bridge._clear_order_totals("hash_test_4")
test("Cache vacia tras _clear_order_totals", bridge._get_order_totals("hash_test_4") is None)
simular_reinicio()
test("SQLite NULL tras _clear_order_totals + reinicio", bridge._get_order_totals("hash_test_4") is None)

# Test 5: Estado awaiting_payment con datos del pedido
print("\n[5] Estado awaiting_payment con datos completos")
state_data = {
    "state": "awaiting_payment",
    "qty_bot": 2,
    "qty_hielo": 1,
    "address": "Calle 72, Maracaibo",
    "total": 2.20,
}
bridge._set_state("hash_test_5", state_data)
simular_reinicio()
rec = bridge._get_state("hash_test_5")
test("Estado recuperado: awaiting_payment", rec.get("state") == "awaiting_payment")
test("address recuperado", rec.get("address") == "Calle 72, Maracaibo")
test("total recuperado", rec.get("total") == 2.20)

# Test 6: Estado awaiting_confirmation
print("\n[6] Estado awaiting_confirmation")
bridge._set_state("hash_test_6", {"state": "awaiting_confirmation", "payment_method": "Pago Movil"})
simular_reinicio()
rec = bridge._get_state("hash_test_6")
test("Estado recuperado: awaiting_confirmation", rec.get("state") == "awaiting_confirmation")
test("payment_method recuperado: Pago Movil", rec.get("payment_method") == "Pago Movil")

# Test 7: _set_state sobrescribe estado anterior (upsert)
print("\n[7] Upsert: _set_state sobrescribe estado anterior")
bridge._set_state("hash_test_7", {"state": "awaiting_payment"})
bridge._set_state("hash_test_7", {"state": "awaiting_confirmation"})
simular_reinicio()
rec = bridge._get_state("hash_test_7")
test("Estado final es awaiting_confirmation (no awaiting_payment)", rec["state"] == "awaiting_confirmation")

# Test 8: Multiples telefonos con estados diferentes
print("\n[8] Multiples telefonos, estados independientes")
bridge._set_state("hash_A", {"state": "awaiting_payment"})
bridge._set_state("hash_B", {"state": "awaiting_confirmation"})
bridge._set_state("hash_C", {"state": "menu_sent"})
simular_reinicio()
test("A=awaiting_payment", bridge._get_state("hash_A")["state"] == "awaiting_payment")
test("B=awaiting_confirmation", bridge._get_state("hash_B")["state"] == "awaiting_confirmation")
test("C=menu_sent", bridge._get_state("hash_C")["state"] == "menu_sent")

# Test 9: Estado None (telefono nuevo, sin estado previo)
print("\n[9] Telefono nuevo devuelve state=None")
simular_reinicio()
result = bridge._get_state("hash_inexistente")
test("Telefono nuevo: state=None", result == {"state": None})

# Test 10: Verificar que la tabla existe en _init_db
print("\n[10] Tabla conversation_state existe en la BD")
conn = sqlite3.connect(TEST_DB)
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='conversation_state'").fetchall()
conn.close()
test("Tabla conversation_state creada por _init_db", len(tables) == 1)

# --- Resultado final ---
print(f"\n=== RESULTADO: {passed} PASS, {failed} FAIL ===\n")

# Cleanup: borrar BD de test
if os.path.exists(TEST_DB):
    os.unlink(TEST_DB)
    for ext in ["-wal", "-shm"]:
        p = TEST_DB + ext
        if os.path.exists(p):
            os.unlink(p)
    print(f"[cleanup] BD de test eliminada: {TEST_DB}")

# Restaurar BD real
if os.path.exists(BACKUP_PATH):
    shutil.move(BACKUP_PATH, DB_PATH)
    print(f"[cleanup] BD real restaurada: {DB_PATH}")

sys.exit(0 if failed == 0 else 1)
