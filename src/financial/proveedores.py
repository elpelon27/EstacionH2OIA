"""
 ============================================================================
 Financial Shield — Proveedores (pagos solo contado)
 Estación H2O · Maracaibo, Venezuela
 ============================================================================

Registro de egresos a proveedores. Solo contado, no hay crédito.
 """

import logging
from typing import List, Optional

from . import database as db
from .models import ProveedorPago
from .currency import get_eur_ves_rate, convert_eur_to_ves
import asyncio

logger = logging.getLogger("financial_shield.proveedores")


async def registrar_pago_proveedor(
    proveedor_id: int,
    proveedor_nombre: str,
    concepto: str,
    monto_eur: float,
    metodo_pago: str = "efectivo_eur",
    referencia: str = None,
    comprobante_url: str = None,
    creado_por: str = "manual",
) -> int:
    """
    Registra un pago a proveedor (solo contado).

    Returns: ID del registro creado.
    """
    tasa = await get_eur_ves_rate()
    monto_ves = convert_eur_to_ves(monto_eur, tasa) if tasa else None

    pago = ProveedorPago(
        proveedor_id=proveedor_id,
        proveedor_nombre=proveedor_nombre,
        concepto=concepto,
        monto_eur=monto_eur,
        monto_ves=monto_ves,
        metodo_pago=metodo_pago,
        referencia=referencia,
        tasa_eur_ves=tasa or 0,
        comprobante_url=comprobante_url,
        creado_por=creado_por,
    )

    pago_id = db.create_proveedor_pago(pago)
    logger.info(
        "Pago a proveedor registrado: %s — €%.2f (%s)",
        proveedor_nombre, monto_eur, concepto
    )
    return pago_id


def get_total_egresos_periodo(fecha_inicio: str, fecha_fin: str) -> dict:
    """Total de egresos a proveedores en un período."""
    from .database import get_db
    try:
        with get_db() as conn:
            row = conn.execute("""
                SELECT
                    COUNT(*) as num_pagos,
                    SUM(monto_eur) as total_eur,
                    SUM(monto_ves) as total_ves
                FROM fs_proveedor_pagos
                WHERE creado_at BETWEEN ? AND ?
            """, (fecha_inicio, fecha_fin + " 23:59:59")).fetchone()

            if row:
                return {
                    "num_pagos": row["num_pagos"] or 0,
                    "total_eur": round(row["total_eur"] or 0, 2),
                    "total_ves": round(row["total_ves"] or 0, 2),
                }
    except Exception as e:
        logger.error("Error consultando egresos: %s", e)

    return {"num_pagos": 0, "total_eur": 0.0, "total_ves": 0.0}
