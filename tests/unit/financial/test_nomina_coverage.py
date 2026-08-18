"""
Coverage tests for src/financial/nomina.py — mock BD, test cálculo de nómina.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.financial.models import Empleado, Nomina
from src.financial.nomina import (
    _contar_botellones_repartidos,
    calcular_nomina_periodo,
    guardar_nomina,
    generar_reporte_nomina,
)


def _make_empleado(**overrides) -> Empleado:
    defaults = dict(
        id=1,
        nombre="Pedro Pérez",
        rol="operador",
        telefono="+584121234567",
        sueldo_fijo_eur=300.0,
        comision_botellon_eur=0.07,
        activo=True,
    )
    defaults.update(overrides)
    return Empleado(**defaults)


# ---------------------------------------------------------------------------
# calcular_nomina_periodo
# ---------------------------------------------------------------------------

class TestCalcularNominaPeriodo:
    async def test_calcular_con_empleados_explicitos(self):
        """Test cálculo with explicit empleados list and mocked tasa."""
        empleados = [_make_empleado(), _make_empleado(id=2, nombre="Ana García")]
        with (
            patch("src.financial.nomina.get_eur_ves_rate", AsyncMock(return_value=100.0)),
            patch("src.financial.nomina._contar_botellones_repartidos", return_value=50),
        ):
            nominas = await calcular_nomina_periodo("2026-08-01", "2026-08-15", empleados)

        assert len(nominas) == 2
        # Pedro: 300 + 50*0.07 = 303.50
        assert nominas[0].empleado_nombre == "Pedro Pérez"
        assert nominas[0].sueldo_fijo_eur == 300.0
        assert nominas[0].comision_total_eur == 3.50  # 50 * 0.07
        assert nominas[0].total_eur == 303.50
        assert nominas[0].total_ves == 30350.0
        assert nominas[0].tasa_eur_ves == 100.0
        assert nominas[0].estado == "calculada"
        assert nominas[0].botellones_repartidos == 50

    async def test_calcular_tasa_no_disponible(self):
        """When tasa is None, should use 0 and still calculate."""
        with (
            patch("src.financial.nomina.get_eur_ves_rate", AsyncMock(return_value=None)),
            patch("src.financial.nomina._contar_botellones_repartidos", return_value=0),
        ):
            nominas = await calcular_nomina_periodo(
                "2026-08-01", "2026-08-15", [_make_empleado()]
            )
        assert len(nominas) == 1
        assert nominas[0].tasa_eur_ves == 0
        assert nominas[0].total_ves == 0.0  # 300 * 0 = 0
        assert nominas[0].total_eur == 300.0  # sueldo + 0 comision

    async def test_calcular_sin_botellones(self):
        """Empleado sin botellones repartidos — solo sueldo fijo."""
        with (
            patch("src.financial.nomina.get_eur_ves_rate", AsyncMock(return_value=105.0)),
            patch("src.financial.nomina._contar_botellones_repartidos", return_value=0),
        ):
            nominas = await calcular_nomina_periodo(
                "2026-08-01", "2026-08-15", [_make_empleado()]
            )
        assert nominas[0].comision_total_eur == 0.0
        assert nominas[0].total_eur == 300.0
        assert nominas[0].total_ves == 31500.0  # 300 * 105

    async def test_calcular_empleados_none_uses_db(self):
        """When empleados=None, should call db.get_all_empleados()."""
        mock_empleados = [_make_empleado()]
        with (
            patch("src.financial.nomina.db.get_all_empleados", return_value=mock_empleados),
            patch("src.financial.nomina.get_eur_ves_rate", AsyncMock(return_value=100.0)),
            patch("src.financial.nomina._contar_botellones_repartidos", return_value=10),
        ):
            nominas = await calcular_nomina_periodo("2026-08-01", "2026-08-15")
        assert len(nominas) == 1
        assert nominas[0].empleado_nombre == "Pedro Pérez"

    async def test_calcular_lista_vacia(self):
        with patch("src.financial.nomina.get_eur_ves_rate", AsyncMock(return_value=100.0)):
            nominas = await calcular_nomina_periodo(
                "2026-08-01", "2026-08-15", empleados=[]
            )
        assert nominas == []

    async def test_calcular_multiples_empleados_diferentes_botellones(self):
        """Test that each empleado gets correct botellones count."""
        empleados = [
            _make_empleado(id=1, nombre="Pedro"),
            _make_empleado(id=2, nombre="Ana"),
            _make_empleado(id=3, nombre="Luis"),
        ]
        botellones_map = {1: 100, 2: 0, 3: 200}
        with (
            patch("src.financial.nomina.get_eur_ves_rate", AsyncMock(return_value=100.0)),
            patch(
                "src.financial.nomina._contar_botellones_repartidos",
                side_effect=lambda eid, fi, ff: botellones_map.get(eid, 0),
            ),
        ):
            nominas = await calcular_nomina_periodo("2026-08-01", "2026-08-15", empleados)

        assert len(nominas) == 3
        assert nominas[0].botellones_repartidos == 100
        assert nominas[0].comision_total_eur == 7.0  # 100 * 0.07
        assert nominas[1].botellones_repartidos == 0
        assert nominas[1].comision_total_eur == 0.0
        assert nominas[2].botellones_repartidos == 200
        assert nominas[2].comision_total_eur == 14.0  # 200 * 0.07


# ---------------------------------------------------------------------------
# _contar_botellones_repartidos
# ---------------------------------------------------------------------------

class TestContarBotellones:
    def test_contar_con_error_bd(self):
        """When get_db raises, should return 0."""
        with patch("src.financial.nomina.get_db", side_effect=Exception("DB error")):
            result = _contar_botellones_repartidos(1, "2026-08-01", "2026-08-15")
        assert result == 0

    def test_contar_sin_resultados(self):
        """When query returns no rows, should return 0."""
        mock_conn = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = MagicMock(return_value=None)
        mock_conn.execute.return_value.fetchone.return_value = mock_row
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_conn)
        mock_cm.__exit__ = MagicMock(return_value=None)

        with patch("src.financial.nomina.get_db", return_value=mock_cm):
            result = _contar_botellones_repartidos(999, "2026-08-01", "2026-08-15")
        assert result == 0


# ---------------------------------------------------------------------------
# guardar_nomina
# ---------------------------------------------------------------------------

class TestGuardarNomina:
    def test_guardar_nomina_calls_db(self):
        nom = Nomina(
            empleado_id=1,
            empleado_nombre="Pedro",
            fecha_inicio="2026-08-01",
            fecha_fin="2026-08-15",
            botellones_repartidos=50,
            sueldo_fijo_eur=300.0,
            comision_total_eur=3.5,
            total_eur=303.5,
            total_ves=30350.0,
            tasa_eur_ves=100.0,
            estado="calculada",
        )
        with patch("src.financial.nomina.db.create_nomina", return_value=42) as mock_create:
            result = guardar_nomina(nom)
        assert result == 42
        mock_create.assert_called_once_with(nom)


# ---------------------------------------------------------------------------
# generar_reporte_nomina
# ---------------------------------------------------------------------------

class TestGenerarReporteNomina:
    async def test_reporte_con_empleados(self):
        nominas = [
            Nomina(
                empleado_id=1,
                empleado_nombre="Pedro",
                fecha_inicio="2026-08-01",
                fecha_fin="2026-08-15",
                botellones_repartidos=50,
                sueldo_fijo_eur=300.0,
                comision_total_eur=3.5,
                total_eur=303.5,
                total_ves=30350.0,
                tasa_eur_ves=100.0,
                estado="calculada",
            ),
        ]
        with (
            patch(
                "src.financial.nomina.calcular_nomina_periodo",
                AsyncMock(return_value=nominas),
            ),
            patch("src.financial.nomina.get_tasa_display", return_value="€1 = Bs. 100.00"),
        ):
            result = await generar_reporte_nomina("2026-08-01", "2026-08-15")

        assert "Nómina" in result
        assert "Pedro" in result
        assert "303.50" in result
        assert "100.00" in result

    async def test_reporte_sin_empleados(self):
        with patch(
            "src.financial.nomina.calcular_nomina_periodo",
            AsyncMock(return_value=[]),
        ):
            result = await generar_reporte_nomina("2026-08-01", "2026-08-15")
        assert "No hay empleados" in result
