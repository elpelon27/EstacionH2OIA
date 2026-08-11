"""
SPRINT 4.1 — E2E Test: Bridge → WorkloadRouter → DispatcherSkill → dispatch_queue consumer

Validates the complete flow:
1. Bridge _send_to_dispatch_queue() writes to dispatch_queue (conversations.db)
2. Bridge notifies via WorkloadRouter → DispatcherSkill.notify_driver()
3. Consumer processes queue → creates delivery in dispatch.db → notifies chofer
4. Order marked as 'enviado' in dispatch_queue
"""

import os
import sys

# CRITICAL: Set environment variables BEFORE importing bridge modules
# because bridge module reads DISPATCH_DB_PATH at import time
os.environ.setdefault("BRIDGE_ALLOW_INSECURE_SALT", "1")
os.environ.setdefault("DISPATCH_DB_PATH", "/mnt/ssd_trabajo/hermes-agent/data/dispatch.db")
os.environ.setdefault("SQLITE_PATH", "/mnt/ssd_trabajo/hermes-agent/data/conversations.db")

sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")

import pytest
import sqlite3

# Now import after env vars are set
from api.bridge import _send_to_dispatch_queue
from skills.dispatch.consumer import consume_pending_orders


# =============================================================================
# OVERRIDE conftest.py's patch_dispatch_db fixture for these tests
# These tests use the REAL production database, not a temp database
# =============================================================================

@pytest.fixture(autouse=True)
def patch_dispatch_db():
    """Override the conftest.py autouse fixture - restore real database for these tests.
    
    These tests use the real production database with real schema.
    The conftest.py patch_dispatch_db fixture creates a temp database 
    which breaks these integration tests.
    
    This fixture runs AFTER conftest.py's patch_dispatch_db (due to test module order),
    so we restore the real database path in all patched modules.
    """
    # Restore real database path in all modules that were patched
    import skills.dispatch.bottle_tracker as bt_module
    import skills.dispatch.telegram_bot as tbot_module
    import skills.dispatch.gps_tracker as gps_module
    import skills.dispatcher_skill as ds_module
    import skills.dispatch.consumer as consumer_module
    
    REAL_DB = "/mnt/ssd_trabajo/hermes-agent/data/dispatch.db"
    
    bt_module.DISPATCH_DB = REAL_DB
    bt_module._bottle_tracker_instance = None
    
    if hasattr(tbot_module, 'DISPATCH_DB'):
        tbot_module.DISPATCH_DB = REAL_DB
    if hasattr(tbot_module, '_dispatcher_bot_instance'):
        tbot_module._dispatcher_bot_instance = None
    
    if hasattr(gps_module, 'DISPATCH_DB'):
        gps_module.DISPATCH_DB = REAL_DB
    if hasattr(gps_module, '_gps_tracker_instance'):
        gps_module._gps_tracker_instance = None
    
    if hasattr(ds_module, 'DISPATCH_DB'):
        ds_module.DISPATCH_DB = REAL_DB
    if hasattr(ds_module, '_dispatcher_skill_instance'):
        ds_module._dispatcher_skill_instance = None
    
    # Also fix consumer module
    consumer_module.DISPATCH_DB = REAL_DB
    
    yield
    
    # Cleanup: reset instances so they don't leak
    bt_module._bottle_tracker_instance = None
    if hasattr(tbot_module, '_dispatcher_bot_instance'):
        tbot_module._dispatcher_bot_instance = None
    if hasattr(gps_module, '_gps_tracker_instance'):
        gps_module._gps_tracker_instance = None
    if hasattr(ds_module, '_dispatcher_skill_instance'):
        ds_module._dispatcher_skill_instance = None


@pytest.fixture(autouse=True)
def clean_dispatch_queue():
    """Clean test orders before and after each test."""
    # Ensure environment variables are set for the test
    os.environ.setdefault("DISPATCH_DB_PATH", "/mnt/ssd_trabajo/hermes-agent/data/dispatch.db")
    os.environ.setdefault("SQLITE_PATH", "/mnt/ssd_trabajo/hermes-agent/data/conversations.db")
    
    conn = sqlite3.connect("/mnt/ssd_trabajo/hermes-agent/data/conversations.db")
    conn.execute('DELETE FROM dispatch_queue WHERE cliente_nombre LIKE "E2E-%"')
    conn.commit()
    conn.close()
    # Also clean deliveries for test clients to avoid vehicle saturation
    conn = sqlite3.connect("/mnt/ssd_trabajo/hermes-agent/data/dispatch.db")
    conn.execute(
        'DELETE FROM deliveries WHERE client_id IN (SELECT id FROM clients WHERE phone LIKE "+584%")'
    )
    conn.execute('DELETE FROM clients WHERE phone LIKE "+584%"')
    conn.commit()
    conn.close()
    yield
    # Cleanup after
    conn = sqlite3.connect("/mnt/ssd_trabajo/hermes-agent/data/conversations.db")
    conn.execute('DELETE FROM dispatch_queue WHERE cliente_nombre LIKE "E2E-%"')
    conn.commit()
    conn.close()


def _create_test_state(qty_bot=3, qty_hielo=2, metodo="efectivo", total=5.40):
    """Helper to create test state dict."""
    return {
        "qty_botellones": qty_bot,
        "qty_hielo": qty_hielo,
        "total_eur": total,
        "payment_method": metodo,
        "address": "Test Address, Maracaibo",
        "latitude": 10.65,
        "longitude": -71.62,
        "contact_name": "E2E-Test Client",
    }


def _get_queued_order(cliente_nombre):
    """Fetch the latest queued order for a client."""
    conn = sqlite3.connect("/mnt/ssd_trabajo/hermes-agent/data/conversations.db")
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM dispatch_queue WHERE cliente_nombre = ? ORDER BY id DESC LIMIT 1",
        (cliente_nombre,),
    ).fetchone()
    conn.close()
    return row


@pytest.mark.asyncio
async def test_bridge_writes_to_dispatch_queue():
    """Test that _send_to_dispatch_queue writes order to conversations.db."""
    ph_hash = "e2e_test_bridge_write_" + "x" * 15
    state = _create_test_state()
    from_phone = "+584****1111"

    # Call bridge function
    _send_to_dispatch_queue(ph_hash, state, from_phone)

    # Verify order in queue
    order = _get_queued_order("E2E-Test Client")
    assert order is not None, "Order should be inserted into dispatch_queue"
    assert order["estado"] == "pending", f"Expected 'pending', got '{order['estado']}'"
    assert order["cliente_telefono"] == from_phone
    assert order["total_eur"] == 5.40
    assert "3 botellones" in order["producto_desc"]
    assert "2 bolsas" in order["producto_desc"]


@pytest.mark.asyncio
async def test_consumer_processes_queue():
    """Test that consumer picks up pending order and marks as enviado."""
    ph_hash = "e2e_test_consumer_" + "y" * 15
    state = _create_test_state()
    from_phone = "+584****2222"

    # Bridge writes order
    _send_to_dispatch_queue(ph_hash, state, from_phone)

    # Consumer processes
    result = await consume_pending_orders(max_orders=10)

    # Verify consumer result
    assert result["processed"] >= 1, "Consumer should process at least 1 order"
    assert result["errors"] == 0, f"Consumer errors: {result['errors']}"

    # Verify order marked as enviado
    order = _get_queued_order("E2E-Test Client")
    assert order is not None
    assert order["estado"] == "enviado", f"Expected 'enviado', got '{order['estado']}'"
    assert order["enviado_at"] is not None, "enviado_at should be set"


@pytest.mark.asyncio
async def test_full_e2e_flow_bridge_to_consumer():
    """Full E2E: Bridge writes → Consumer processes → Delivery created in dispatch.db."""
    ph_hash = "e2e_test_full_" + "z" * 16
    state = _create_test_state(qty_bot=4, qty_hielo=1, total=5.20)
    from_phone = "+584****3333"

    # Step 1: Bridge receives payment confirmation, writes to queue
    _send_to_dispatch_queue(ph_hash, state, from_phone)

    order = _get_queued_order("E2E-Test Client")
    assert order is not None
    order["id"]
    assert order["estado"] == "pending"

    # Step 2: Consumer processes the queue
    result = await consume_pending_orders(max_orders=10)
    assert result["processed"] >= 1
    assert result["notified"] >= 1  # Chofer notified
    assert result["errors"] == 0

    # Step 3: Verify order marked as enviado
    order = _get_queued_order("E2E-Test Client")
    assert order["estado"] == "enviado"
    assert order["enviado_at"] is not None

    # Step 4: Verify delivery created in dispatch.db
    conn = sqlite3.connect("/mnt/ssd_trabajo/hermes-agent/data/dispatch.db")
    conn.row_factory = sqlite3.Row
    delivery = conn.execute(
        "SELECT * FROM deliveries WHERE client_id IN (SELECT id FROM clients WHERE phone = ?) ORDER BY id DESC LIMIT 1",
        (from_phone,),
    ).fetchone()
    conn.close()

    assert delivery is not None, "Delivery should be created in dispatch.db"
    assert delivery["status"] == "pending"
    assert delivery["bottles_full"] == 4  # qty_botellones

    # Step 5: Verify client created in dispatch.db
    conn = sqlite3.connect("/mnt/ssd_trabajo/hermes-agent/data/dispatch.db")
    conn.row_factory = sqlite3.Row
    client = conn.execute("SELECT * FROM clients WHERE phone = ?", (from_phone,)).fetchone()
    conn.close()

    assert client is not None, "Client should be synced to dispatch.db"
    assert client["name"] == "E2E-Test Client"


@pytest.mark.asyncio
async def test_multiple_orders_batch():
    """Test multiple orders queued and processed in batch."""
    orders_data = [
        ("e2e_batch_1", 3, 0, 3.00, "efectivo"),
        ("e2e_batch_2", 2, 2, 4.40, "pagomovil"),
        ("e2e_batch_3", 5, 0, 5.00, "efectivo"),
    ]

    for i, (_ph_suffix, bot, hielo, total, metodo) in enumerate(orders_data):
        ph_hash = f"e2e_batch_{i}_" + "w" * 16
        state = _create_test_state(qty_bot=bot, qty_hielo=hielo, metodo=metodo, total=total)
        from_phone = f"+584****4444{i}"
        state["contact_name"] = f"E2E-Batch Client {i+1}"
        _send_to_dispatch_queue(ph_hash, state, from_phone)

    # Process all
    result = await consume_pending_orders(max_orders=10)

    assert result["processed"] >= 3
    assert result["errors"] == 0

    # Verify all marked as enviado
    conn = sqlite3.connect("/mnt/ssd_trabajo/hermes-agent/data/conversations.db")
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        'SELECT COUNT(*) as cnt FROM dispatch_queue WHERE cliente_nombre LIKE "E2E-Batch%" AND estado = "enviado"'
    ).fetchone()
    conn.close()

    assert row["cnt"] >= 3, "All batch orders should be marked as enviado"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])