#!/usr/bin/env python3
"""
Tests para el fix de conversión VES→EUR en casación R4 (bug crítico).

Regla de negocio del Líder:
- Saldo (fs_pedidos.monto_total_eur) SIEMPRE en EUR, fijo
- El banco notifica Monto en VES; la casación debe convertir VES→EUR
  con la tasa BCV del DÍA DEL PAGO antes de comparar (±1%)
- Pedido guarda su propia tasa_eur_ves (puede diferir de la del pago —
  NO es error de casación)

Cubre:
- process_r4notifica pasa monto EUR convertido a buscar_pedidos_por_telefono_monto
- Pago VES que convierte a EUR y casa con pedido EUR
- Pago VES que NO casa (monto EUR fuera de ±1%)
- Tasa del pago distinta a la tasa del pedido (debe casar igual)
- Payload del banco con monto VES string
- Tasa no disponible → fallback al monto EUR del pedido
"""

import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")

from src.integrations.r4.webhooks import (
    R4NotificaRequest,
    R4WebhookConfig,
    process_r4notifica,
)


def _payload(monto_ves: str = "2933.63", emisor: str = "04122560720") -> R4NotificaRequest:
    return R4NotificaRequest(
        IdComercio="13536734",
        TelefonoComercio="04122227777",
        TelefonoEmisor=emisor,
        Concepto="PAGO",
        BancoEmisor="0105",
        Monto=monto_ves,
        FechaHora="2026-09-12T14:12:32Z",
        Referencia="125556273821",
        CodigoRed="00",
    )


@pytest.fixture
def mock_config() -> R4WebhookConfig:
    return R4WebhookConfig()


class TestConvesionVESaEURNotifica:
    """El webhook debe convertir VES→EUR ANTES de buscar el pedido."""

    @pytest.mark.asyncio
    async def test_busca_con_monto_eur_convertido(self, mock_config) -> None:
        # 2933.63 VES / 977.88 = 3.00 EUR exactos
        buscar_mock = patch(
            "src.financial.database.buscar_pedidos_por_telefono_monto",
            return_value=[],
        )
        with buscar_mock as m, patch(
            "src.financial.currency.get_eur_ves_rate",
            new_callable=AsyncMock,
            return_value=977.88,
        ):
            await process_r4notifica(_payload(), mock_config)
            kwargs = m.call_args.kwargs
            assert float(kwargs["monto_str"]) == 3.00, (
                f"Debe pasar EUR convertido (3.00), pasó: {kwargs['monto_str']}"
            )

    @pytest.mark.asyncio
    async def test_pago_ves_casa_con_pedido_eur(self, mock_config) -> None:
        # Pedido EUR 3.0; pago 2933.63 VES a tasa 977.88 → 3.00 EUR → MATCH
        from src.financial.database import PedidoFinanciero

        pedido = PedidoFinanciero(
            id=2108,
            pedido_id=2108,
            cliente_telefono="584122560720",
            monto_total_eur=3.0,
            tasa_eur_ves=977.88,
            estado_pago="pendiente",
        )
        with patch(
            "src.financial.database.buscar_pedidos_por_telefono_monto",
            return_value=[pedido],
        ), patch(
            "src.financial.database.seleccionar_mejor_match",
            return_value=pedido,
        ), patch(
            "src.financial.currency.get_eur_ves_rate",
            new_callable=AsyncMock,
            return_value=977.88,
        ), patch(
            "src.financial.verificacion.verificar_pago_manual",
            new_callable=AsyncMock,
            return_value={"success": True, "nuevo_estado": "pagado"},
        ):
            result = await process_r4notifica(_payload(), mock_config)
        assert result.success is True
        assert "NO_ORDER" not in result.message

    @pytest.mark.asyncio
    async def test_pago_ves_no_casa_si_eur_fuera_de_tolerancia(self, mock_config) -> None:
        # Pago 5000 VES a tasa 977.88 → 5.11 EUR ≠ 3.0 EUR ±1% → sin pedido
        with patch(
            "src.financial.database.buscar_pedidos_por_telefono_monto",
            return_value=[],
        ) as buscar, patch(
            "src.financial.currency.get_eur_ves_rate",
            new_callable=AsyncMock,
            return_value=977.88,
        ):
            result = await process_r4notifica(_payload(monto_ves="5000.00"), mock_config)
        assert result.success is True
        assert "NO_ORDER" in result.message
        # Se buscó con el EUR convertido (5.11), no con el VES crudo
        assert float(buscar.call_args.kwargs["monto_str"]) == 5.11

    @pytest.mark.asyncio
    async def test_tasa_pago_distinta_a_tasa_pedido_casa_igual(self, mock_config) -> None:
        # Pedido creado con tasa 823.94 (vieja) pero monto_total_eur=3.0 fijo.
        # Paga 2933.63 VES con tasa del día 977.88 → 3.00 EUR → MATCH igual.
        from src.financial.database import PedidoFinanciero

        pedido = PedidoFinanciero(
            id=1,
            pedido_id=1,
            cliente_telefono="584122560720",
            monto_total_eur=3.0,
            tasa_eur_ves=823.94,  # tasa vieja del pedido
            estado_pago="pendiente",
        )
        with patch(
            "src.financial.database.buscar_pedidos_por_telefono_monto",
            return_value=[pedido],
        ), patch(
            "src.financial.database.seleccionar_mejor_match",
            return_value=pedido,
        ), patch(
            "src.financial.currency.get_eur_ves_rate",
            new_callable=AsyncMock,
            return_value=977.88,  # tasa del DÍA del pago, distinta
        ), patch(
            "src.financial.verificacion.verificar_pago_manual",
            new_callable=AsyncMock,
            return_value={"success": True, "nuevo_estado": "pagado"},
        ):
            result = await process_r4notifica(_payload(), mock_config)
        assert result.success is True
        assert "NO_ORDER" not in result.message

    @pytest.mark.asyncio
    async def test_tasa_no_disponible_fail_safe_no_order(self, mock_config) -> None:
        # get_eur_ves_rate → None: NO se puede convertir VES→EUR de forma
        # confiable. Fail-safe: no casar contra VES crudo; responder NO_ORDER
        # (el banco ya recibió abono=True, el pago queda para conciliación
        # manual) y nunca pasar el monto VES como si fuera EUR.
        with patch(
            "src.financial.database.buscar_pedidos_por_telefono_monto",
            return_value=[],
        ) as buscar, patch(
            "src.financial.currency.get_eur_ves_rate",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await process_r4notifica(_payload(), mock_config)
        # Nunca se busca con el VES crudo (2933.63) como monto EUR
        assert not buscar.called or float(buscar.call_args.kwargs["monto_str"]) != 2933.63
        assert result.success is True  # graceful al banco
        assert "NO_ORDER" in result.message

    @pytest.mark.asyncio
    async def test_payload_banco_monto_ves_string_decimales(self, mock_config) -> None:
        # Payload real del banco: Monto string "2933.63" → EUR "3.0" (no crash)
        with patch(
            "src.financial.database.buscar_pedidos_por_telefono_monto",
            return_value=[],
        ) as buscar, patch(
            "src.financial.currency.get_eur_ves_rate",
            new_callable=AsyncMock,
            return_value=977.88,
        ):
            await process_r4notifica(_payload(monto_ves="2933.63"), mock_config)
        assert float(buscar.call_args.kwargs["monto_str"]) == 3.00
