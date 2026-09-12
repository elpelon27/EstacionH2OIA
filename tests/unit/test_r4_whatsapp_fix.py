#!/usr/bin/env python3
"""
Tests para el fix del httpx client en webhook R4 — WhatsApp al cliente.

Causa raíz (bug real del pago 2026-09-12 16:53):
El systemd corre `uvicorn bridge:app` (cwd=api/) → módulo live es `bridge`,
cuyo _http_client SÍ está inicializado en startup. Pero el webhook R4 hacía
`from api.bridge import _send_whatsapp_message`, cargando una SEGUNDA copia
del módulo (`api.bridge`) cuyo _http_client es None → "http client not
initialized" → el cliente nunca recibía "✅ Pago confirmado".

Fix: preferir el módulo live con client inicializado (bridge, luego api.bridge);
si ninguno lo tiene, crear un client httpx para el envío (best-effort).

Cubre:
- Webhook R4 envía WhatsApp al cliente cuando pago OK (usa el módulo live)
- Si WhatsApp falla, el pago sigue verificado (best-effort)
- Payload real del banco + teléfono en formato 584122560720
"""

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")

from src.integrations.r4.webhooks import (
    R4NotificaRequest,
    R4WebhookConfig,
    process_r4notifica,
)


def _payload() -> R4NotificaRequest:
    return R4NotificaRequest(
        IdComercio="13536734",
        TelefonoComercio="04122227777",
        TelefonoEmisor="04122560720",
        Concepto="PAGO",
        BancoEmisor="0105",
        Monto="2933.63",
        FechaHora="2026-09-12T20:53:45Z",
        Referencia="125556473809",
        CodigoRed="00",
    )


@pytest.fixture
def mock_config() -> R4WebhookConfig:
    return R4WebhookConfig()


@pytest.fixture
def pedido_ok():
    from src.financial.database import PedidoFinanciero

    return PedidoFinanciero(
        id=2109,
        pedido_id=2109,
        cliente_telefono="584122560720",
        monto_total_eur=3.0,
        tasa_eur_ves=977.88,
        estado_pago="pendiente",
    )


@pytest.fixture(autouse=True)
def _setup_pipeline(pedido_ok):
    """Parchea todo el pipeline salvo el envío de WhatsApp."""
    with patch(
        "src.financial.database.buscar_pedidos_por_telefono_monto",
        return_value=[pedido_ok],
    ), patch(
        "src.financial.database.seleccionar_mejor_match",
        return_value=pedido_ok,
    ), patch(
        "src.financial.currency.get_eur_ves_rate",
        new_callable=AsyncMock,
        return_value=977.88,
    ), patch(
        "src.financial.verificacion.verificar_pago_manual",
        new_callable=AsyncMock,
        return_value={"success": True, "nuevo_estado": "pagado"},
    ), patch(
        "src.integrations.odoo.odoo_sync.OdooClient.connect",
        return_value=False,
    ):
        yield


@pytest.fixture
def live_bridge_module():
    """Simula el módulo live `bridge` con httpx client inicializado."""
    send = AsyncMock(return_value=True)
    mod = types.ModuleType("bridge")
    mod._http_client = MagicMock()  # type: ignore[attr-defined]  # inicializado → módulo vivo
    mod._send_whatsapp_message = send  # type: ignore[attr-defined]
    with patch.dict(sys.modules, {"bridge": mod}):
        yield mod, send


class TestWhatsAppClienteEnR4:
    @pytest.mark.asyncio
    async def test_envia_whatsapp_usando_modulo_live_con_client(
        self, mock_config, live_bridge_module, pedido_ok
    ) -> None:
        """El webhook debe usar el módulo `bridge` (client inicializado),
        NO la copia fría `api.bridge` (client=None) que causaba el fallo."""
        mod_live, send_mock = live_bridge_module
        result = await process_r4notifica(_payload(), mock_config)
        assert result.success is True
        send_mock.assert_awaited_once()
        args = send_mock.await_args.args
        assert args[0] == "584122560720", f"teléfono mal formateado: {args[0]}"
        assert args[1] == "✅ Pago confirmado. Gracias. 💧"

    @pytest.mark.asyncio
    async def test_whatsapp_falla_pago_sigue_verificado(
        self, mock_config, live_bridge_module
    ) -> None:
        """Best-effort: si el envío de WhatsApp lanza, el pago sigue OK."""
        mod_live, send_mock = live_bridge_module
        send_mock.side_effect = Exception("http client not initialized")
        result = await process_r4notifica(_payload(), mock_config)
        assert result.success is True
        assert "Pago verificado" in result.message

    @pytest.mark.asyncio
    async def test_envio_directo_si_ningun_modulo_live(
        self, mock_config, pedido_ok
    ) -> None:
        """Sin módulo live disponible: el fix crea su propio client httpx
        y envía directamente por Meta Graph API (best-effort)."""
        # api.bridge cargado frío (sin client) — escenario del bug real
        import api.bridge as cold_bridge

        saved_client = getattr(cold_bridge, "_http_client", None)
        cold_bridge._http_client = None  # type: ignore[attr-defined]
        try:
            with patch.dict(sys.modules, {}, clear=False):
                sys.modules.pop("bridge", None)
                with patch(
                    "src.integrations.r4.webhooks._enviar_whatsapp_directo",
                    new_callable=AsyncMock,
                    return_value=True,
                ) as directo:
                    result = await process_r4notifica(_payload(), mock_config)
            assert result.success is True
            directo.assert_awaited_once()
            assert directo.await_args.args[0] == "584122560720"
        finally:
            cold_bridge._http_client = saved_client

    @pytest.mark.asyncio
    async def test_payload_banco_real_envia_confirmacion(
        self, mock_config, live_bridge_module
    ) -> None:
        """Payload real del banco del pago 16:53 — end-to-end del envío."""
        mod_live, send_mock = live_bridge_module
        result = await process_r4notifica(_payload(), mock_config)
        assert result.success is True
        assert send_mock.await_count == 1
