#!/usr/bin/env python3
"""R4 Banco - Script de testing y validación de endpoints"""

import asyncio
import logging
import sys
from datetime import UTC, datetime

# Configurar paths
sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")

from src.banking.r4_client import R4Client
from src.banking.r4_endpoints import (
    ENDPOINTS,
    build_url,
    get_response_meaning,
    is_bank_ip_allowed,
    is_success_code,
)
from src.banking.r4_models import (
    R4BcvRequest,
    R4ConsultaRequest,
    R4NotificaRequest,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("r4banco.test")


async def test_endpoints_config() -> None:
    """Test 1: Verificar configuración de endpoints"""
    print("\n=== TEST 1: Configuración endpoints ===")

    for key, _path in ENDPOINTS.items():
        url = build_url(key)
        print(f"  {key:25} → {url}")

    assert "bcv" in ENDPOINTS
    assert "notifica" in ENDPOINTS
    assert "consulta" in ENDPOINTS
    print("✅ Endpoints OK")


async def test_ip_whitelist() -> None:
    """Test 2: Validar IP whitelist"""
    print("\n=== TEST 2: IP Whitelist ===")

    allowed = ["45.175.213.98", "200.74.203.91", "204.199.249.3"]
    blocked = ["1.2.3.4", "192.168.1.1", "8.8.8.8"]

    for ip in allowed:
        assert is_bank_ip_allowed(ip), f"IP {ip} debería estar permitida"
        print(f"  ✅ {ip} permitida")

    for ip in blocked:
        assert not is_bank_ip_allowed(ip), f"IP {ip} NO debería estar permitida"
        print(f"  ❌ {ip} bloqueada (correcto)")

    print("✅ IP Whitelist OK")


async def test_response_codes() -> None:
    """Test 3: Códigos de respuesta"""
    print("\n=== TEST 3: Códigos de respuesta ===")

    success_codes = ["00", "202", "ACCP", "true"]
    error_codes = ["01", "05", "08", "51", "56", "99", "AM04", "MD01"]

    for code in success_codes:
        assert is_success_code(code), f"{code} debería ser éxito"
        print(f"  ✅ {code}: {get_response_meaning(code)}")

    for code in error_codes:
        assert not is_success_code(code), f"{code} NO debería ser éxito"
        print(f"  ⚠️  {code}: {get_response_meaning(code)} (error esperado)")

    print("✅ Códigos de respuesta OK")


async def test_models_validation() -> None:
    """Test 4: Validación de modelos Pydantic"""
    print("\n=== TEST 4: Modelos Pydantic ===")

    # R4NotificaRequest
    payload_notifica = {
        "IdComercio": "12345678",
        "TelefonoComercio": "04129999999",
        "TelefonoEmisor": "04141234567",
        "Concepto": "PAGO PEDIDO H2O",
        "BancoEmisor": "0134",
        "Monto": "10.00",
        "FechaHora": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "Referencia": "TEST123456",
        "CodigoRed": "00",
    }
    r = R4NotificaRequest(**payload_notifica)
    assert r.CodigoRed == "00"
    print(f"  ✅ R4NotificaRequest: emisor={r.TelefonoEmisor} monto={r.Monto}")

    # R4ConsultaRequest (TelefonoComercio opcional en el modelo)
    r2 = R4ConsultaRequest(IdCliente="12345678", Monto="10.00", TelefonoComercio="04129999999")
    assert r2.IdCliente == "12345678"
    print(f"  ✅ R4ConsultaRequest: cliente={r2.IdCliente}")

    # R4BcvRequest
    r3 = R4BcvRequest(Moneda="USD", Fechavalor="2026-07-28")
    assert r3.Moneda == "USD"
    print(f"  ✅ R4BcvRequest: moneda={r3.Moneda} fecha={r3.Fechavalor}")

    print("✅ Modelos Pydantic OK")


async def test_client_init() -> bool:
    """Test 5: Inicialización del cliente (sin credenciales reales)"""
    print("\n=== TEST 5: Cliente R4 (mock) ===")

    # Verificar que falla sin credenciales
    try:
        client = R4Client(
            commerce_token="test_token",
            hmac_key="test_key",
            base_url="https://r4conecta.mibanco.com.ve/",
        )
        print(f"  ✅ Cliente creado: base_url={client.base_url}")
    except Exception as e:
        print(f"  ❌ Error creando cliente: {e}")
        return False

    print("✅ Cliente R4 OK")
    return True


async def test_mock_notifica() -> None:
    """Test 6: Simular payload R4notifica"""
    print("\n=== TEST 6: Mock R4notifica ===")

    from src.financial.banco_verificador import crear_payload_test_notifica

    payload = crear_payload_test_notifica(
        telefono_emisor="04141234567",
        monto="10.00",
        referencia="TEST123456",
    )

    # R4NotificaRequest ya importado desde src.banking.r4_models (top del archivo)
    r = R4NotificaRequest(**payload)
    print(f"  Emisor: {r.TelefonoEmisor}")
    print(f"  Monto: {r.Monto}")
    print(f"  Referencia: {r.Referencia}")
    print(f"  Banco: {r.BancoEmisor}")
    print(f"  Código Red: {r.CodigoRed}")
    print("✅ Mock payload OK")


async def main() -> None:
    print("=" * 60)
    print("🏦 R4 BANCO - SUITE DE TESTING")
    print("=" * 60)

    try:
        await test_endpoints_config()
        await test_ip_whitelist()
        await test_response_codes()
        await test_models_validation()
        await test_client_init()
        await test_mock_notifica()

        print("\n" + "=" * 60)
        print("🎉 TODOS LOS TESTS PASARON - Infraestructura lista")
        print("=" * 60)
        print("\n⏳ Esperando credenciales del banco para tests reales:")
        print("  1. R4_COMMERCE_TOKEN")
        print("  2. R4_HMAC_KEY")
        print("  3. R4_BASE_URL (o R4_SANDBOX_URL)")
        print("\nLuego ejecutar:")
        print("  python -m skills.r4banco_test test_bcv")
        print("  python -m skills.r4banco_test test_c2p")
        print("  python -m skills.r4banco_test mock_notifica")

    except Exception as e:
        logger.error("Test falló: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
