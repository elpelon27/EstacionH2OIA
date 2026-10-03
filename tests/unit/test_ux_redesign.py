"""
Tests del rediseño UX de Valentina: bancos VE, Pago Móvil ágil + QR, C2P 1-mensaje.

- Fase 1: scripts/banks_ve.py (normalize_bank: código/acrónimo/nombre/fuzzy)
- Fase 2: send_image_from_file (falla si no existe archivo, NO inventa QR),
  estado awaiting_qr_respuesta (SÍ envía QR + Ya pagué / NO directo a confirmar),
  PAGO_MOVIL_DATOS copiable
- Fase 3: parser registro 1-mensaje, cliente nuevo vs recurrente (clients.client_cedula),
  saludo personalizado 2da vez, español neutro (sin voseo)
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "api"))

os.environ["BRIDGE_ALLOW_INSECURE_SALT"] = "1"
os.environ.setdefault("C2P_ENABLED", "false")

import bridge  # noqa: E402
from scripts.banks_ve import BANCOS_VE, normalize_bank, nombre_banco  # noqa: E402

PH = "test_ux_phone_hash_001"
PHONE = "04145555555"


def _msg(text: str) -> dict:
    return {"type": "text", "text": {"body": text}}


# ============================================================
# FASE 1: mapa de bancos VE
# ============================================================

class TestBanksVe:
    def test_tamanio_gist(self):
        """El gist arodu trae 25 instituciones (verificado 2026-10-03)."""
        assert len(BANCOS_VE) == 25

    def test_codigos_reales_gist(self):
        """Códigos exactos del gist — NO inventados."""
        assert BANCOS_VE["0102"] == "BANCO DE VENEZUELA"
        assert BANCOS_VE["0105"] == "BANCO MERCANTIL"
        assert BANCOS_VE["0114"] == "BANCARIBE"
        assert BANCOS_VE["0169"] == "R4 BANCO MICROFINANCIERO C.A."
        assert BANCOS_VE["0191"] == "BANCO NACIONAL DE CREDITO"

    def test_codigo_directo(self):
        assert normalize_bank("0105") == "0105"
        assert normalize_bank("105") == "0105"  # sin ceros

    def test_acronimo(self):
        assert normalize_bank("BNC") == "0191"
        assert normalize_bank("BDV") == "0102"
        assert normalize_bank("BBVA") == "0108"

    def test_nombre_oficial(self):
        assert normalize_bank("Banco Mercantil") == "0105"
        assert normalize_bank("Banco Nacional de Crédito") == "0191"

    def test_fuzzy_typo(self):
        assert normalize_bank("mercantl") == "0105"
        assert normalize_bank("bankaribe") == "0114"

    def test_no_reconocido(self):
        assert normalize_bank("xyz inventado") is None
        assert normalize_bank("0199") is None  # código que no existe

    def test_nombre_banco(self):
        assert nombre_banco("0169").startswith("R4")
        assert nombre_banco("9999") == ""


# ============================================================
# FASE 2: Pago Móvil ágil + QR oficial
# ============================================================

class TestPagoMovilAgil:
    def setup_method(self):
        bridge._clear_state(PH)
        bridge._set_state(
            PH,
            {
                "state": "awaiting_payment",
                "total_eur": 3.0,
                "qty_botellones": 3,
                "address": "Av. Test",
                "contact_name": "Cliente Test",
            },
        )

    def teardown_method(self):
        bridge._clear_state(PH)

    def test_datos_copiables_completos(self):
        """Opción 1 → texto con Banco/RIF/Teléfono/Monto/Concepto + pregunta QR."""
        r = asyncio.run(bridge._handle_deterministic(PH, "1", PHONE, "Cliente Test", _msg("1"), {}))
        assert "R4 Banco Microfinanciero (0169)" in r["answer"]
        assert "J506356899" in r["answer"]
        assert "04122560721" in r["answer"]
        assert "Concepto: Agua H2O" in r["answer"]
        assert "QR oficial" in r["answer"]
        buttons = r["interactive"]["buttons"]
        assert [b["id"] for b in buttons] == ["qr_si", "qr_no"]

    def test_qr_si_envia_imagen_oficial(self):
        """SÍ → llama send_image_from_file con la ruta del QR OFICIAL (estático)."""
        bridge._set_state(PH, {**bridge._get_state(PH), "state": "awaiting_qr_respuesta"})
        with patch.object(
            bridge, "send_image_from_file", new=AsyncMock(return_value=True)
        ) as mock_img:
            r = asyncio.run(
                bridge._handle_deterministic(PH, "sí", PHONE, "Cliente Test", _msg("sí"), {})
            )
        mock_img.assert_awaited_once()
        args = mock_img.call_args.args
        assert args[1] == bridge.QR_R4_OFICIAL_PATH  # archivo estático, no generado
        assert bridge._get_state(PH)["state"] == "awaiting_confirmation"
        assert any(b["id"] == "ya_pague" for b in r["interactive"]["buttons"])

    def test_qr_no_sin_imagen(self):
        """NO → NO envía imagen, directo a confirmación con Ya pagué."""
        bridge._set_state(PH, {**bridge._get_state(PH), "state": "awaiting_qr_respuesta"})
        with patch.object(
            bridge, "send_image_from_file", new=AsyncMock(return_value=True)
        ) as mock_img:
            r = asyncio.run(
                bridge._handle_deterministic(PH, "no", PHONE, "Cliente Test", _msg("no"), {})
            )
        mock_img.assert_not_awaited()
        assert bridge._get_state(PH)["state"] == "awaiting_confirmation"

    def test_send_image_archivo_inexistente_falla(self):
        """Archivo faltante → False + log de error. NUNCA inventa QR."""
        r = asyncio.run(bridge.send_image_from_file(PHONE, "/no/existe/qr.png"))
        assert r is False

    def test_qr_oficial_existe_en_ruta(self):
        """El Líder colocó el QR oficial en la ruta esperada."""
        assert os.path.isfile(bridge.QR_R4_OFICIAL_PATH)

    def test_ya_pague_sigue_funcionando(self):
        """Regresión: el estado awaiting_confirmation no cambió."""
        bridge._set_state(PH, {**bridge._get_state(PH), "state": "awaiting_confirmation",
                                "payment_method": "Pago Móvil", "total_eur": 3.0,
                                "qty_botellones": 3, "address": "Av. Test"})
        with patch.object(bridge, "_send_to_dispatch_queue") as mock_q:
            r = asyncio.run(
                bridge._handle_deterministic(PH, "ya pagué", PHONE, "Cliente Test", _msg("ya pagué"), {})
            )
        mock_q.assert_called_once()
        assert "Pedido completado" in r["answer"]


# ============================================================
# FASE 3: C2P 1-mensaje + personalización + recurrente
# ============================================================

class TestParserRegistro:
    def test_parser_formato_correcto(self):
        nombre, cedula, banco = bridge._c2p_parsear_registro("Karla Perez V12345678 BNC")
        assert nombre == "Karla Perez"
        assert cedula == "V12345678"
        assert banco == "BNC"

    def test_parser_cedula_con_guion(self):
        nombre, cedula, banco = bridge._c2p_parsear_registro("José García E-1234567 Mercantil")
        assert nombre == "José García"
        assert cedula == "E1234567"
        assert banco == "Mercantil"

    def test_parser_falta_banco(self):
        assert bridge._c2p_parsear_registro("Karla Perez V12345678") is None

    def test_parser_falta_nombre(self):
        assert bridge._c2p_parsear_registro("V12345678 BNC") is None

    def test_parser_sin_cedula(self):
        assert bridge._c2p_parsear_registro("Karla Perez BNC") is None


class TestC2pUnMensaje:
    def setup_method(self):
        bridge._clear_state(PH)
        bridge._set_state(
            PH,
            {
                "state": "awaiting_payment",
                "total_eur": 3.0,
                "qty_botellones": 3,
                "address": "Av. Test",
                "contact_name": "Cliente Test",
            },
        )

    def teardown_method(self):
        bridge._clear_state(PH)

    def test_cliente_nuevo_pide_registro_1_mensaje(self):
        """Cliente sin cédula guardada → un solo mensaje con nombre+cédula+banco."""
        with patch.object(bridge, "C2P_ENABLED", True), patch.object(
            bridge, "_c2p_datos_guardados", return_value={"cedula": "", "banco": "", "nombre": ""}
        ):
            r = asyncio.run(bridge._handle_deterministic(PH, "2", PHONE, "Cliente Test", _msg("2"), {}))
        assert "en un solo mensaje" in r["answer"]
        assert "Ejemplo: Karla Perez V12345678 BNC" in r["answer"]
        assert bridge._get_state(PH)["state"] == "awaiting_c2p_registro"

    def test_registro_completo_avanza_a_otp(self):
        """Mensaje completo → guarda datos + pide clave dinámica con el nombre."""
        with patch.object(bridge, "C2P_ENABLED", True), patch.object(
            bridge, "_c2p_guardar_dato_cliente"
        ) as mock_save, patch.object(
            bridge, "_c2p_disparar_generar_otp"
        ) as mock_otp, patch(
            "src.integrations.r4.client.R4Client.cobro_c2p",
            new=AsyncMock(),
        ):
            bridge._set_state(PH, {**bridge._get_state(PH), "state": "awaiting_c2p_registro"})
            r = asyncio.run(
                bridge._handle_deterministic(
                    PH, "Karla Perez V12345678 BNC", PHONE, "Cliente Test",
                    _msg("Karla Perez V12345678 BNC"), {}
                )
            )
        # Guardó nombre, cédula y banco
        guardados = {call.args[1] for call in mock_save.call_args_list}
        assert {"client_cedula", "client_banco_emisor", "name"} <= guardados
        # Mensaje personalizado con nombre + clave dinámica (2846)
        assert "Listo, Karla Perez" in r["answer"]
        assert "2846" in r["answer"]
        mock_otp.assert_called_once()
        assert bridge._get_state(PH)["state"] == "awaiting_c2p_otp"
        assert bridge._get_state(PH)["c2p_banco"] == "0191"  # BNC normalizado

    def test_banco_no_reconocido_reintenta(self):
        with patch.object(bridge, "C2P_ENABLED", True):
            bridge._set_state(PH, {**bridge._get_state(PH), "state": "awaiting_c2p_registro"})
            r = asyncio.run(
                bridge._handle_deterministic(
                    PH, "Karla Perez V12345678 Banco Inventado XYZ", PHONE, "Cliente Test",
                    _msg("Karla Perez V12345678 Banco Inventado XYZ"), {}
                )
            )
        assert "No reconocí su banco" in r["answer"]
        assert bridge._get_state(PH)["state"] == "awaiting_c2p_registro"

    def test_cliente_recurrente_no_pide_datos(self):
        """Cédula+banco guardados → directo a OTP sin pedir nada (solo clave)."""
        datos = {"cedula": "V12345678", "banco": "0191", "nombre": "Karla Perez"}
        with patch.object(bridge, "C2P_ENABLED", True), patch.object(
            bridge, "_c2p_datos_guardados", return_value=datos
        ), patch.object(bridge, "_c2p_disparar_generar_otp") as mock_otp:
            r = asyncio.run(bridge._handle_deterministic(PH, "2", PHONE, "Cliente Test", _msg("2"), {}))
        # NO pide cédula/banco — el mensaje solo pide la clave dinámica
        assert "cédula" not in r["answer"].lower()
        assert "Karla Perez" in r["answer"]
        assert "2846" in r["answer"]
        mock_otp.assert_called_once()
        assert bridge._get_state(PH)["state"] == "awaiting_c2p_otp"
        assert bridge._get_state(PH)["c2p_cedula"] == "V12345678"


class TestPersonalizacion:
    def test_saludo_con_nombre_2da_vez(self):
        """Cliente recurrente → menú principal lo saluda por su nombre."""
        datos = {"cedula": "V12345678", "banco": "0191", "nombre": "Karla Perez Gomez"}
        with patch.object(bridge, "_c2p_datos_guardados", return_value=datos), patch(
            "scripts.security.geofence.check_location",
            return_value={"status": "ok", "message": "Dentro de la zona"},
        ):
            r = bridge._geofence_gate(PH, PHONE, 10.6725, -71.6126)
        assert "¡Hola, Karla!" in r["interactive"]["body"]
        assert "Qué gusto de nuevo" in r["interactive"]["body"]

    def test_saludo_generico_cliente_nuevo(self):
        """Sin datos guardados → saludo genérico (sin personalización)."""
        with patch.object(
            bridge, "_c2p_datos_guardados", return_value={}
        ), patch(
            "scripts.security.geofence.check_location",
            return_value={"status": "ok", "message": "Dentro de la zona"},
        ):
            r = bridge._geofence_gate(PH, PHONE, 10.6725, -71.6126)
        assert "Buen día" in r["interactive"]["body"]
        assert "Hola," not in r["interactive"]["body"]


class TestEspanolNeutroRedesign:
    def test_sin_voseo_en_mensajes_nuevos(self):
        """Los textos del rediseño no usan voseo argentino."""
        textos = [
            bridge.C2P_MSG_REGISTRO,
            bridge.C2P_MSG_BANCO_NO_RECONOCIDO,
            bridge.PAGO_MOVIL_QR_PREGUNTA,
            bridge.PAGO_MOVIL_QR_SI,
            bridge._c2p_msg_solicitud_otp("Ana", "10.00"),
            bridge._c2p_msg_cobro_recurrente("Ana", "10.00"),
        ]
        prohibidos = ["solicitá", "enviame", "envíame", "decime", "podés", "tenés",
                      "querés", "pagas con", "intentamos de nuevo o pagas"]
        for t in textos:
            low = t.lower()
            for p in prohibidos:
                assert p not in low, f"Voseo '{p}' en: {t}"
            assert "usted" in low or "su " in low or "le " in low or "envíeme" in low or "escríbamela" in low

    def test_usa_envieme_y_escrbamela(self):
        assert "envíeme" in bridge.C2P_MSG_REGISTRO
        assert "escríbamela" in bridge._c2p_msg_solicitud_otp("Ana", "10.00")
