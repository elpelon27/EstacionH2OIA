"""
 ============================================================================
 Financial Shield — Nómina (cálculo sueldos + comisiones)
 Estación H2O · Maracaibo, Venezuela
 ============================================================================

Estructura: Sueldo fijo (€) + Comisión (€0.07 × botellones repartidos)
Comisión SOLO botellones, NO hielo.
 """

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, List

from . import database as db
from .models import Empleado, Nomina
from .currency import get_tasa_display, convert_eur_to_ves, get_eur_ves_rate
import asyncio

logger = logging.getLogger("financial_shield.nomina")

CARACAS_TZ = timezone(timedelta(hours=-4))


async def calcular_nomina_periodo(
    fecha_inicio: str,
    fecha_fin: str,
    empleados: List[Empleado] | None = None,
) -> List[Nomina]:
    """
    Calcula nómina para un período dado.

    Args:
        fecha_inicio: ISO format (ej: "2026-07-01")
        fecha_fin: ISO format (ej: "2026-07-15")
        empleados: lista de empleados (si None, usa todos los activos)

    Returns: lista de Nomina calculadas (no guardadas en BD)
    """
    if empleados is None:
        empleados = db.get_all_empleados()

    # Obtener tasa actual
    tasa = await get_eur_ves_rate()
    if not tasa:
        logger.warning("No se pudo obtener tasa para nómina, usando 0")
        tasa = 0

    nominas = []

    for emp in empleados:
        # Contar botellones repartidos en el período
        # (Consulta a fs_pedidos donde operador_id = emp.id y fecha en rango)
        botellones = _contar_botellones_repartidos(int(emp.id) if emp.id else 0, fecha_inicio, fecha_fin)

        comision = round(botellones * emp.comision_botellon_eur, 2)
        total_eur = round(emp.sueldo_fijo_eur + comision, 2)
        total_ves = convert_eur_to_ves(total_eur, tasa)

        nom = Nomina(
            empleado_id=int(emp.id) if emp.id else 0,
            empleado_nombre=emp.nombre,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            botellones_repartidos=botellones,
            sueldo_fijo_eur=emp.sueldo_fijo_eur,
            comision_total_eur=comision,
            total_eur=total_eur,
            total_ves=total_ves,
            tasa_eur_ves=tasa,
            estado="calculada",
        )
        nominas.append(nom)
        logger.info(
            "Nómina calculada: %s — Sueldo €%.2f + Comisión €%.2f (%d botellones) = €%.2f",
            emp.nombre, emp.sueldo_fijo_eur, comision, botellones, total_eur
        )

    return nominas


def _contar_botellones_repartidos(empleado_id: int, fecha_inicio: str, fecha_fin: str) -> int:
    """Cuenta botellones repartidos por un empleado en un período."""
    from .database import get_db
    try:
        with get_db() as conn:
            row = conn.execute("""
                SELECT SUM(botellones_cantidad) as total
                FROM fs_pedidos
                WHERE operador_id = ?
                AND estado_entrega = 'confirmado'
                AND entrega_confirmada_at BETWEEN ? AND ?
            """, (empleado_id, fecha_inicio, fecha_fin + " 23:59:59")).fetchone()
            return row["total"] if row and row["total"] else 0
    except Exception as e:
        logger.error("Error contando botellones: %s", e)
        return 0


def guardar_nomina(nom: Nomina) -> int:
    """Guarda nómina calculada en BD."""
    return db.create_nomina(nom)


async def generar_reporte_nomina(fecha_inicio: str, fecha_fin: str) -> str:
    """Genera texto de reporte de nómina para Telegram."""
    nominas = await calcular_nomina_periodo(fecha_inicio, fecha_fin)

    if not nominas:
        return "📋 Nómina: No hay empleados activos."

    tasa_str = get_tasa_display()
    total_eur = sum(n.total_eur for n in nominas)
    total_ves = sum(n.total_ves or 0 for n in nominas)

    lineas = [
        f"📋 <b>Nómina {fecha_inicio} a {fecha_fin}</b>\n",
        f"Tasa: {tasa_str}\n",
    ]

    for n in nominas:
        lineas.append(
            f"👤 <b>{n.empleado_nombre}</b>\n"
            f"  Sueldo fijo: €{n.sueldo_fijo_eur:.2f}\n"
            f"  Botellones: {n.botellones_repartidos} × €0.07 = €{n.comision_total_eur:.2f}\n"
            f"  Total: €{n.total_eur:.2f} (Bs. {n.total_ves:.2f})\n"
        )

    lineas.append(f"\n💰 <b>Total nómina: €{total_eur:.2f} (Bs. {total_ves:.2f})</b>")

    return "\n".join(lineas)
