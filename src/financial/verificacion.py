"""
 ============================================================================
 Financial Shield — Verificación de pagos
 Estación H2O · Maracaibo, Venezuela
 ============================================================================

3 métodos de verificación:
1. API Bancaria (futuro) — cliente pega código de confirmación
2. OCR de comprobante — Qwen2.5-VL extrae referencia + monto
3. Manual — Líder confirma via Telegram /pagado

Actualmente: Método 3 (manual) activo por defecto.
 """

import os
import logging
import base64
import httpx
from typing import Optional
from datetime import datetime, timezone, timedelta

from . import database as db
from .models import Pago, PedidoFinanciero
from .currency import get_eur_ves_rate, convert_eur_to_ves
import asyncio

logger = logging.getLogger("financial_shield.verificacion")

CARACAS_TZ = timezone(timedelta(hours=-4))

# Configuración
VERIFICATION_METHOD = os.getenv("FS_BANK_VERIFICATION_METHOD", "manual")
OCR_ENABLED = os.getenv("FS_OCR_ENABLED", "false").lower() == "true"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
META_ACCESS_TOKEN = ""  # Se carga dinámicamente
META_API_VERSION = os.getenv("META_API_VERSION", "v25.0")


async def verificar_pago_manual(
    fs_pedido_id: int,
    monto_eur: float,
    metodo_pago: str,
    referencia: str = None,
    verificado_por: str = "manual",
) -> dict:
    """
    Verificación manual: Líder confirma pago via Telegram.

    Returns: dict con 'success', 'mensaje'
    """
    # Verificar anti-fraude: referencia duplicada
    if referencia:
        existing = db.get_pago_by_referencia(referencia)
        if existing:
            return {
                "success": False,
                "mensaje": f"⚠️ Referencia duplicada: {referencia} ya fue usada en pago #{existing.id}",
            }

    # Crear registro de pago
    tasa = await get_eur_ves_rate()
    monto_ves = convert_eur_to_ves(monto_eur, tasa) if tasa else None

    pago = Pago(
        fs_pedido_id=fs_pedido_id,
        monto_eur=monto_eur,
        monto_ves=monto_ves,
        metodo_pago=metodo_pago,
        referencia=referencia,
        tasa_eur_ves=tasa or 0,
        verificacion_metodo="manual",
        verificado=True,
        verificado_at=datetime.now(CARACAS_TZ).isoformat(),
        verificado_por=verificado_por,
    )

    pago_id = db.create_pago(pago)

    # Actualizar estado del pedido
    db.update_estado_pago(fs_pedido_id, "pagado", "manual")

    # Log de auditoría
    db.log_verificacion(
        fs_pedido_id, 1, "manual",
        True, "pagado",
        f"Pago verificado manualmente por {verificado_por}. Monto: €{monto_eur:.2f}"
    )

    logger.info("Pago verificado manualmente: pedido_fs=%s monto=€%.2f", fs_pedido_id, monto_eur)

    return {
        "success": True,
        "mensaje": f"✅ Pago verificado: €{monto_eur:.2f} ({metodo_pago})",
        "pago_id": pago_id,
    }


async def verificar_pago_api_bancaria(
    fs_pedido_id: int,
    codigo_confirmacion: str,
    monto_esperado_eur: float,
) -> dict:
    """
    Verificación via API bancaria (FUTURO).
    Cliente pega código de confirmación del banco.

    Returns: dict con 'success', 'mensaje'
    """
    # TODO: Implementar cuando API bancaria esté disponible
    # Por ahora, delegar a manual
    logger.warning("API bancaria no disponible, delegando a manual")

    return await verificar_pago_manual(
        fs_pedido_id=fs_pedido_id,
        monto_eur=monto_esperado_eur,
        metodo_pago="pagomovil",
        referencia=codigo_confirmacion,
        verificado_por="api_bancaria_pending",
    )


async def verificar_pago_ocr(
    fs_pedido_id: int,
    image_url: str,
    monto_esperado_eur: float,
    meta_token: str = None,
) -> dict:
    """
    Verificación via OCR: cliente envía comprobante por WhatsApp.
    Usa Qwen2.5-VL para extraer referencia + monto de la imagen.

    Returns: dict con 'success', 'mensaje', 'datos_extraidos'
    """
    if not OCR_ENABLED:
        logger.info("OCR deshabilitado, delegando a manual")
        return {
            "success": False,
            "mensaje": "OCR deshabilitado. Use verificación manual.",
            "needs_manual": True,
        }

    # 1. Descargar imagen de Meta API
    image_data = await _download_whatsapp_image(image_url, meta_token)
    if not image_data:
        return {
            "success": False,
            "mensaje": "No se pudo descargar el comprobante",
            "needs_manual": True,
        }

    # 2. OCR con Qwen2.5-VL
    datos = await _ocr_comprobante(image_data)
    if not datos:
        return {
            "success": False,
            "mensaje": "No se pudo leer el comprobante. Verificación manual requerida.",
            "needs_manual": True,
        }

    # 3. Validar monto
    monto_extraido = datos.get("monto", 0)
    if monto_extraido and abs(monto_extraido - monto_esperado_eur) > 0.50:
        return {
            "success": False,
            "mensaje": f"Monto no coincide: esperado €{monto_esperado_eur:.2f}, comprobante €{monto_extraido:.2f}",
            "datos_extraidos": datos,
            "needs_manual": True,
        }

    # 4. Registrar pago
    referencia = datos.get("referencia", f"OCR_{fs_pedido_id}")
    resultado = await verificar_pago_manual(
        fs_pedido_id=fs_pedido_id,
        monto_eur=monto_esperado_eur,
        metodo_pago="pagomovil",
        referencia=referencia,
        verificado_por="ocr",
    )

    resultado["datos_extraidos"] = datos
    return resultado


async def _download_whatsapp_image(image_url: str, meta_token: str) -> Optional[bytes]:
    """Descarga imagen del comprobante desde Meta API."""
    if not meta_token:
        logger.error("Meta token no proporcionado para descargar imagen")
        return None
    try:
        async with httpx.AsyncClient() as client:
            # Descargar media
            resp = await client.get(
                f"https://graph.facebook.com/{META_API_VERSION}/{image_url}",
                headers={"Authorization": f"Bearer {meta_token}"},
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                url = data.get("url")
                mime = data.get("mime_type", "image/jpeg")

                if url:
                    img_resp = await client.get(
                        url,
                        headers={"Authorization": f"Bearer {meta_token}"},
                        timeout=30,
                    )
                    if img_resp.status_code == 200:
                        return img_resp.content
    except Exception as e:
        logger.error("Error descargando imagen: %s", e)
    return None


async def _ocr_comprobante(image_data: bytes) -> Optional[dict]:
    """
    Usa Qwen2.5-VL (Ollama) para extraer datos del comprobante de pago.
    Returns: dict con 'referencia', 'monto', 'fecha', 'banco'
    """
    try:
        b64 = base64.b64encode(image_data).decode()

        prompt = (
            "Extrae los siguientes datos de este comprobante de pago móvil:\n"
            "- Referencia (número)\n"
            "- Monto (en bolívares)\n"
            "- Fecha\n"
            "- Banco emisor\n\n"
            "Responde SOLO en formato JSON:\n"
            '{"referencia": "123456789", "monto": 1000.00, "fecha": "2026-07-09", "banco": "Banesco"}'
        )

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": "qwen2.5:7b",
                    "prompt": prompt,
                    "images": [b64],
                    "stream": False,
                    "format": "json",
                },
                timeout=60,
            )
            if resp.status_code == 200:
                import json
                data = resp.json()
                texto = data.get("response", "{}")
                return json.loads(texto)
    except Exception as e:
        logger.error("Error OCR: %s", e)
    return None
