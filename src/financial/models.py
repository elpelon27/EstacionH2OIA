"""
============================================================================
Financial Shield — Modelos de datos v3.0 (dataclasses)
Estación H2O · Maracaibo, Venezuela
============================================================================

Clases tipadas para todas las entidades financieras.
"""

from dataclasses import dataclass


@dataclass
class Producto:
    """Catálogo de productos con precios y volumen."""

    id: int
    nombre: str
    precio_base_eur: float
    precio_volumen_eur: float
    umbral_volumen: int
    tiene_comision: bool
    comision_eur: float
    activo: bool = True

    def precio_unitario(self, cantidad: int) -> float:
        """Calcula precio unitario según cantidad (descuento por volumen)."""
        if cantidad >= self.umbral_volumen:
            return self.precio_volumen_eur
        return self.precio_base_eur

    def total(self, cantidad: int) -> float:
        """Calcula total para una cantidad dada."""
        return round(self.precio_unitario(cantidad) * cantidad, 2)


@dataclass
class PedidoFinanciero:
    """Vista financiera de un pedido (1:1 con orders de Valentina)."""

    id: int | None = None
    pedido_id: int = 0  # FK → orders.id (Valentina, solo lectura)
    cliente_telefono: str = ""
    cliente_nombre: str = ""
    operador_id: int | None = None
    monto_total_eur: float = 0.0
    monto_total_ves: float | None = None
    tasa_eur_ves: float = 0.0
    tasa_usd_ves_ref: float | None = None
    botellones_cantidad: int = 0
    hielo_cantidad: int = 0
    metodo_pago: str | None = None  # pagomovil | efectivo_eur | efectivo_ves
    estado_pago: str = "pendiente"  # pendiente|parcial|pagado|verificando|vencido|moroso
    estado_entrega: str = "sin_entregar"  # sin_entregar|entregado|confirmado
    tipo_credito: str | None = None  # None=contado | express|semanal|mensual
    fecha_vencimiento_credito: str | None = None
    verificacion_bancaria: str = "pending"  # pending|api|ocr|manual
    recordatorios_enviados: int = 0
    ultimo_recordatorio_at: str | None = None
    escalo_humano: bool = False
    entrega_confirmada_at: str | None = None
    creado_at: str = ""
    actualizado_at: str = ""
    # v3.0 campos nuevos
    monto_pagado_eur: float = 0.0
    tasa_eur_ves_deuda: float = 0.0


@dataclass
class Pago:
    """Pago recibido (historial completo)."""

    id: int | None = None
    fs_pedido_id: int | None = None
    cuenta_cobrar_id: int | None = None
    cliente_telefono: str = ""
    cliente_nombre: str = ""
    monto_eur: float = 0.0
    monto_ves: float | None = None
    metodo_pago: str = ""  # pagomovil | efectivo_eur | efectivo_ves
    referencia: str | None = None  # Anti-fraude (solo pagomovil)
    tasa_eur_ves: float = 0.0
    verificacion_metodo: str = "pending"  # pending|api_bancaria|ocr|manual
    verificado: bool = False
    verificado_at: str | None = None
    verificado_por: str | None = None  # 'api_bancaria'|'ocr'|'manual'|'sistema'
    comprobante_url: str | None = None
    creado_at: str = ""
    # v3.0 campos nuevos
    tasa_eur_ves_pago: float = 0.0  # Tasa al segundo del pago (renombra tasa_eur_ves)
    comprobante_phash: str | None = None  # Perceptual hash anti-fraude


@dataclass
class CuentaCobrar:
    """Cuenta por cobrar (crédito activo)."""

    id: int | None = None
    cliente_telefono: str = ""
    cliente_nombre: str = ""
    fs_pedido_id: int = 0
    monto_original_eur: float = 0.0
    monto_pagado_eur: float = 0.0
    tipo_credito: str = ""  # express|semanal|mensual
    fecha_vencimiento: str = ""
    estado: str = "pendiente"  # pendiente|parcial|pagado|vencido|moroso
    recordatorios_enviados: int = 0
    ultimo_recordatorio_at: str | None = None
    escalo_humano: bool = False
    cerrado_at: str | None = None
    creado_at: str = ""
    actualizado_at: str = ""


@dataclass
class Empleado:
    """Empleado con sueldo y comisión."""

    id: int | None = None
    nombre: str = ""
    rol: str = "operador"  # operador|admin|otro
    telefono: str | None = None
    sueldo_fijo_eur: float = 0.0
    comision_botellon_eur: float = 0.07
    telegram_id: str | None = None
    activo: bool = True
    creado_at: str = ""


@dataclass
class Nomina:
    """Período de liquidación de nómina."""

    id: int | None = None
    empleado_id: int = 0
    empleado_nombre: str = ""
    fecha_inicio: str = ""
    fecha_fin: str = ""
    botellones_repartidos: int = 0
    sueldo_fijo_eur: float = 0.0
    comision_total_eur: float = 0.0
    total_eur: float = 0.0
    total_ves: float | None = None
    tasa_eur_ves: float | None = None
    estado: str = "pending"  # pending|calculada|pagada
    pagado_at: str | None = None
    creado_at: str = ""


@dataclass
class ProveedorPago:
    """Pago a proveedor (solo contado)."""

    id: int | None = None
    proveedor_id: int = 0
    proveedor_nombre: str = ""
    concepto: str = ""
    monto_eur: float = 0.0
    monto_ves: float | None = None
    metodo_pago: str | None = None
    referencia: str | None = None
    tasa_eur_ves: float = 0.0
    comprobante_url: str | None = None
    creado_at: str = ""
    creado_por: str | None = None


@dataclass
class TasaCambio:
    """Histórico de tasa de cambio (inmutable)."""

    id: int | None = None
    par: str = ""  # EUR/VES | USD/VES
    tasa: float = 0.0
    fuente: str = ""  # bcv|api_eur_ves|calculada|manual|open_er_api|frankfurter
    notas: str | None = None
    registrado_at: str = ""


@dataclass
class ReporteDiario:
    """Reporte diario enviado por Telegram."""

    id: int | None = None
    fecha: str = ""
    ventas_total_eur: float = 0.0
    cobros_total_eur: float = 0.0
    por_cobrar_eur: float = 0.0
    ventas_total_ves: float = 0.0
    cobros_total_ves: float = 0.0
    por_cobrar_ves: float = 0.0
    num_pedidos: int = 0
    num_pagados: int = 0
    num_pendientes: int = 0
    num_morosos: int = 0
    nomina_eur: float = 0.0
    generado_at: str = ""
    enviado_telegram: bool = False
    telegram_msg_id: str | None = None


@dataclass
class VerificacionLog:
    """Log de auditoría del loop de verificación."""

    id: int | None = None
    fs_pedido_id: int = 0
    intento: int = 0
    metodo_verificacion: str = ""  # api_bancaria|ocr|manual
    pago_encontrado: bool = False
    accion: str = ""  # recordatorio_enviado|escalo_humano|pagado
    resultado_detalle: str = ""
    timestamp: str = ""
