"""Tests unitarios de cobertura para helpers puros de api/bridge.py (sin red).

Cubre funciones determinísticas y de persistencia local que los archivos
test_bridge.py / test_bridge_helpers.py existentes NO cubren todavía:

- _convert_eur_to_bs        (tasa EUR/VES desde SQLite local)
- _is_within_business_hours / _get_out_of_hours_message  (horario laboral)
- _validate_meta_payload     (validación de estructura del webhook de Meta)
- _is_duplicate              (deduplicación in-memory)
- _check_tcp_up              (health TCP local)
- _is_kill_switch_active     (archivo centinela)
- _nearest_zone_id           (Haversine contra tabla zones)
- _get_state/_set_state/_clear_state + _get/_save/_clear_order_totals
                              (persistencia SQLite local)

Ningún test ejecuta llamadas HTTP a Meta/Dify/Telegram ni a servicios externos.
La persistencia SQLite se aísla con bases temporales (tmp_path) y se parchean
las rutas SQLITE_PATH / DISPATCH_DB_PATH / KILL_SWITCH_FILE del módulo.
"""

import os
import sqlite3
import sys
import time
from datetime import datetime as _real_datetime
from unittest.mock import MagicMock, patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "api"))

# Bypass LOG_SALT para tests (mismo patrón que test_bridge.py)
os.environ["BRIDGE_ALLOW_INSECURE_SALT"] = "1"

# Valores de entorno de test (sin secretos reales) ANTES de importar el módulo.
os.environ.setdefault("META_APP_SECRET", "test")
os.environ.setdefault("META_ACCESS_TOKEN", "")
os.environ.setdefault("META_PHONE_NUMBER_ID", "")
os.environ.setdefault("DIFY_API_KEY", "")
os.environ.setdefault("SQLITE_PATH", "/tmp/bridge_test_default.db")
os.environ.setdefault("DISPATCH_DB_PATH", "/tmp/bridge_test_dispatch.db")

import bridge  # noqa: E402

# ============================================================================
# Fixtures de aislamiento SQLite
# ============================================================================

def _create_conversation_db(path: str) -> None:
    """Crea el esquema mínimo (conversation_state + fs_tasas_cambio)."""
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_state (
            phone_hash TEXT PRIMARY KEY,
            state_json TEXT NOT NULL,
            total REAL,
            qty_bot INTEGER,
            qty_hielo INTEGER,
            updated_at REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fs_tasas_cambio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            par TEXT,
            tasa REAL,
            registrado_at REAL
        )
        """
    )
    conn.commit()
    conn.close()


def _create_dispatch_db(path: str) -> None:
    """Crea el esquema mínimo de dispatch.db (tabla zones)."""
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS zones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            center_lat REAL,
            center_lng REAL,
            radius_km REAL,
            color TEXT DEFAULT '#3B82F6',
            created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
        )
        """
    )
    conn.commit()
    conn.close()



# ============================================================================
# _is_duplicate — deduplicación in-memory
# ============================================================================

class TestIsDuplicate:
    def test_primera_vez_false(self):
        bridge._seen_messages.clear()
        assert bridge._is_duplicate("msg-1") is False
        assert "msg-1" in bridge._seen_messages

    def test_segunda_vez_true(self):
        bridge._seen_messages.clear()
        bridge._is_duplicate("msg-2")
        assert bridge._is_duplicate("msg-2") is True

    def test_con_una_entrada_no_es_duplicado(self):
        bridge._seen_messages.clear()
        bridge._seen_messages["otra"] = time.time()
        assert bridge._is_duplicate("msg-fresh") is False

    def test_entrada_expirada_se_limpia(self):
        # Una entrada vieja debe expirarse (limpieza perezosa) y no contar como dup.
        bridge._seen_messages.clear()
        bridge._seen_messages["viejo"] = time.time() - (bridge.DEDUP_TTL_SECONDS + 10)
        assert bridge._is_duplicate("viejo") is False  # se purga y se re-registra
        assert bridge._is_duplicate("viejo") is True   # ahora sí cuenta


# ============================================================================
# _is_kill_switch_active — archivo centinela
# ============================================================================

class TestIsKillSwitchActive:
    def test_sin_archivo_false(self, tmp_path):
        ks = tmp_path / "kill"
        with patch.object(bridge, "KILL_SWITCH_FILE", str(ks)):
            assert bridge._is_kill_switch_active() is False

    def test_con_archivo_true(self, tmp_path):
        ks = tmp_path / "kill"
        ks.write_text("")
        with patch.object(bridge, "KILL_SWITCH_FILE", str(ks)):
            assert bridge._is_kill_switch_active() is True


# ============================================================================
# _convert_eur_to_bs — tasa EUR/VES desde SQLite local (parchea SQLITE_PATH)
# ============================================================================

class TestConvertEurToBs:
    def test_conversion_con_tasa(self, tmp_path):
        db = tmp_path / "conv.db"
        _create_conversation_db(str(db))
        conn = sqlite3.connect(str(db))
        conn.execute(
            "INSERT INTO fs_tasas_cambio (par, tasa, registrado_at) VALUES (?, ?, ?)",
            ("EUR/VES", 40.0, time.time()),
        )
        conn.commit()
        conn.close()
        with patch.object(bridge, "SQLITE_PATH", str(db)):
            assert bridge._convert_eur_to_bs(2.0) == 80.00

    def test_conversion_redondea_dos_decimales(self, tmp_path):
        db = tmp_path / "conv.db"
        _create_conversation_db(str(db))
        conn = sqlite3.connect(str(db))
        conn.execute(
            "INSERT INTO fs_tasas_cambio (par, tasa, registrado_at) VALUES (?, ?, ?)",
            ("EUR/VES", 3.33, time.time()),
        )
        conn.commit()
        conn.close()
        with patch.object(bridge, "SQLITE_PATH", str(db)):
            assert bridge._convert_eur_to_bs(1.0) == 3.33

    def test_tasa_cero_devuelve_none(self, tmp_path):
        db = tmp_path / "conv.db"
        _create_conversation_db(str(db))
        conn = sqlite3.connect(str(db))
        conn.execute(
            "INSERT INTO fs_tasas_cambio (par, tasa, registrado_at) VALUES (?, ?, ?)",
            ("EUR/VES", 0.0, time.time()),
        )
        conn.commit()
        conn.close()
        with patch.object(bridge, "SQLITE_PATH", str(db)):
            assert bridge._convert_eur_to_bs(2.0) is None

    def test_sin_tasas_devuelve_none(self, tmp_path):
        db = tmp_path / "conv.db"
        _create_conversation_db(str(db))
        with patch.object(bridge, "SQLITE_PATH", str(db)):
            assert bridge._convert_eur_to_bs(2.0) is None

    def test_error_db_devuelve_none(self, tmp_path):
        # Ruta inexistente → excepción → None (fail-soft)
        bad_db = tmp_path / "noexiste" / "x.db"
        with patch.object(bridge, "SQLITE_PATH", str(bad_db)):
            assert bridge._convert_eur_to_bs(2.0) is None


# ============================================================================
# _is_within_business_hours / _get_out_of_hours_message — horario laboral
# ============================================================================

class _FakeDatetime:
    """Reemplaza bridge.datetime; now() devuelve un datetime fijo con tz."""
    _current = None

    @classmethod
    def now(cls, tz=None):
        return cls._current

    @classmethod
    def set(cls, dt):
        cls._current = dt


def _now_at(year=2026, month=8, day=17, hour=10, minute=0):
    """Devuelve un datetime con tzinfo de Caracas (UTC-4)."""
    return _real_datetime(year, month, day, hour, minute, tzinfo=bridge.CARACAS_TZ)


class TestIsWithinBusinessHours:
    def test_dia_laboral_en_horario(self):
        # Lun 17-ago-2026 10:00 → dentro
        _FakeDatetime.set(_now_at(hour=10))
        with patch.object(bridge, "datetime", _FakeDatetime):
            assert bridge._is_within_business_hours() is True

    def test_dia_laboral_apertura_exacta(self):
        _FakeDatetime.set(_now_at(hour=8, minute=0))
        with patch.object(bridge, "datetime", _FakeDatetime):
            assert bridge._is_within_business_hours() is True

    def test_dia_laboral_antes_de_apertura(self):
        _FakeDatetime.set(_now_at(hour=7, minute=0))
        with patch.object(bridge, "datetime", _FakeDatetime):
            assert bridge._is_within_business_hours() is False

    def test_dia_laboral_despues_de_cierre(self):
        _FakeDatetime.set(_now_at(hour=19, minute=0))
        with patch.object(bridge, "datetime", _FakeDatetime):
            assert bridge._is_within_business_hours() is False

    def test_domingo_siempre_false(self):
        # Dom 16-ago-2026 10:00 → weekday=6 → mapeado a 0 → no laboral
        _FakeDatetime.set(_now_at(month=8, day=16, hour=10))
        with patch.object(bridge, "datetime", _FakeDatetime):
            assert bridge._is_within_business_hours() is False

    def test_dia_excluido_por_config(self):
        # Config solo Lun a Vie (sin Sáb). Sáb 22-ago-2026 12:00 → False
        _FakeDatetime.set(_now_at(month=8, day=22, hour=12))
        with patch.object(bridge, "datetime", _FakeDatetime), \
             patch.object(bridge, "BUSINESS_HOURS_DAYS", "1,2,3,4,5"):
            assert bridge._is_within_business_hours() is False


class TestGetOutOfHoursMessage:
    def test_apertura_en_menos_de_30min(self):
        # Lun 07:50 → faltan 10 min
        _FakeDatetime.set(_now_at(hour=7, minute=50))
        with patch.object(bridge, "datetime", _FakeDatetime):
            msg = bridge._get_out_of_hours_message()
            assert "10 minutos" in msg

    def test_apertura_en_mas_de_30min(self):
        # Lun 06:00 → faltan 120 min
        _FakeDatetime.set(_now_at(hour=6, minute=0))
        with patch.object(bridge, "datetime", _FakeDatetime):
            msg = bridge._get_out_of_hours_message()
            assert "estamos cerrados" in msg
            assert "8:00am" in msg

    def test_fuera_dia_no_laboral(self):
        # Dom 16-ago-2026 10:00
        _FakeDatetime.set(_now_at(month=8, day=16, hour=10))
        with patch.object(bridge, "datetime", _FakeDatetime):
            msg = bridge._get_out_of_hours_message()
            assert "cerrados" in msg


# ============================================================================
# _validate_meta_payload — validación de estructura de Meta
# ============================================================================

def _valid_payload():
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [{"wa_id": "584120000000"}],
                            "messages": [
                                {"id": "wamid.XYZ", "type": "text", "text": {"body": "hola"}}
                            ],
                        }
                    }
                ]
            }
        ]
    }


class TestValidateMetaPayload:
    def test_payload_valido(self):
        assert bridge._validate_meta_payload(_valid_payload()) is True

    def test_sin_entry(self):
        assert bridge._validate_meta_payload({}) is False

    def test_entry_no_lista(self):
        p = _valid_payload()
        p["entry"] = "no-lista"
        assert bridge._validate_meta_payload(p) is False

    def test_sin_changes(self):
        p = _valid_payload()
        p["entry"][0].pop("changes", None)
        assert bridge._validate_meta_payload(p) is False

    def test_sin_value(self):
        p = _valid_payload()
        p["entry"][0]["changes"] = [{}]
        assert bridge._validate_meta_payload(p) is False

    def test_sin_contacts(self):
        p = _valid_payload()
        del p["entry"][0]["changes"][0]["value"]["contacts"]
        assert bridge._validate_meta_payload(p) is False

    def test_sin_wa_id(self):
        p = _valid_payload()
        p["entry"][0]["changes"][0]["value"]["contacts"][0] = {"name": "x"}
        assert bridge._validate_meta_payload(p) is False

    def test_wa_id_no_digitos(self):
        p = _valid_payload()
        p["entry"][0]["changes"][0]["value"]["contacts"][0]["wa_id"] = "abc12345678"
        assert bridge._validate_meta_payload(p) is False

    def test_wa_id_demasiado_corto(self):
        p = _valid_payload()
        p["entry"][0]["changes"][0]["value"]["contacts"][0]["wa_id"] = "123"
        assert bridge._validate_meta_payload(p) is False

    def test_messages_sin_id(self):
        p = _valid_payload()
        del p["entry"][0]["changes"][0]["value"]["messages"][0]["id"]
        assert bridge._validate_meta_payload(p) is False

    def test_messages_sin_type(self):
        p = _valid_payload()
        del p["entry"][0]["changes"][0]["value"]["messages"][0]["type"]
        assert bridge._validate_meta_payload(p) is False

    def test_payload_sin_messages_valido(self):
        # Sin mensajes (p.ej. webhook de estado) pero con contacts válidos
        p = _valid_payload()
        p["entry"][0]["changes"][0]["value"].pop("messages", None)
        assert bridge._validate_meta_payload(p) is True

    def test_entrada_no_dict(self):
        p = _valid_payload()
        p["entry"] = [None]
        assert bridge._validate_meta_payload(p) is False


# ============================================================================
# _check_tcp_up — health TCP local (sin red externa)
# ============================================================================

class TestCheckTcpUp:
    def test_puerto_cerrado_false(self):
        # 127.0.0.1 con un puerto alto que casi seguro no escucha → conexión
        # rechazada → OSError → False. Sin red externa.
        assert bridge._check_tcp_up("127.0.0.1", 1, timeout=0.3) is False

    def test_conexion_aceptada_true(self):
        # Mock del socket: create_connection devuelve un context manager exitoso.
        fake_sock = MagicMock()
        fake_sock.__enter__.return_value = fake_sock
        with patch.object(bridge.socket, "create_connection", return_value=fake_sock):
            assert bridge._check_tcp_up("127.0.0.1", 8069, timeout=0.3) is True


# ============================================================================
# _nearest_zone_id — Haversine contra dispatch.db (parchea DISPATCH_DB_PATH)
# ============================================================================

class TestNearestZoneId:
    def test_sin_gps_none(self):
        assert bridge._nearest_zone_id(None, None) is None
        assert bridge._nearest_zone_id(10.6, None) is None
        assert bridge._nearest_zone_id(None, -71.6) is None

    def test_zona_mas_cercana(self, tmp_path):
        db = tmp_path / "dispatch.db"
        _create_dispatch_db(str(db))
        conn = sqlite3.connect(str(db))
        # Zone 1: centro de Maracaibo (10.65, -71.6), radio 5km
        conn.execute(
            "INSERT INTO zones (id, name, center_lat, center_lng, radius_km) VALUES (?,?,?,?,?)",
            (1, "Centro", 10.65, -71.6, 5.0),
        )
        # Zone 2 más lejos
        conn.execute(
            "INSERT INTO zones (id, name, center_lat, center_lng, radius_km) VALUES (?,?,?,?,?)",
            (2, "Lejana", 11.0, -72.0, 5.0),
        )
        conn.commit()
        conn.close()
        with patch.object(bridge, "DISPATCH_DB_PATH", str(db)):
            # Punto casi en el centro → zone 1
            got = bridge._nearest_zone_id(10.65, -71.6)
            assert got == 1

    def test_fuera_de_rango_none(self, tmp_path):
        db = tmp_path / "dispatch.db"
        _create_dispatch_db(str(db))
        conn = sqlite3.connect(str(db))
        conn.execute(
            "INSERT INTO zones (id, name, center_lat, center_lng, radius_km) VALUES (?,?,?,?,?)",
            (1, "Centro", 10.65, -71.6, 5.0),
        )
        conn.commit()
        conn.close()
        with patch.object(bridge, "DISPATCH_DB_PATH", str(db)):
            # Punto muy lejos (≈ 100km) → fuera del radio → None
            assert bridge._nearest_zone_id(11.5, -71.6) is None

    def test_error_db_none(self, tmp_path):
        bad = tmp_path / "no" / "dispatch.db"
        with patch.object(bridge, "DISPATCH_DB_PATH", str(bad)):
            assert bridge._nearest_zone_id(10.65, -71.6) is None

    def test_zonas_sin_centro_se_ignoran(self, tmp_path):
        db = tmp_path / "dispatch.db"
        _create_dispatch_db(str(db))
        conn = sqlite3.connect(str(db))
        conn.execute(
            "INSERT INTO zones (id, name, center_lat, center_lng, radius_km) VALUES (?,?,?,?,?)",
            (1, "SinGPS", None, None, 5.0),
        )
        conn.commit()
        conn.close()
        with patch.object(bridge, "DISPATCH_DB_PATH", str(db)):
            assert bridge._nearest_zone_id(10.65, -71.6) is None


# ============================================================================
# Estado conversacional (FSM) — SQLite local
# ============================================================================

class TestConversationStatePersistence:
    def test_set_get_roundtrip(self, tmp_path):
        db = tmp_path / "conv.db"
        _create_conversation_db(str(db))
        ph = "ph-fsm-1"
        state = {"state": "awaiting_payment", "total": 5.4, "qty_bot": 3, "qty_hielo": 2}
        bridge._conversation_state.pop(ph, None)
        with patch.object(bridge, "SQLITE_PATH", str(db)):
            bridge._set_state(ph, dict(state))
            # Limpiar cache para forzar lectura desde SQLite
            bridge._conversation_state.pop(ph, None)
            got = bridge._get_state(ph)
            assert got.get("state") == "awaiting_payment"
            assert got.get("total") == 5.4

    def test_get_sin_estado_devuelve_default(self, tmp_path):
        db = tmp_path / "conv.db"
        _create_conversation_db(str(db))
        with patch.object(bridge, "SQLITE_PATH", str(db)):
            got = bridge._get_state("ph-sin-estado")
            assert got == {"state": None}

    def test_get_usa_cache(self, tmp_path):
        db = tmp_path / "conv.db"
        _create_conversation_db(str(db))
        ph = "ph-cache"
        bridge._conversation_state[ph] = {"state": "desde_cache"}
        with patch.object(bridge, "SQLITE_PATH", str(db)):
            assert bridge._get_state(ph) == {"state": "desde_cache"}

    def test_clear_elimina_estado(self, tmp_path):
        db = tmp_path / "conv.db"
        _create_conversation_db(str(db))
        ph = "ph-borrar"
        with patch.object(bridge, "SQLITE_PATH", str(db)):
            bridge._set_state(ph, {"state": "x"})
            bridge._conversation_state.pop(ph, None)  # limpiar cache
            assert bridge._get_state(ph) != {"state": None}
            bridge._clear_state(ph)
            bridge._conversation_state.pop(ph, None)  # limpiar cache
            assert bridge._get_state(ph) == {"state": None}


class TestOrderTotalsPersistence:
    def test_save_get_roundtrip(self, tmp_path):
        db = tmp_path / "conv.db"
        _create_conversation_db(str(db))
        ph = "ph-totals-1"
        bridge._last_order_totals.pop(ph, None)
        with patch.object(bridge, "SQLITE_PATH", str(db)):
            bridge._save_order_totals(ph, 4.40, 2, 2)
            bridge._last_order_totals.pop(ph, None)  # forzar lectura desde SQLite
            got = bridge._get_order_totals(ph)
            assert got["total"] == 4.40
            assert got["qty_bot"] == 2
            assert got["qty_hielo"] == 2

    def test_get_usa_cache(self, tmp_path):
        db = tmp_path / "conv.db"
        _create_conversation_db(str(db))
        ph = "ph-tot-cache"
        bridge._last_order_totals[ph] = {"total": 1.0, "qty_bot": 1, "qty_hielo": 0}
        with patch.object(bridge, "SQLITE_PATH", str(db)):
            assert bridge._get_order_totals(ph)["total"] == 1.0

    def test_get_sin_totales_none(self, tmp_path):
        db = tmp_path / "conv.db"
        _create_conversation_db(str(db))
        with patch.object(bridge, "SQLITE_PATH", str(db)):
            assert bridge._get_order_totals("ph-sin-totales") is None

    def test_clear_elimina_totales(self, tmp_path):
        db = tmp_path / "conv.db"
        _create_conversation_db(str(db))
        ph = "ph-tot-borrar"
        with patch.object(bridge, "SQLITE_PATH", str(db)):
            bridge._save_order_totals(ph, 2.20, 1, 1)
            bridge._last_order_totals.pop(ph, None)
            assert bridge._get_order_totals(ph) is not None
            bridge._clear_order_totals(ph)
            bridge._last_order_totals.pop(ph, None)
            assert bridge._get_order_totals(ph) is None


# ============================================================================
# Limpieza de caches globales entre tests (aislamiento)
# ============================================================================
