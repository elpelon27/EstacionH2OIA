"""R4 Banco - Verificador de pagos: conecta webhook R4notifica → Financial Shield v3.0"""
import logging
import re
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, timedelta

from src.financial import database as db
from src.financial import verificacion
from src.financial.models import PedidoFinanciero
from api.banking_webhooks import R4NotificaRequest

logger = logging.getLogger("r4banco.verificador")

CARACAS_TZ = timezone(timedelta(hours=-4))


def normalizar_telefono_venezuela(telefono: str) -> str:
    """
    Normaliza teléfono venezolano para búsqueda en BD.
    Elimina prefijos V/E, +58, 00, etc. Deja solo los 10 dígitos.
    """
    # Quitar todo lo que no sea dígito
    digitos = re.sub(r"\D", "", telefono)
    
    # Si empieza con 58 (código país), quitarlo
    if digitos.startswith("58"):
        digitos = digitos[2:]
    
    # Si empieza con 0, quitarlo
    if digitos.startswith("0"):
        digitos = digitos[1:]
    
    # Debe quedar 10 dígitos
    if len(digitos) == 10:
        return digitos
    
    return telefono  # fallback


def buscar_pedidos_por_telefono_monto(
    telefono_emisor: str,
    monto_str: str,
    estados_permitidos: Optional[List[str]] = None,
) -> List[PedidoFinanciero]:
    """
    Busca fs_pedidos que coincidan con teléfono y monto aproximado.
    
    Args:
        telefono_emisor: Teléfono del pagador (normalizado a 10 dígitos)
        monto_str: Monto como string (ej: "123.45")
        estados_permitidos: Lista de estados_pago válidos
    
    Returns:
        Lista de PedidoFinanciero ordenados por fecha (más reciente primero)
    """
    if estados_permitidos is None:
        estados_permitidos = ["pendiente", "verificando", "parcial", "vencido"]
    
    try:
        monto_objetivo = float(monto_str)
    except (ValueError, TypeError):
        logger.warning("Monto inválido para búsqueda: %s", monto_str)
        return []
    
    # Rango de tolerancia ±1% (ajustable)
    tolerancia = max(0.01, monto_objetivo * 0.01)
    monto_min = monto_objetivo - tolerancia
    monto_max = monto_objetivo + tolerancia
    
    telefono_norm = normalizar_telefono_venezuela(telefono_emisor)
    
    with db.get_db() as conn:
        # Buscar por teléfono (LIKE en últimos 10 dígitos) + monto + estado
        placeholders = ",".join(["?"] * len(estados_permitidos))
        query = f"""
            SELECT * FROM fs_pedidos
            WHERE 
                (cliente_telefono LIKE ? OR cliente_telefono LIKE ? OR cliente_telefono LIKE ?)
                AND monto_total_eur BETWEEN ? AND ?
                AND estado_pago IN ({placeholders})
            ORDER BY creado_at DESC
        """
        
        # Variaciones de teléfono: +58XXXXXXXXXX, 0XXXXXXXXXX, XXXXXXXXXX
        tel_vars = [
            f"%{telefono_norm}%",
            f"+58{telefono_norm}%",
            f"0{telefono_norm}%",
        ]
        
        params = tel_vars + [monto_min, monto_max] + estados_permitidos
        rows = conn.execute(query, params).fetchall()
        
    pedidos = []
    for row in rows:
        pedido = PedidoFinanciero(**dict(row))
        pedidos.append(pedido)
    
    logger.info(
        "Búsqueda R4: telefono=%s monto=€%.2f±%.2f → %d matches",
        telefono_emisor, monto_objetivo, tolerancia, len(pedidos)
    )
    return pedidos


def seleccionar_mejor_match(pedidos: List[PedidoFinanciero], telefono_emisor: str, monto: float) -> Optional[PedidoFinanciero]:
    """
    Selecciona el mejor match entre candidatos.
    Criterios: 1) teléfono exacto, 2) monto exacto, 3) más reciente.
    """
    if not pedidos:
        return None
    
    if len(pedidos) == 1:
        return pedidos[0]
    
    telefono_norm = normalizar_telefono_venezuela(telefono_emisor)
    
    # Scorear cada pedido
    scored = []
    for p in pedidos:
        score = 0
        p_tel_norm = normalizar_telefono_venezuela(p.cliente_telefono or "")
        
        # Teléfono exacto (últimos 10 dígitos)
        if p_tel_norm == telefono_norm:
            score += 100
        elif telefono_norm in p_tel_norm or p_tel_norm in telefono_norm:
            score += 50
        
        # Monto exacto (dentro de centavos)
        if abs(p.monto_total_eur - monto) < 0.01:
            score += 50
        elif abs(p.monto_total_eur - monto) < 1.0:
            score += 20
        
        # Más reciente
        score += 10  # base
        
        scored.append((score, p))
    
    # Ordenar por score descendente
    scored.sort(key=lambda x: x[0], reverse=True)
    
    logger.info(
        "Match scoring: top=%s (score=%.0f) vs alternatives=%d",
        scored[0][1].id, scored[0][0], len(scored) - 1
    )
    
    return scored[0][1]


async def procesar_notifica_pago_movil(payload: R4NotificaRequest) -> Dict[str, Any]:
    """
    Procesa notificación de pago móvil entrante (R4notifica).
    
    Flujo:
    1. Validar CodigoRed == "00" (aprobado por red interbancaria)
    2. Normalizar teléfono emisor
    3. Buscar fs_pedidos match (teléfono + monto + estado)
    4. Si match único → llamar Financial Shield verificar_pago_manual()
    5. Registrar en fs_audit_log (origen: 'banco_r4')
    6. Retornar {"abono": true/false} para el banco
    
    Args:
        payload: Request validado del webhook R4notifica
    
    Returns:
        {"abono": true} si procesado y verificado, {"abono": false} en caso contrario
    """
    logger.info(
        "R4notifica recibido: comercio=%s emisor=%s monto=%s ref=%s banco=%s red=%s",
        payload.IdComercio, payload.TelefonoEmisor, payload.Monto,
        payload.Referencia, payload.BancoEmisor, payload.CodigoRed
    )
    
    # 1. Verificar código de red interbancaria
    if payload.CodigoRed != "00":
        logger.warning(
            "R4notifica: CodigoRed != 00 (%s) → rechazado automáticamente",
            payload.CodigoRed
        )
        return {"abono": False}
    
    # 2. Buscar pedidos candidatos
    pedidos = buscar_pedidos_por_telefono_monto(
        telefono_emisor=payload.TelefonoEmisor,
        monto_str=payload.Monto,
    )
    
    if not pedidos:
        logger.info(
            "R4notifica: Sin pedidos match para telefono=%s monto=%s",
            payload.TelefonoEmisor, payload.Monto
        )
        return {"abono": False}
    
    # 3. Seleccionar mejor match
    pedido = seleccionar_mejor_match(pedidos, payload.TelefonoEmisor, float(payload.Monto))
    
    if not pedido:
        logger.warning("R4notifica: No se pudo seleccionar match único")
        return {"abono": False}
    
    # 4. Verificar que no esté ya pagado completamente
    if pedido.estado_pago == "pagado" and pedido.monto_pagado_eur >= pedido.monto_total_eur - 0.01:
        logger.info("R4notifica: Pedido %d ya está pagado", pedido.id)
        return {"abono": True}  # ACK al banco aunque ya esté pagado
    
    # 5. Llamar Financial Shield - verificación atómica
        try:
            fs_pedido_id = pedido.id
            if fs_pedido_id is None:
                logger.error("Pedido sin ID válido")
                return {"abono": False}

            logger.info("Match pedido fs_id=%d cliente=%s monto=%.2f", fs_pedido_id, pedido.cliente_nombre, monto)

            resultado = await verificacion.verificar_pago_manual(
                fs_pedido_id=fs_pedido_id,
                monto_eur=float(payload.Monto),
                metodo_pago="pagomovil",
                referencia=payload.Referencia,
                verificado_por="banco_r4",
            )

            if resultado.get("verified"):
                logger.info(
                    "R4notifica: Pago VERIFICADO ✅ pedido=%s monto=€%.2f ref=%s",
                    pedido.id, float(payload.Monto), payload.Referencia
                )

                # Registrar en audit log origen banco
                with db.get_db() as conn:
                    conn.execute("""
                        INSERT INTO fs_audit_log (tabla, registro_id, accion, estado_nuevo, modificado_por, timestamp)
                        VALUES ('fs_pedidos', ?, 'PAGO_BANCO_R4',
                                json_object('estado_pago', 'pagado', 'monto_pagado_eur', ?, 'referencia_banco', ?),
                                'banco_r4', datetime('now'))
                    """, (pedido.id, float(payload.Monto), payload.Referencia))

                return {"abono": True}
            else:
                logger.warning(
                    "R4notifica: Financial Shield NO verificó pago pedido=%s: %s",
                    pedido.id, resultado.get("mensaje", "sin mensaje")
                )
                return {"abono": False}

        except Exception as e:
            logger.error("R4notifica: Error procesando verificación: %s", e, exc_info=True)
            return {"abono": False}


async def procesar_consulta_cliente(payload: Any) -> Dict[str, Any]:
    """
    Procesa R4consulta / MBconsulta - validar si cliente existe para aceptar pago.
    
    El banco nos consulta ANTES de procesar el pago móvil.
    Respondemos {"status": true} si cliente válido, {"status": false} para reversar.
    """
    # Extraer IdCliente (puede venir como IdCliente o IdComercio)
    id_cliente = getattr(payload, "IdCliente", None) or getattr(payload, "IdComercio", None)
    
    if not id_cliente:
        logger.warning("R4consulta: Sin IdCliente/IdComercio")
        return {"status": False}
    
    # Normalizar a 8 dígitos
    id_norm = re.sub(r"\D", "", id_cliente)
    if len(id_norm) != 8:
        logger.warning("R4consulta: IdCliente inválido: %s", id_cliente)
        return {"status": False}
    
    # Buscar en fs_pedidos o tabla de clientes si existe
    with db.get_db() as conn:
        # Verificar si hay pedidos activos para este cliente
        row = conn.execute("""
            SELECT COUNT(*) as cnt FROM fs_pedidos
            WHERE cliente_telefono LIKE ? AND estado_pago IN ('pendiente', 'verificando', 'parcial')
        """, (f"%{id_norm}%",)).fetchone()
        
        if row and row["cnt"] > 0:
            logger.info("R4consulta: Cliente %s ACEPTADO (tiene pedidos pendientes)", id_norm)
            return {"status": True}
        
        # También verificar en clientes del dispatcher si existe
        row2 = conn.execute("""
            SELECT 1 FROM clients WHERE phone_hash LIKE ?
        """, (f"%{id_norm}%",)).fetchone()
        
        if row2:
            logger.info("R4consulta: Cliente %s ACEPTADO (existe en clients)", id_norm)
            return {"status": True}
    
    logger.info("R4consulta: Cliente %s RECHAZADO (no encontrado)", id_norm)
    return {"status": False}


# ============================================================================
# FUNCIONES DE TESTING / SIMULACIÓN
# ============================================================================

def crear_payload_test_notifica(
    telefono_emisor: str = "04141234567",
    monto: str = "10.00",
    referencia: str = "TEST123456",
    banco_emisor: str = "0134",
    codigo_red: str = "00",
) -> Dict[str, Any]:
    """Crea payload de prueba para R4notifica"""
    return {
        "IdComercio": "12345678",
        "TelefonoComercio": "04129999999",
        "TelefonoEmisor": telefono_emisor,
        "Concepto": "PAGO PEDIDO H2O",
        "BancoEmisor": banco_emisor,
        "Monto": monto,
        "FechaHora": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "Referencia": referencia,
        "CodigoRed": codigo_red,
    }


async def test_flujo_completo():
    """Test E2E simulando webhook → verificación"""
    print("🧪 Test R4 Banco: Flujo completo simulado")
    
    # 1. Crear pedido de prueba en BD
    from src.financial.database import create_pedido_financiero
    from src.financial.models import PedidoFinanciero
    
    pedido_test = PedidoFinanciero(
        pedido_id=999999,
        cliente_telefono="04141234567",
        cliente_nombre="CLIENTE TEST",
        monto_total_eur=10.00,
        monto_total_ves=8447.50,
        tasa_eur_ves=844.75,
        tasa_eur_ves_deuda=844.75,
        botellones_cantidad=10,
        estado_pago="pendiente",
        estado_entrega="sin_entregar",
        metodo_pago="pagomovil",
    )
    
    fs_id = create_pedido_financiero(pedido_test)
    print(f"✅ Pedido test creado: fs_id={fs_id}")
    
    # 2. Simular webhook R4notifica
    payload = crear_payload_test_notifica(
        telefono_emisor="04141234567",
        monto="10.00",
        referencia="TEST123456",
    )
    
    from api.banking_webhooks import R4NotificaRequest
    r4_payload = R4NotificaRequest(**payload)
    
    # 3. Procesar
    resultado = await procesar_notifica_pago_movil(r4_payload)
    print(f"📥 Resultado webhook: {resultado}")
    
    # 4. Verificar en BD
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT estado_pago, monto_pagado_eur FROM fs_pedidos WHERE id = ?", (fs_id,)
        ).fetchone()
        print(f"📊 BD post-webhook: estado={row['estado_pago']} pagado=€{row['monto_pagado_eur']}")
    
    # 5. Limpiar
    with db.get_db() as conn:
        conn.execute("DELETE FROM fs_pedidos WHERE id = ?", (fs_id,))
        conn.execute("DELETE FROM fs_audit_log WHERE registro_id = ? AND tabla = 'fs_pedidos'", (fs_id,))
    
    print("✅ Test completado")


if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_flujo_completo())