"""
============================================================================
Financial Shield — Verificación de pagos v3.0
Estación H2O · Maracaibo, Venezuela
============================================================================

3 métodos de verificación:
1. API Bancaria (futuro) — cliente pega código de confirmación
2. OCR de comprobante — Tesseract → Regex → Qwen2.5-VL fallback
3. Manual — Líder confirma via Telegram /pagado

Scheduler resiliente + Recovery scan al arrancar + VRAM guard.
"""

import base64
import contextlib
import logging
import os
import re
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import httpx

from . import database as db
from .currency import convert_eur_to_ves, get_eur_ves_rate
from .models import PedidoFinanciero

logger = logging.getLogger("financial_shield.verificacion")

CARACAS_TZ = timezone(timedelta(hours=-4))

# Config
MAX_RECORDATORIOS = int(os.getenv("FS_MAX_RECORDATORIOS", "3"))
INTERVALO_MINUTOS = int(os.getenv("FS_INTERVALO_RECORDATORIO_MINUTOS", "60"))
OCR_ENABLED = os.getenv("FS_OCR_ENABLED", "false").lower() == "true"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
META_API_VERSION = os.getenv("META_API_VERSION", "v25.0")

# VRAM Guard para Qwen2.5-VL fallback
PYNVML_AVAILABLE = False
try:
    import pynvml  # type: ignore[import-untyped]

    pynvml.nvmlInit()
    PYNVML_AVAILABLE = True
except Exception:
    logger.warning("pynvml no disponible; VRAM guard deshabilitado")

# Perceptual hash (pHash) para anti-fraude de comprobantes
try:
    import imagehash
    from PIL import Image

    PHASH_AVAILABLE = True
except Exception:
    logger.warning("imagehash/PIL no disponible; pHash anti-fraude deshabilitado")
    PHASH_AVAILABLE = False

VRAM_LIMIT_MB = int(os.getenv("FS_LLM_VRAM_LIMIT_MB", "3500"))  # GTX 1070 8GB -> dejar 3.5GB libre


def _compute_phash(image_data: bytes) -> str | None:
    """Calcula perceptual hash (pHash) de una imagen para detección de duplicados/editados."""
    if not PHASH_AVAILABLE:
        return None
    try:
        import io

        img = Image.open(io.BytesIO(image_data))
        # Convertir a RGB si es RGBA
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")
        phash = imagehash.phash(img, hash_size=16)  # 256 bits
        return str(phash)
    except Exception as e:
        logger.warning("Error calculando pHash: %s", e)
        return None


def _check_vram() -> bool:
    """Return True si hay VRAM libre >= VRAM_LIMIT_MB."""
    if not PYNVML_AVAILABLE:
        return True  # Fail-open si no hay pynvml
    try:
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        free_mb = info.free / (1024 * 1024)
        return free_mb >= VRAM_LIMIT_MB
    except Exception as e:
        logger.warning("VRAM check falló: %s", e)
        return True


# =============================================================================
# 1. RECOVERY SCAN — Se ejecuta al ARRANCAR el bridge (valentina_bridge.py startup)
# =============================================================================
async def recovery_scan_stuck_payments() -> int:
    """
    Escanea pedidos atascados en 'verificando' o 'parcial' tras reinicio.
    Reanuda recordatorios donde corresponda.
    """
    now = datetime.now(UTC)
    recovered = 0

    with db.get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM fs_pedidos
            WHERE estado_pago IN ('verificando', 'parcial')
            AND escalo_humano = 0
            AND recordatorios_enviados < ?
            AND (
                ultimo_recordatorio_at IS NULL
                OR datetime(ultimo_recordatorio_at) <= datetime(?, '-' || ? || ' minutes')
            )
        """,
            (MAX_RECORDATORIOS, now.isoformat(), INTERVALO_MINUTOS),
        ).fetchall()

    for row in rows:
        pedido = PedidoFinanciero(**dict(row))
        logger.info("Recovery: reanudando recordatorios para pedido_fs=%s", pedido.id)
        await _process_reminder_cycle(pedido)
        recovered += 1

    if recovered:
        logger.warning("Recovery scan completado: %d pedidos reanudados", recovered)
    return recovered


# =============================================================================
# 2. CICLO PRINCIPAL — Lo llama cron cada 30 min (run_fs_recordatorios)
# =============================================================================
async def run_reminder_cycle() -> dict[str, int]:
    """Ejecuta un ciclo completo de recordatorios. Retorna contadores."""
    pedidos = _get_pedidos_para_recordatorio()

    stats = {"procesados": 0, "recordatorios_enviados": 0, "escalados": 0, "errores": 0}

    for pedido in pedidos:
        stats["procesados"] += 1
        try:
            resultado = await _process_reminder_cycle(pedido)
            if resultado["accion"] == "recordatorio_enviado":
                stats["recordatorios_enviados"] += 1
            elif resultado["accion"] == "escalar_humano":
                stats["escalados"] += 1
        except Exception as e:
            logger.error("Error procesando recordatorio pedido_fs=%s: %s", pedido.id, e)
            stats["errores"] += 1

    logger.info("Ciclo recordatorios: %s", stats)
    return stats


def _get_pedidos_para_recordatorio() -> list[PedidoFinanciero]:
    """Réplica de lógica actual + filtro de tiempo estricto."""
    now = datetime.now(CARACAS_TZ)
    pedidos = db.get_pedidos_pendientes_pago()
    result = []

    for p in pedidos:
        if p.ultimo_recordatorio_at:
            try:
                ultimo = datetime.fromisoformat(p.ultimo_recordatorio_at.replace("Z", "+00:00"))
                if (now - ultimo).total_seconds() < INTERVALO_MINUTOS * 60:
                    continue
            except (ValueError, TypeError):
                pass
        result.append(p)
    return result


async def _process_reminder_cycle(pedido: PedidoFinanciero) -> dict[str, Any]:
    """Procesa un recordatorio individual. Idempotente."""
    intento = pedido.recordatorios_enviados + 1

    if intento > MAX_RECORDATORIOS:
        return await _escalar_humano(pedido, intento)

    # Enviar recordatorio via Valentina (WhatsApp)
    mensaje_cliente = (
        f"Estimado {pedido.cliente_nombre}, le recordamos que tiene un pedido "
        f"pendiente de pago por €{pedido.monto_total_eur:.2f}. "
        f"Por favor, envíe su comprobante. ¡Gracias! 💧"
    )

    # TODO: Llamar a Valentina para enviar WhatsApp
    # await valentina.send_whatsapp(pedido.cliente_telefono, mensaje_cliente)
    logger.info("Recordatorio #%d enviado a %s", intento, pedido.cliente_telefono)

    # Persistir
    now = datetime.now(UTC).isoformat()
    with db.get_db() as conn:
        conn.execute(
            """
            UPDATE fs_pedidos
            SET recordatorios_enviados = ?, ultimo_recordatorio_at = ?, actualizado_at = ?
            WHERE id = ?
        """,
            (intento, now, now, pedido.id),
        )

        db.log_verificacion(
            pedido.id,
            intento,
            "manual",
            False,
            "recordatorio_enviado",
            f"Recordatorio #{intento} enviado",
        )

    return {
        "accion": "recordatorio_enviado",
        "mensaje": f"Recordatorio #{intento}/{MAX_RECORDATORIOS} enviado",
        "mensaje_cliente": mensaje_cliente,
        "intento": intento,
    }


async def _escalar_humano(pedido: PedidoFinanciero, intento: int) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    with db.get_db() as conn:
        conn.execute(
            """
            UPDATE fs_pedidos SET escalo_humano = 1, actualizado_at = ? WHERE id = ?
        """,
            (now, pedido.id),
        )
        db.log_verificacion(
            pedido.id,
            intento,
            "manual",
            False,
            "escalo_humano",
            "3 recordatorios fallidos — escalado a humano",
        )

    # Alerta a Líder por Telegram
    alerta = (
        f"🚨 ESCALAMIENTO HUMANO\n\n"
        f"Cliente: {pedido.cliente_nombre} ({pedido.cliente_telefono})\n"
        f"Pedido: #{pedido.pedido_id}\n"
        f"Monto: €{pedido.monto_total_eur:.2f}\n"
        f"Recordatorios: {MAX_RECORDATORIOS}\n"
        f"Estado: SIN PAGO"
    )
    # await telegram_bot.send_alert(alerta)
    logger.warning("ESCALADO HUMANO: pedido_fs=%s", pedido.id)

    return {"accion": "escalar_humano", "mensaje": alerta, "mensaje_cliente": None}


# =============================================================================
# 3. VERIFICACIÓN MANUAL (Líder via Telegram) — Transacción atómica v3.0
# =============================================================================
async def verificar_pago_manual(
    fs_pedido_id: int,
    monto_eur: float,
    metodo_pago: str,
    referencia: str | None = None,
    verificado_por: str = "manual",
) -> dict[str, Any]:
    """Verificación manual con actualización atómica de monto_pagado_eur + estado."""

    # Anti-fraude: referencia duplicada (same method)
    if referencia:
        existing = db.get_pago_by_referencia(referencia)
        if existing and existing.metodo_pago == metodo_pago:
            return {
                "success": False,
                "mensaje": f"⚠️ Referencia duplicada: {referencia} ya usada en pago #{existing.id}",
            }

    # Tasa AL MOMENTO DEL PAGO (no la de la deuda)
    tasa_pago = await get_eur_ves_rate()
    monto_ves = convert_eur_to_ves(monto_eur, tasa_pago) if tasa_pago else None

    # Transacción atómica: INSERT en fs_pagos + UPDATE fs_pedidos (monto_pagado_eur, estado_pago)
    pago_id, nuevo_estado = db.add_pago_and_update_pedido(
        fs_pedido_id=fs_pedido_id,
        monto_eur=monto_eur,
        monto_ves=monto_ves or 0,
        tasa_eur_ves_pago=tasa_pago or 0,
        metodo_pago=metodo_pago,
        referencia=referencia,
        comprobante_phash=None,  # Fase 6
        verificacion_metodo="manual",
        verificado_por=verificado_por,
    )

    logger.info(
        "Pago verificado: pedido_fs=%s monto=€%.2f estado=%s", fs_pedido_id, monto_eur, nuevo_estado
    )
    return {
        "success": True,
        "mensaje": f"✅ Pago verificado: €{monto_eur:.2f} ({metodo_pago}) → Estado: {nuevo_estado}",
        "pago_id": pago_id,
        "nuevo_estado": nuevo_estado,
    }


# =============================================================================
# 4. VERIFICACIÓN API BANCARIA (Futuro)
# =============================================================================
async def verificar_pago_api_bancaria(
    fs_pedido_id: int,
    codigo_confirmacion: str,
    monto_esperado_eur: float,
) -> dict[str, Any]:
    """Verificación via API bancaria (FUTURO). Cliente pega código de confirmación."""
    logger.warning("API bancaria no disponible, delegando a manual")
    return await verificar_pago_manual(
        fs_pedido_id=fs_pedido_id,
        monto_eur=monto_esperado_eur,
        metodo_pago="pagomovil",
        referencia=codigo_confirmacion,
        verificado_por="api_bancaria_pending",
    )


# =============================================================================
# 5. OCR TURBO — Tesseract (CPU) → Regex → Qwen2.5-VL (GPU) con VRAM guard
# =============================================================================
async def verificar_pago_ocr(
    fs_pedido_id: int,
    image_url: str,
    monto_esperado_eur: float,
    meta_token: str | None = None,
) -> dict[str, Any]:
    """Pipeline OCR: 1) Tesseract rápido 2) Regex 3) Qwen fallback (si VRAM)."""

    if not OCR_ENABLED:
        return {"success": False, "mensaje": "OCR deshabilitado", "needs_manual": True}

    # 1. Descargar imagen
    image_data = await _download_whatsapp_image(image_url, meta_token or "")
    if not image_data:
        return {"success": False, "mensaje": "No se pudo descargar imagen", "needs_manual": True}

    # 2. Tesseract (rápido, CPU)
    raw_text = ""
    try:
        import io

        import pytesseract
        from PIL import Image

        img = Image.open(io.BytesIO(image_data))
        raw_text = pytesseract.image_to_string(img, lang="spa")
        logger.debug("OCR Tesseract raw: %s", raw_text[:200])
    except Exception as e:
        logger.warning("Tesseract falló: %s", e)
        raw_text = ""

    # 3. Regex potente (patrones bancarios VE)
    referencia = None
    monto_ves = None

    patterns = [
        r"[Rr]eferencia[:\s]*(\d{6,})",
        r"[Cc]ódigo[:\s]*(\d{6,})",
        r"[Tt]ransacción[:\s]*(\d{6,})",
        r"Bs\.?\s*([\d.,]+)",
        r"Monto[:\s]*Bs\.?\s*([\d.,]+)",
    ]

    for pat in patterns:
        m = re.search(pat, raw_text, re.IGNORECASE)
        if m:
            if not referencia and m.group(1).isdigit():
                referencia = m.group(1)
            if not monto_ves:
                with contextlib.suppress(ValueError):
                    monto_ves = float(m.group(1).replace(",", "").replace(".", ""))

    # Si regex encuentra todo → éxito
    if referencia and monto_ves:
        tasa_actual = await get_eur_ves_rate() or 1
        monto_eur_extraido = round(monto_ves / tasa_actual, 2)
        if abs(monto_eur_extraido - monto_esperado_eur) <= 0.50:
            return await verificar_pago_manual(
                fs_pedido_id, monto_esperado_eur, "pagomovil", referencia, "ocr_tesseract"
            )

    # 4. Fallback Qwen2.5-VL (solo si VRAM disponible)
    if _check_vram():
        try:
            qwen_result = await _ocr_qwen_vl(image_data)
            if qwen_result and qwen_result.get("referencia") and qwen_result.get("monto_ves"):
                tasa_actual = await get_eur_ves_rate() or 1
                monto_eur_extraido = round(qwen_result["monto_ves"] / tasa_actual, 2)
                if abs(monto_eur_extraido - monto_esperado_eur) <= 0.50:
                    return await verificar_pago_manual(
                        fs_pedido_id,
                        monto_esperado_eur,
                        "pagomovil",
                        qwen_result["referencia"],
                        "ocr_qwen",
                    )
        except Exception as e:
            logger.error("Qwen OCR falló: %s", e)
    else:
        logger.warning("VRAM insuficiente para Qwen; saltando fallback LLM")

    return {"success": False, "mensaje": "OCR no pudo extraer datos válidos", "needs_manual": True}


async def _ocr_qwen_vl(image_data: bytes) -> dict | None:
    """Llamada a Ollama/Qwen2.5-VL con imagen base64."""
    b64 = base64.b64encode(image_data).decode()
    payload = {
        "model": "qwen2.5-vl:7b",
        "messages": [
            {
                "role": "user",
                "content": 'Extrae referencia (número) y monto en bolívares de este comprobante. Responde JSON: {"referencia": "", "monto_ves": 0}',
                "images": [b64],
            }
        ],
        "format": "json",
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
        if resp.status_code == 200:
            import json

            content = resp.json()["message"]["content"]
            return json.loads(content)
    return None


async def _download_whatsapp_image(image_url: str, meta_token: str) -> bytes | None:
    if not meta_token:
        return None
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://graph.facebook.com/{META_API_VERSION}/{image_url}",
                headers={"Authorization": f"Bearer {meta_token}"},
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                url = data.get("url")
                if url:
                    img_resp = await client.get(
                        url, headers={"Authorization": f"Bearer {meta_token}"}, timeout=30
                    )
                    if img_resp.status_code == 200:
                        return img_resp.content
    except Exception as e:
        logger.error("Error descargando imagen: %s", e)
    return None
