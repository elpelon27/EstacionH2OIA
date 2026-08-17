"""Tests unitarios de las funciones ASYNC DE RED de api/bridge.py.

Cubre las funciones del bridge que llaman a servicios externos (Meta Graph API,
Dify, Telegram) y las que persisten en SQLite — MOCKEANDO TODO.

Funciones cubiertas:
- _send_whatsapp_message       (Meta Graph API — texto)
- _send_whatsapp_interactive   (Meta Graph API — list / button)
- _call_dify                   (Dify Chatflow)
- _send_telegram               (Telegram bot)
- _alert_critical              (Telegram + log de error)
- _send_to_dispatch_queue      (INSERT en SQLite dispatch_queue)

Nota: `_convert_eur_to_bs` YA está cubierta en tests/unit/test_bridge_coverage.py
(tasa EUR/VES desde SQLite), así que NO se duplica aquí.

Ningún test realiza llamadas de red reales: _http_client y _telegram_bot se
sustituyen por AsyncMock, y la persistencia SQLite se aísla con una base temporal.

Metodo de import (idéntico a test_bridge.py / test_bridge_coverage.py):
- INSERTA "api" en sys.path
- By-pass de LOG_SALT via BRIDGE_ALLOW_INSECURE_SALT=1
- Define valores de entorno de TEST (sin secretos reales) antes de importar.
"""

import os
import sqlite3
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "api"))

# Bypass LOG_SALT para tests (mismo patron que test_bridge.py)
os.environ["BRIDGE_ALLOW_INSECURE_SALT"] = "1"

# Valores de entorno de test (sin secretos reales) ANTES de importar el modulo.
os.environ.setdefault("META_APP_SECRET", "test")
os.environ.setdefault("META_ACCESS_TOKEN", "")
os.environ.setdefault("META_PHONE_NUMBER_ID", "")
os.environ.setdefault("DIFY_API_KEY", "")
os.environ.setdefault("SQLITE_PATH", "/tmp/bridge_network_test_default.db")
os.environ.setdefault("DISPATCH_DB_PATH", "/tmp/bridge_network_test_dispatch.db")

import bridge  # noqa: E402


# ============================================================================
# Fixtures de aislamiento
# ============================================================================

def _init_schema(path: str) -> None:
    """Crea el esquema minimo (dispatch_queue + fs_tasas_cambio)."""
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dispatch_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_nombre TEXT,
            cliente_telefono TEXT,
            producto_desc TEXT,
            total_eur REAL,
            total_bs REAL,
            metodo_pago TEXT,
            gps_lat REAL,
            gps_lng REAL,
            gps_url TEXT,
            direccion TEXT,
            estado TEXT,
            creado_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fs_tasas_cambio (
            par TEXT PRIMARY KEY,
            tasa REAL,
            registrado_at TEXT,
            fuente TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def _fake_http_client(status_code: int = 200, json_body: dict | None = None):
    """Devuelve un AsyncMock .post con una respuesta fake (sin red real)."""
    client = AsyncMock()
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = "fake body"
    resp.json.return_value = json_body if json_body is not None else {}
    client.post.return_value = resp
    return client


@pytest.fixture(autouse=True)
def _module_isolation(tmp_path, monkeypatch):
    """Aisla el estado global del módulo y la DB por cada test."""
    # Reset de dicts globales
    bridge._seen_messages.clear()
    bridge._conversation_state.clear()
    if hasattr(bridge, "_last_order_totals"):
        bridge._last_order_totals.clear()

    # Valores de entorno de test (parcheados a nivel de atributo del módulo)
    monkeypatch.setattr(bridge, "META_ACCESS_TOKEN", "test")
    monkeypatch.setattr(bridge, "META_PHONE_NUMBER_ID", "12345")
    monkeypatch.setattr(bridge, "META_API_VERSION", "v25.0")
    monkeypatch.setattr(bridge, "DIFY_API_KEY", "test")
    monkeypatch.setattr(bridge, "DIFY_API_URL", "http://localhost:9999/dify")
    monkeypatch.setattr(bridge, "TELEGRAM_ENABLED", True)

    # Base SQLite temporal aislada
    db = tmp_path / "bridge_network.db"
    _init_schema(str(db))
    monkeypatch.setattr(bridge, "SQLITE_PATH", str(db))

    # Clientes externos mockeados (sin red real)
    bridge._http_client = _fake_http_client()
    bridge._telegram_bot = AsyncMock()

    yield

    bridge._http_client = None
    bridge._telegram_bot = None
    bridge._seen_messages.clear()
    bridge._conversation_state.clear()


# ============================================================================
# _send_whatsapp_message — Meta Graph API (texto)
# ============================================================================

class TestSendWhatsappMessage:
    async def test_envia_mensaje_con_exito(self):
        assert await bridge._send_whatsapp_message("+584120000000", "hola") is True
        bridge._http_client.post.assert_awaited_once()

    async def test_http_client_llamado_con_payload_correcto(self):
        await bridge._send_whatsapp_message("+584120000000", "hola")
        url = bridge._http_client.post.call_args.args[0]
        assert "graph.facebook.com" in url
        assert "/v25.0/" in url
        kwargs = bridge._http_client.post.call_args.kwargs
        assert kwargs["json"]["to"] == "+584120000000"
        assert kwargs["json"]["type"] == "text"
        assert kwargs["json"]["text"]["body"] == "hola"

    async def test_error_si_falta_token(self, monkeypatch):
        monkeypatch.setattr(bridge, "META_ACCESS_TOKEN", "")
        assert await bridge._send_whatsapp_message("+584120000000", "hola") is False
        bridge._http_client.post.assert_not_awaited()

    async def test_error_si_falta_phone_number_id(self, monkeypatch):
        monkeypatch.setattr(bridge, "META_PHONE_NUMBER_ID", "")
        assert await bridge._send_whatsapp_message("+584120000000", "hola") is False
        bridge._http_client.post.assert_not_awaited()

    async def test_error_status_no_200(self):
        bridge._http_client = _fake_http_client(status_code=400)
        assert await bridge._send_whatsapp_message("+584120000000", "hola") is False

    async def test_error_httpx_http_error(self):
        bridge._http_client.post.side_effect = bridge.httpx.HTTPError("boom")
        assert await bridge._send_whatsapp_message("+584120000000", "hola") is False


# ============================================================================
# _send_whatsapp_interactive — Meta Graph API (list / button)
# ============================================================================

class TestSendWhatsappInteractive:
    async def test_envia_button_con_exito(self):
        ok = await bridge._send_whatsapp_interactive(
            "+584120000000", "Elija", "button",
            buttons=[{"id": "1", "title": "Opcion A"}, {"id": "2", "title": "Opcion B"}],
            header_text="Titulo largo que excede el limite de sesenta caracteres",
            footer_text="Pie",
        )
        assert ok is True
        payload = bridge._http_client.post.call_args.kwargs["json"]
        assert payload["type"] == "interactive"
        assert payload["interactive"]["type"] == "button"
        assert len(payload["interactive"]["action"]["buttons"]) == 2
        assert len(payload["interactive"]["header"]["text"]) <= 60
        assert payload["interactive"]["footer"]["text"] == "Pie"

    async def test_envia_list_con_exito(self):
        ok = await bridge._send_whatsapp_interactive(
            "+584120000000", "Menú", "list",
            list_sections=[{"title": "S", "rows": [{"id": "1", "title": "A"}]}],
        )
        assert ok is True
        payload = bridge._http_client.post.call_args.kwargs["json"]
        assert payload["interactive"]["type"] == "list"
        assert payload["interactive"]["action"]["button"] == "Ver opciones"

    async def test_tipo_no_soportado_retorna_false_sin_post(self):
        assert await bridge._send_whatsapp_interactive(
            "+584120000000", "x", "desconocido"
        ) is False
        bridge._http_client.post.assert_not_awaited()

    async def test_error_si_falta_token(self, monkeypatch):
        monkeypatch.setattr(bridge, "META_ACCESS_TOKEN", "")
        assert await bridge._send_whatsapp_interactive(
            "+584120000000", "x", "button"
        ) is False
        bridge._http_client.post.assert_not_awaited()

    async def test_error_status_no_200(self):
        bridge._http_client = _fake_http_client(status_code=500)
        assert await bridge._send_whatsapp_interactive(
            "+584120000000", "x", "button"
        ) is False

    async def test_error_httpx_http_error(self):
        bridge._http_client.post.side_effect = bridge.httpx.HTTPError("boom")
        assert await bridge._send_whatsapp_interactive(
            "+584120000000", "x", "button"
        ) is False


# ============================================================================
# _call_dify — Dify Chatflow
# ============================================================================

class TestCallDify:
    async def test_llamada_con_exito(self):
        bridge._http_client = _fake_http_client(
            status_code=200,
            json_body={"answer": "hola", "conversation_id": "c-1"},
        )
        result = await bridge._call_dify("hola", "+584120000000", "conv-abc")
        assert result == {"answer": "hola", "conversation_id": "c-1"}

    async def test_payload_incluye_conversation_id(self):
        bridge._http_client = _fake_http_client(
            status_code=200,
            json_body={"answer": "a", "conversation_id": "c-1"},
        )
        await bridge._call_dify("hola", "+584120000000", "conv-abc")
        payload = bridge._http_client.post.call_args.kwargs["json"]
        assert payload["conversation_id"] == "conv-abc"
        assert payload["response_mode"] == "blocking"

    async def test_sin_conversation_id_no_lo_agrega(self):
        bridge._http_client = _fake_http_client(
            status_code=200,
            json_body={"answer": "a", "conversation_id": "c-1"},
        )
        await bridge._call_dify("hola", "+584120000000", None)
        payload = bridge._http_client.post.call_args.kwargs["json"]
        assert "conversation_id" not in payload

    async def test_error_si_falta_api_key(self, monkeypatch):
        monkeypatch.setattr(bridge, "DIFY_API_KEY", "")
        assert await bridge._call_dify("hola", "+584120000000", None) is None
        bridge._http_client.post.assert_not_awaited()

    async def test_error_status_no_200(self):
        bridge._http_client = _fake_http_client(status_code=500)
        assert await bridge._call_dify("hola", "+584120000000", None) is None

    async def test_error_httpx_http_error(self):
        bridge._http_client.post.side_effect = bridge.httpx.HTTPError("boom")
        assert await bridge._call_dify("hola", "+584120000000", None) is None


# ============================================================================
# _send_telegram — Telegram bot
# ============================================================================

class TestSendTelegram:
    async def test_no_envia_si_deshabilitado(self, monkeypatch):
        monkeypatch.setattr(bridge, "TELEGRAM_ENABLED", False)
        await bridge._send_telegram("msg")
        bridge._telegram_bot.send_message.assert_not_awaited()

    async def test_no_envia_si_bot_none(self):
        bridge._telegram_bot = None
        await bridge._send_telegram("msg")  # no debe lanzar

    async def test_envia_mensaje_correcto(self):
        await bridge._send_telegram("alerta", parse_mode="HTML")
        bridge._telegram_bot.send_message.assert_awaited_once_with(
            chat_id=bridge.TELEGRAM_CHAT_ID,
            text="alerta",
            parse_mode="HTML",
        )

    async def test_atrapa_excepcion(self):
        bridge._telegram_bot.send_message.side_effect = RuntimeError("no")
        await bridge._send_telegram("alerta")  # no debe lanzar


# ============================================================================
# _alert_critical — alerta critica -> Telegram + log
# ============================================================================

class TestAlertCritical:
    async def test_loguea_error_y_envia_telegram(self, monkeypatch):
        send = AsyncMock()
        monkeypatch.setattr(bridge, "_send_telegram", send)
        with patch.object(bridge.logger, "error") as log_err:
            await bridge._alert_critical("Fallo", "detalle")
        log_err.assert_called_once()
        send.assert_awaited_once()
        text = send.await_args.args[0]
        assert "Fallo" in text
        assert "detalle" in text


# ============================================================================
# _send_to_dispatch_queue — INSERT en SQLite dispatch_queue
# ============================================================================

class TestSendToDispatchQueue:
    def _state(self, **overrides):
        state = {
            "qty_botellones": 2,
            "qty_hielo": 1,
            "total_eur": 3.2,
            "payment_method": "efectivo",
            "address": "Av 5, Maracaibo",
            "latitude": 10.5,
            "longitude": -71.6,
            "contact_name": "Juan",
        }
        state.update(overrides)
        return state

    def _mock_workload_router(self, monkeypatch):
        """Mockea core.workload_router para evitar red/tareas reales."""
        router = AsyncMock()
        router.execute.return_value = {"success": True, "data": {"sent": True}}
        fake = types.ModuleType("core.workload_router")
        fake.get_router = MagicMock(return_value=router)
        monkeypatch.setitem(sys.modules, "core.workload_router", fake)
        return router

    def test_inserta_registro_en_dispatch_queue(self, monkeypatch):
        self._mock_workload_router(monkeypatch)
        monkeypatch.setattr(bridge, "_convert_eur_to_bs", MagicMock(return_value=200.0))
        monkeypatch.setattr(bridge, "_sync_client_to_dispatch_db", MagicMock())
        monkeypatch.setattr(bridge, "_assign_vehicle_for_order", MagicMock(return_value=1))

        bridge._send_to_dispatch_queue("hash1234", self._state(), "58412000000")

        conn = sqlite3.connect(bridge.SQLITE_PATH)
        row = conn.execute("SELECT * FROM dispatch_queue").fetchone()
        conn.close()
        assert row is not None
        assert row[1] == "Juan"                    # cliente_nombre
        assert row[2] == "58412000000"             # cliente_telefono
        assert "2 botellones de agua + 1 bolsas de hielo" in row[3]  # producto_desc
        assert row[4] == 3.2                       # total_eur
        assert row[5] == 200.0                     # total_bs
        assert row[6] == "efectivo"                # metodo_pago
        assert row[11] == "pending"                # estado

    def test_sin_gps_no_genera_url(self, monkeypatch):
        self._mock_workload_router(monkeypatch)
        monkeypatch.setattr(bridge, "_convert_eur_to_bs", MagicMock(return_value=0.0))
        monkeypatch.setattr(bridge, "_sync_client_to_dispatch_db", MagicMock())
        monkeypatch.setattr(bridge, "_assign_vehicle_for_order", MagicMock(return_value=1))

        bridge._send_to_dispatch_queue("hash1234", self._state(latitude=None, longitude=None), "58412000000")

        conn = sqlite3.connect(bridge.SQLITE_PATH)
        row = conn.execute("SELECT * FROM dispatch_queue").fetchone()
        conn.close()
        assert row is not None
        assert row[9] == ""  # gps_url vacio cuando no hay lat/lng

    def test_error_db_no_lanza(self, monkeypatch):
        # Ruta de DB inexistente -> excepcion -> se captura y loguea (fail-soft)
        self._mock_workload_router(monkeypatch)
        monkeypatch.setattr(bridge, "_sync_client_to_dispatch_db", MagicMock())
        monkeypatch.setattr(bridge, "_assign_vehicle_for_order", MagicMock(return_value=1))
        with patch.object(bridge, "SQLITE_PATH", str(bridge.SQLITE_PATH) + "/noexiste/x.db"):
            bridge._send_to_dispatch_queue("hash1234", self._state(), "58412000000")  # no debe lanzar
