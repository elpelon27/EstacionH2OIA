#!/usr/bin/env python3
"""Tests Bloque 4 Fase 4.3: resumen semanal de crédito + /resumen."""
import os
import sqlite3
import sys
import uuid
from unittest.mock import MagicMock, patch

sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")
CONV_DB = "/mnt/ssd_trabajo/hermes-agent/data/conversations.db"

from scripts.credit_summary import (  # noqa: E402
    clientes_con_deuda,
    generate_weekly_summary,
    send_summary_via_valentina,
)

TEST_PHONE = f"0414-TESTCS-{uuid.uuid4().hex[:6]}"
created: list[int] = []

conn = sqlite3.connect(CONV_DB)
conn.row_factory = sqlite3.Row

# Ver schema real de fs_tasas_cambio para el test de tasa
schema_tasa = [r[1] for r in conn.execute("PRAGMA table_info(fs_tasas_cambio)")]

try:
    # Fixture: 2 pedidos pendientes (uno con tasa implícita)
    for monto, bots, hielo in ((3.0, 3, 0), (4.2, 3, 1)):
        pid = 95000 + uuid.uuid4().int % 9000
        rowid = conn.execute(
            """INSERT INTO fs_pedidos
               (pedido_id, cliente_telefono, cliente_nombre, monto_total_eur,
                botellones_cantidad, hielo_cantidad, estado_pago, estado_entrega,
                tasa_eur_ves, creado_at, actualizado_at)
               VALUES (?, ?, 'Cliente Test CS', ?, ?, ?, 'pendiente', 'sin_entregar',
                       40.0, datetime('now'), datetime('now'))""",
            (pid, TEST_PHONE, monto, bots, hielo),
        ).lastrowid
        created.append(rowid)
    conn.commit()

    # TEST 1: generate_weekly_summary con datos reales
    s = generate_weekly_summary(TEST_PHONE)
    assert s, "resumen vacío"
    assert "Resumen Semanal" in s and "Cliente Test CS" in s
    assert "Pedidos pendientes: 2" in s
    assert "7.20 EUR" in s  # 3.0 + 4.2
    assert "3 AGUA" in s and "1 HIELO" in s
    assert "Total a pagar: 7.20 EUR" in s
    assert "comprobante de transferencia" in s
    print("TEST1_OK: resumen generado con datos reales")
    print("--- preview ---")
    print(s)
    print("--- fin preview ---")

    # TEST 2: cliente sin deuda → None
    assert generate_weekly_summary("0000-SIN-DEUDA") is None
    print("TEST2_OK: sin deuda → None")

    # TEST 3: send_summary_via_valentina con API Meta mockeada
    with patch("urllib.request.urlopen") as mock_urlopen:
        resp = MagicMock()
        resp.status = 200
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp
        ok = send_summary_via_valentina(TEST_PHONE, s)
    assert ok, "envío mock falló"
    print("TEST3_OK: envío via Meta API (mock) OK")

    # TEST 3b: sin configuración Meta → False (no crash)
    with patch.dict(os.environ, {"META_ACCESS_TOKEN": "", "META_PHONE_NUMBER_ID": ""}):
        ok = send_summary_via_valentina(TEST_PHONE, s)
    assert not ok
    print("TEST3b_OK: sin config Meta → False")

    # TEST 4: clientes_con_deuda incluye al test
    deudores = clientes_con_deuda()
    assert any(p == TEST_PHONE for p, _ in deudores), deudores
    print("TEST4_OK: clientes_con_deuda detecta al cliente")

    # TEST 5: comando /resumen registrado en el bot
    import skills.client_commands as cc

    fake_app = MagicMock()
    n = cc.register_client_handlers(fake_app)
    assert n >= 6, n
    registered = []
    for c in fake_app.add_handler.call_args_list:
        handler = c.args[0]
        cmds_attr = getattr(handler, "commands", None) or frozenset()
        registered.extend(cmds_attr)
    assert "resumen" in registered, registered
    print(f"TEST5_OK: /resumen registrado en @Skynet_27_bot ({n} comandos)")

    # TEST 6: guard — chat no autorizado no responde
    import asyncio

    async def t():
        upd = MagicMock()
        upd.effective_chat.id = 12345  # no es el Líder
        upd.effective_user.id = 12345
        ctx = MagicMock()
        ctx.args = [TEST_PHONE]
        with patch("skills.client_commands._reply") as mock_reply:
            await cc.cmd_resumen(upd, ctx)
            mock_reply.assert_not_called()

    asyncio.run(t())
    print("TEST6_OK: guard chat_id bloquea no-Líder")

    print("ALL_CREDIT_SUMMARY_TESTS_PASSED")
finally:
    for rowid in created:
        conn.execute("DELETE FROM fs_pedidos WHERE id=?", (rowid,))
    conn.commit()
    left = conn.execute(
        "SELECT COUNT(*) c FROM fs_pedidos WHERE cliente_telefono=?", (TEST_PHONE,)
    ).fetchone()["c"]
    conn.close()
    assert left == 0
    print("CLEANUP_OK")
