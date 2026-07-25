"""
 ============================================================================
 Financial Shield — Agente Principal (orquestador del módulo)
 Estación H2O · Maracaibo, Venezuela
 ============================================================================

Este agente es el ÚNICO autorizado para verificar, registrar y cerrar
transacciones financieras. Ningún otro agente (Valentina, Dispatcher) puede
confirmar pagos o modificar registros financieros.

Responsabilidades:
1. Crear registros financieros cuando Valentina confirma pedido
2. Verificar pagos (manual / OCR / API bancaria)
3. Gestionar créditos y cuentas por cobrar
4. Enviar recordatorios a través de Valentina
5. Generar reporte diario 6:30 PM
6. Calcular nómina

Integración:
- Valentina → FS: nuevo pedido confirmado
- FS → Valentina: recordatorio de pago para cliente
- FS → Telegram: alertas + reportes al Líder
- Dispatcher → FS: entrega confirmada (trigger loop verificación)
 """

import os
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

# Configurar path para imports
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from financial import database as db
from financial import currency, cobranzas, nomina, proveedores, verificacion, reportes
from financial.models import Producto, PedidoFinanciero, Pago

logger = logging.getLogger("financial_shield.agent")

CARACAS_TZ = timezone(timedelta(hours=-4))


class FinancialShieldAgent:
    """Agente financiero — ÚNICO que maneja transacciones financieras."""

    def __init__(self):
        self.initialized = False

    def init(self):
        """Inicializa BD y configuración."""
        db.init_database()
        self.initialized = True
        logger.info("Financial Shield Agent inicializado — 10 tablas fs_* listas")

    # ========================================================================
    # 1. NUEVO PEDIDO (llamado por Valentina/Bridge)
    # ========================================================================

    async def on_nuevo_pedido(
        self,
        pedido_id: int,
        cliente_telefono: str,
        cliente_nombre: str,
        qty_botellones: int,
        qty_hielo: int,
        metodo_pago: str,
        total_eur: float,
    ) -> int:
        """
        Called when Valentina confirms a new order.
        Creates financial record with correct pricing (including volume discounts).

        Returns: fs_pedido_id
        """
        if not self.initialized:
            self.init()

        # Calcular total CON descuento por volumen
        producto_bot = db.get_producto_by_nombre("Botellón")
        producto_hielo = db.get_producto_by_nombre("Hielo")

        total_calculado = 0.0
        if producto_bot and qty_botellones > 0:
            total_calculado += producto_bot.total(qty_botellones)
        else:
            total_calculado += qty_botellones * 1.00

        if producto_hielo and qty_hielo > 0:
            total_calculado += producto_hielo.total(qty_hielo)
        else:
            total_calculado += qty_hielo * 1.20

        total_calculado = round(total_calculado, 2)

        # Si el total del bridge difiere (no aplicó volumen), usar el del FS
        if abs(total_calculado - total_eur) > 0.01:
            logger.warning(
                "Total difiere: bridge=€%.2f fs=€%.2f (volumen aplicado)",
                total_eur, total_calculado
            )
            total_eur = total_calculado

        # Obtener tasa
        tasa = await currency.get_eur_ves_rate()
        monto_ves = currency.convert_eur_to_ves(total_eur, tasa) if tasa else None

        # Crear pedido financiero
        pedido_fin = PedidoFinanciero(
            pedido_id=pedido_id,
            cliente_telefono=cliente_telefono,
            cliente_nombre=cliente_nombre,
            monto_total_eur=total_eur,
            monto_total_ves=monto_ves,
            tasa_eur_ves=tasa or 0,
            botellones_cantidad=qty_botellones,
            hielo_cantidad=qty_hielo,
            metodo_pago=metodo_pago,
            estado_pago="pendiente",
            estado_entrega="sin_entregar",
        )

        fs_id = db.create_pedido_financiero(pedido_fin)
        logger.info(
            "Pedido financiero creado: fs_id=%d pedido=%d cliente=%s total=€%.2f",
            fs_id, pedido_id, cliente_nombre, total_eur
        )

        return fs_id

    # ========================================================================
    # 2. VERIFICACIÓN DE PAGO
    # ========================================================================

    async def on_pago_reclamado(
        self,
        fs_pedido_id: int,
        monto_eur: float,
        metodo_pago: str,
        referencia: str = None,
        comprobante_image_url: str = None,
        meta_token: str = None,
    ) -> dict:
        """
        Called when customer claims "ya pagué".
        Verifies payment using best available method.

        Returns: dict with 'verified', 'mensaje', 'needs_manual'
        """
        if not self.initialized:
            self.init()

        # Método 1: OCR (si está habilitado y hay imagen)
        if comprobante_image_url and os.getenv("FS_OCR_ENABLED", "false").lower() == "true":
            result = await verificacion.verificar_pago_ocr(
                fs_pedido_id, comprobante_image_url, monto_eur, meta_token
            )
            if result.get("success"):
                return result
            # Si OCR falla, continuar a manual

        # Método 2: API bancaria (si hay referencia/código)
        if referencia and os.getenv("FS_BANK_VERIFICATION_METHOD") == "api":
            result = await verificacion.verificar_pago_api_bancaria(
                fs_pedido_id, referencia, monto_eur
            )
            if result.get("success"):
                return result

        # Método 3: Manual (default)
        result = await verificacion.verificar_pago_manual(
            fs_pedido_id=fs_pedido_id,
            monto_eur=monto_eur,
            metodo_pago=metodo_pago,
            referencia=referencia,
        )

        return result

    async def confirmar_pago_manual(
        self,
        fs_pedido_id: int,
        monto_eur: float,
        metodo_pago: str,
        referencia: str = None,
    ) -> dict:
        """Líder confirma pago via Telegram /pagado."""
        return await verificacion.verificar_pago_manual(
            fs_pedido_id, monto_eur, metodo_pago, referencia, "telegram_lider"
        )

    # ========================================================================
    # 3. ENTREGA CONFIRMADA (trigger loop verificación)
    # ========================================================================

    def on_entrega_confirmada(self, fs_pedido_id: int, operador_id: int = None):
        """
        Called when dispatcher confirms delivery.
        Triggers payment verification loop.
        """
        db.confirmar_entrega(fs_pedido_id, operador_id)
        logger.info("Entrega confirmada: fs_pedido=%s — iniciando loop verificación", fs_pedido_id)

    # ========================================================================
    # 4. LOOP DE RECORDATORIOS
    # ========================================================================

    async def procesar_recordatorios_pendientes(self) -> list[dict]:
        """
        Procesa todos los pedidos que necesitan recordatorio.
        Returns: lista de dicts con 'phone', 'mensaje', 'accion'
        """
        if not self.initialized:
            self.init()

        pedidos = cobranzas.get_pedidos_para_recordatorio()
        resultados = []

        for pedido in pedidos:
            result = cobranzas.procesar_recordatorio(pedido)

            if result["accion"] == "recordatorio_enviado" and result.get("mensaje_cliente"):
                # FS → Valentina: enviar recordatorio al cliente
                resultados.append({
                    "phone": pedido.cliente_telefono,
                    "mensaje": result["mensaje_cliente"],
                    "accion": "enviar_recordatorio",
                    "fs_pedido_id": pedido.id,
                    "intento": result.get("intento", 0),
                })
            elif result["accion"] == "escalar_humano":
                # FS → Telegram: alertar al Líder
                resultados.append({
                    "accion": "alertar_humano",
                    "mensaje": result["mensaje"],
                    "fs_pedido_id": pedido.id,
                })

        return resultados

    # ========================================================================
    # 5. CRÉDITOS
    # ========================================================================

    def asignar_credito(self, fs_pedido_id: int, tipo_credito: str) -> int:
        """
        Asigna crédito a un pedido.
        tipo_credito: 'express' | 'semanal' | 'mensual'
        """
        pedido = db.get_pedido_financiero_by_pedido_id(fs_pedido_id)
        if not pedido:
            # Buscar por fs_pedido_id directamente
            from .database import get_db
            with get_db() as conn:
                row = conn.execute(
                    "SELECT * FROM fs_pedidos WHERE id = ?", (fs_pedido_id,)
                ).fetchone()
                if row:
                    pedido = PedidoFinanciero(**dict(row))

        if not pedido:
            logger.error("Pedido no encontrado para crédito: %s", fs_pedido_id)
            return -1

        cuenta_id = cobranzas.crear_cuenta_cobrar(pedido, tipo_credito)

        # Actualizar pedido con tipo de crédito
        from .database import get_db
        now = datetime.now(CARACAS_TZ).isoformat()
        venc = cobranzas.calcular_fecha_vencimiento(tipo_credito)
        with get_db() as conn:
            conn.execute("""
                UPDATE fs_pedidos
                SET tipo_credito = ?, fecha_vencimiento_credito = ?, actualizado_at = ?
                WHERE id = ?
            """, (tipo_credito, venc, now, fs_pedido_id))

        logger.info("Crédito %s asignado a pedido %s", tipo_credito, fs_pedido_id)
        return cuenta_id

    # ========================================================================
    # 6. REPORTE DIARIO
    # ========================================================================

    async def generar_y_enviar_reporte(self):
        """Genera y envía reporte diario por Telegram (6:30 PM)."""
        return await reportes.generar_y_enviar_reporte()

    # ========================================================================
    # 7. NÓMINA
    # ========================================================================

    async def calcular_nomina(self, fecha_inicio: str, fecha_fin: str) -> str:
        """Calcula nómina y retorna reporte para Telegram."""
        return await nomina.generar_reporte_nomina(fecha_inicio, fecha_fin)

    # ========================================================================
    # 8. PROVEEDORES
    # ========================================================================

    async def registrar_pago_proveedor(
        self, proveedor_nombre: str, concepto: str,
        monto_eur: float, metodo_pago: str = "efectivo_eur",
        referencia: str = None,
    ) -> int:
        """Registra pago a proveedor (solo contado)."""
        return await proveedores.registrar_pago_proveedor(
            proveedor_id=0,  # ID auto-generado o asignado
            proveedor_nombre=proveedor_nombre,
            concepto=concepto,
            monto_eur=monto_eur,
            metodo_pago=metodo_pago,
            referencia=referencia,
        )

    # ========================================================================
    # 9. UTILIDADES
    # ========================================================================

    def get_tasa_actual(self) -> str:
        """Retorna string con tasa actual."""
        return currency.get_tasa_display()

    def set_tasa_manual(self, tasa: float):
        """Líder setea tasa manual via Telegram."""
        return currency.set_manual_rate(tasa)

    def get_resumen_cobranzas(self) -> dict:
        """Resumen de cuentas por cobrar."""
        return cobranzas.get_resumen_cobranzas()


# ============================================================================
# Singleton
# ============================================================================

_agent_instance: Optional[FinancialShieldAgent] = None


def get_agent() -> FinancialShieldAgent:
    """Retorna instancia singleton del agente."""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = FinancialShieldAgent()
    return _agent_instance


# ============================================================================
# Punto de entrada (para cron / systemd)
# ============================================================================

async def main():
    """Ejecuta tareas programadas del FS (loop recordatorios + reporte)."""
    agent = get_agent()
    agent.init()

    # Procesar recordatorios pendientes
    resultados = await agent.procesar_recordatorios_pendientes()
    for r in resultados:
        logger.info("Resultado recordatorio: %s", r)

    # Si es 6:30 PM, generar reporte
    now = datetime.now(CARACAS_TZ)
    if now.hour == 18 and now.minute >= 30:
        await agent.generar_y_enviar_reporte()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
