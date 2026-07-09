"""
 ============================================================================
 Financial Shield — Cobranzas (cuentas por cobrar + loop recordatorios)
 Estación H2O · Maracaibo, Venezuela
 ============================================================================

Gestiona:
- Créditos a clientes (express, semanal, mensual)
- Loop de recordatorios automáticos (3 máx, 1h entre cada uno)
- Escalamiento a humano tras 3 recordatorios fallidos
- Cálculo de fechas de vencimiento
 """

import logging
from typing import Optional
from datetime import datetime, timezone, timedelta

from . import database as db
from .models import PedidoFinanciero, CuentaCobrar

logger = logging.getLogger("financial_shield.cobranzas")

CARACAS_TZ = timezone(timedelta(hours=-4))

# Configuración
MAX_RECORDATORIOS = int(__import__("os").getenv("FS_MAX_RECORDATORIOS", "3"))
INTERVALO_MINUTOS = int(__import__("os").getenv("FS_INTERVALO_RECORDATORIO_MINUTOS", "60"))


def calcular_fecha_vencimiento(tipo_credito: str) -> str:
    """Calcula fecha de vencimiento según tipo de crédito."""
    now = datetime.now(CARACAS_TZ)
    if tipo_credito == "express":
        venc = now + timedelta(hours=24)
    elif tipo_credito == "semanal":
        venc = now + timedelta(days=7)
    elif tipo_credito == "mensual":
        venc = now + timedelta(days=30)
    else:
        venc = now  # Contado = vence ahora
    return venc.strftime("%Y-%m-%d %H:%M")


def crear_cuenta_cobrar(pedido: PedidoFinanciero, tipo_credito: str) -> int:
    """Crea cuenta por cobrar cuando se asigna crédito a un pedido."""
    cuenta = CuentaCobrar(
        cliente_telefono=pedido.cliente_telefono,
        cliente_nombre=pedido.cliente_nombre,
        fs_pedido_id=pedido.id,
        monto_original_eur=pedido.monto_total_eur,
        monto_pagado_eur=0.0,
        tipo_credito=tipo_credito,
        fecha_vencimiento=calcular_fecha_vencimiento(tipo_credito),
        estado="pendiente",
    )
    cuenta_id = db.create_cuenta_cobrar(cuenta)
    logger.info(
        "Cuenta por cobrar creada: cliente=%s monto=€%.2f vence=%s",
        pedido.cliente_nombre, pedido.monto_total_eur, cuenta.fecha_vencimiento
    )
    return cuenta_id


def get_pedidos_para_recordatorio() -> list[PedidoFinanciero]:
    """
    Obtiene pedidos que necesitan recordatorio:
    - Entregados pero sin pago
    - No escalados a humano
    - Menos de 3 recordatorios enviados
    - Ha pasado al menos 1h desde el último recordatorio
    """
    pedidos = db.get_pedidos_pendientes_pago()
    result = []
    now = datetime.now(CARACAS_TZ)

    for p in pedidos:
        # Verificar si ha pasado suficiente tiempo desde último recordatorio
        if p.ultimo_recordatorio_at:
            try:
                ultimo = datetime.fromisoformat(p.ultimo_recordatorio_at)
                if (now - ultimo).total_seconds() < INTERVALO_MINUTOS * 60:
                    continue  # Aún no es hora del siguiente recordatorio
            except (ValueError, TypeError):
                pass  # Si no se puede parsear, enviar recordatorio

        result.append(p)

    return result


def procesar_recordatorio(pedido: PedidoFinanciero) -> dict:
    """
    Procesa un recordatorio para un pedido.
    Returns: dict con 'accion' y 'mensaje' para que Valentina envíe.
    """
    intento = pedido.recordatorios_enviados + 1

    if intento > MAX_RECORDATORIOS:
        # Escalar a humano
        db.marcar_escalo_humano(pedido.id)
        db.log_verificacion(
            pedido.id, intento, "manual",
            False, "escalo_humano",
            f"3 recordatorios fallidos — escalado a humano"
        )
        return {
            "accion": "escalar_humano",
            "mensaje": (
                f"🚨 ESCALAMIENTO HUMANO\n\n"
                f"Cliente: {pedido.cliente_nombre} ({pedido.cliente_telefono})\n"
                f"Pedido #{pedido.pedido_id}\n"
                f"Monto: €{pedido.monto_total_eur:.2f}\n"
                f"Recordatorios enviados: {MAX_RECORDATORIOS}\n"
                f"Estado: SIN PAGO tras 3 intentos"
            ),
            "mensaje_cliente": None,  # No se envía al cliente
        }

    # Enviar recordatorio
    db.incrementar_recordatorio(pedido.id)
    db.log_verificacion(
        pedido.id, intento, "manual",
        False, "recordatorio_enviado",
        f"Recordatorio #{intento} enviado"
    )

    mensaje_cliente = (
        f"Estimado cliente, le recordamos que tiene un pedido pendiente de pago "
        f"por €{pedido.monto_total_eur:.2f}. "
        f"Por favor, envíe su comprobante de pago. ¡Gracias! 💧"
    )

    return {
        "accion": "recordatorio_enviado",
        "mensaje": f"Recordatorio #{intenido}/{MAX_RECORDATORIOS} enviado a {pedido.cliente_nombre}",
        "mensaje_cliente": mensaje_cliente,
        "intento": intento,
    }


def get_resumen_cobranzas() -> dict:
    """Resumen de cuentas por cobrar para reporte."""
    activas = db.get_cuentas_cobrar_activas()
    vencidas = db.get_cuentas_vencidas()

    total_activas = sum(c.monto_original_eur - c.monto_pagado_eur for c in activas)
    total_vencidas = sum(c.monto_original_eur - c.monto_pagado_eur for c in vencidas)

    return {
        "num_activas": len(activas),
        "num_vencidas": len(vencidas),
        "total_activas_eur": round(total_activas, 2),
        "total_vencidas_eur": round(total_vencidas, 2),
        "cuentas": [
            {
                "cliente": c.cliente_nombre,
                "telefono": c.cliente_telefono,
                "monto": c.monto_original_eur - c.monto_pagado_eur,
                "vencimiento": c.fecha_vencimiento,
                "tipo": c.tipo_credito,
                "estado": c.estado,
            }
            for c in vencidas[:10]  # Top 10 vencidas
        ],
    }
