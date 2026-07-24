"""Tests unitarios para api/bridge.py — funciones determinísticas.

Testea funciones del bridge que no requieren servicios externos (no mockea
httpx, Dify, Meta API, etc.). Funciones puras con input → output predecible.

Cobertura:
- _calc_total: cálculo determinístico de precios
- _format_product_desc: formato de descripción para confirmación
- _phone_hash: hash determinístico del teléfono
- _detect_message_type: detección de tipo de mensaje interactivo
- _fix_total_in_response: corrección de total del LLM
"""

import os
import sys

# Path setup
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "api"))

# Bypass LOG_SALT para tests
os.environ["BRIDGE_ALLOW_INSECURE_SALT"] = "1"

import bridge


class TestCalcTotal:
    """_calc_total: cálculo determinístico de precios."""

    def test_solo_agua(self):
        assert bridge._calc_total(3, 0) == 3.00

    def test_solo_hielo(self):
        assert bridge._calc_total(0, 3) == 3.60

    def test_combo(self):
        assert bridge._calc_total(3, 2) == 5.40  # 3*1.00 + 2*1.20

    def test_cero(self):
        assert bridge._calc_total(0, 0) == 0.00

    def test_redondeo(self):
        # 1 botellon + 1 hielo = 1.00 + 1.20 = 2.20
        assert bridge._calc_total(1, 1) == 2.20

    def test_cantidades_grandes(self):
        assert bridge._calc_total(10, 10) == 22.00


class TestFormatProductDesc:
    """_format_product_desc: formato de descripción para confirmación."""

    def test_solo_agua(self):
        result = bridge._format_product_desc(3, 0)
        assert "3 botellones de agua" in result

    def test_solo_hielo(self):
        result = bridge._format_product_desc(0, 2)
        assert "2 bolsas de hielo" in result

    def test_combo(self):
        result = bridge._format_product_desc(3, 2)
        assert "3 botellones de agua" in result
        assert "2 bolsas de hielo" in result

    def test_cero_cero(self):
        result = bridge._format_product_desc(0, 0)
        # No debe tener contenido de productos
        assert "botellones" not in result
        assert "hielo" not in result


class TestPhoneHash:
    """_phone_hash: hash determinístico del teléfono."""

    def test_deterministico(self):
        h1 = bridge._phone_hash("+584122560721")
        h2 = bridge._phone_hash("+584122560721")
        assert h1 == h2

    def test_diferentes_telefonos(self):
        h1 = bridge._phone_hash("+584122560721")
        h2 = bridge._phone_hash("+584127110000")
        assert h1 != h2

    def test_longitud_fija(self):
        h = bridge._phone_hash("+584122560721")
        assert len(h) == 32  # SHA256[:32]

    def test_no_es_vacio(self):
        h = bridge._phone_hash("+584122560721")
        assert h != ""
        assert h is not None


class TestDetectMessageType:
    """_detect_message_type: detección de tipo de mensaje interactivo."""

    def test_vacio(self):
        result = bridge._detect_message_type("")
        assert result["type"] == "text"

    def test_none(self):
        result = bridge._detect_message_type(None)
        assert result["type"] == "text"

    def test_texto_simple(self):
        result = bridge._detect_message_type("Hola, buenos dias")
        assert result["type"] == "text"

    def test_menu_principal(self):
        # Mensaje con 1️⃣ ... 5️⃣ + "opción" o "servirle"
        msg = "¡Buen dia! 1️⃣ Recarga 2️⃣ Hielo 3️⃣ Combo 4️⃣ Estado 5️⃣ Otra opción"
        result = bridge._detect_message_type(msg)
        assert result["type"] == "list"
        assert "list_sections" in result

    def test_deteccion_pago(self):
        msg = "¿Cómo desea pagar? 1️⃣ Pago Móvil 2️⃣ Efectivo"
        result = bridge._detect_message_type(msg)
        assert result["type"] == "button"

    def test_deteccion_pago_variacion(self):
        # Variacion sin acentos pero con palabra clave
        msg = "¿Como desea pagar? 1️⃣ Pago Móvil 2️⃣ Efectivo"
        result = bridge._detect_message_type(msg)
        assert result["type"] == "button"

    def test_deteccion_pago_metodo(self):
        msg = "Seleccione metodo de pago: 1 Pago Movil 2 Efectivo"
        result = bridge._detect_message_type(msg)
        assert result["type"] == "button"


class TestFixTotalInResponse:
    """_fix_total_in_response: corrección de total del LLM."""

    def test_corregir_total_punto(self):
        # LLM dice €6.00 pero el bridge calculó €3.00
        payload = {"total_eur": 3.00, "_llm_total": 6.00}
        fixed = bridge._fix_total_in_response("Total: €6.00", payload)
        assert "€3.00" in fixed
        assert "€6.00" not in fixed

    def test_corregir_total_coma(self):
        # LLM usa coma decimal (formato europeo)
        payload = {"total_eur": 3.00, "_llm_total": 6.00}
        fixed = bridge._fix_total_in_response("Total: €6,00", payload)
        assert "€3.00" in fixed

    def test_corregir_total_euros_texto(self):
        # "Total: 6 euros" → "Total: €3.00"
        payload = {"total_eur": 3.00, "_llm_total": 6.00}
        fixed = bridge._fix_total_in_response("Total: 6 euros", payload)
        assert "€3.00" in fixed

    def test_no_corregir_total_correcto(self):
        # LLM calcule bien — no debe cambiar
        payload = {"total_eur": 3.00, "_llm_total": 3.00}
        answer = "Total: €3.00"
        fixed = bridge._fix_total_in_response(answer, payload)
        assert "€3.00" in fixed

    def test_total_cero_no_corregir(self):
        # Si total_eur es 0, no debe tocar la respuesta
        payload = {"total_eur": 0, "_llm_total": 0}
        answer = "Total: €6.00"
        fixed = bridge._fix_total_in_response(answer, payload)
        assert fixed == answer

    def test_preservar_resto_mensaje(self):
        # El resto del mensaje no debe verse afectado
        payload = {"total_eur": 2.20, "_llm_total": 5.00}
        answer = "Confirmo: 1 botellon + 1 hielo. Total: €5.00. ¿Cómo paga?"
        fixed = bridge._fix_total_in_response(answer, payload)
        assert "Confirmo: 1 botellon + 1 hielo." in fixed
        assert "¿Cómo paga?" in fixed
        assert "€2.20" in fixed
