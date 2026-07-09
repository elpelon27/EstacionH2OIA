"""
 ============================================================================
 Financial Shield — Conversión de monedas (EUR/VES/USD)
 Estación H2O · Maracaibo, Venezuela
 ============================================================================

3 prioridades para obtener tasa EUR/VES:
1. frankfurter.app (gratis, sin API key)
2. BCV scraper (USD/VES + EUR/USD → calcular EUR/VES)
3. Manual (Líder envía /tasa por Telegram)

Cada tasa se guarda en fs_tasas_cambio (inmutable).
 """

import os
import logging
import httpx
from typing import Optional
from datetime import datetime, timezone, timedelta

from . import database as db
from .models import TasaCambio

logger = logging.getLogger("financial_shield.currency")

CARACAS_TZ = timezone(timedelta(hours=-4))

# URLs APIs
FRANKFURTER_URL = os.getenv("FS_TASA_API_URL", "https://api.frankfurter.app")
BCV_FALLBACK = os.getenv("FS_TASA_FALLBACK_BCV", "true").lower() == "true"


async def get_eur_ves_rate() -> Optional[float]:
    """
    Obtiene tasa EUR/VES con 3 prioridades:
    1. frankfurter.app directo
    2. BCV (USD/VES × EUR/USD)
    3. Última tasa guardada en BD

    Returns: tasa EUR/VES o None si no disponible.
    """
    # Prioridad 1: frankfurter.app
    tasa = await _try_frankfurter()
    if tasa:
        db.save_tasa("EUR/VES", tasa, "api_eur_ves", "frankfurter.app")
        logger.info("Tasa EUR/VES obtenida de frankfurter: %.2f", tasa)
        return tasa

    # Prioridad 2: BCV (si está habilitado)
    if BCV_FALLBACK:
        tasa = await _try_bcv_calculation()
        if tasa:
            db.save_tasa("EUR/VES", tasa, "calculada", "BCV: EUR/USD × USD/VES")
            logger.info("Tasa EUR/VES calculada de BCV: %.2f", tasa)
            return tasa

    # Prioridad 3: última tasa guardada
    last = db.get_last_tasa("EUR/VES")
    if last:
        logger.warning("Usando última tasa guardada: %.2f (fuente: %s)", last.tasa, last.fuente)
        return last.tasa

    logger.error("No se pudo obtener tasa EUR/VES de ninguna fuente")
    return None


async def _try_frankfurter() -> Optional[float]:
    """Intenta obtener EUR/VES directo de frankfurter.app."""
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            # frankfurter puede no soportar VES directo, intentar
            resp = await client.get(
                f"{FRANKFURTER_URL}/latest",
                params={"from": "EUR", "to": "VES"},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                ves = data.get("rates", {}).get("VES")
                if ves:
                    return float(ves)

            # Si VES no disponible, obtener EUR/USD y calcular con BCV
            resp2 = await client.get(
                f"{FRANKFURTER_URL}/latest",
                params={"from": "EUR", "to": "USD"},
                timeout=10,
            )
            if resp2.status_code == 200:
                eur_usd = resp2.json().get("rates", {}).get("USD")
                if eur_usd:
                    # Guardar EUR/USD para cálculo BCV
                    db.save_tasa("EUR/USD", float(eur_usd), "api_eur_ves", "frankfurter.app")
                    return None  # Dejar que BCV calcule
    except Exception as e:
        logger.warning("frankfurter.app no disponible: %s", e)
    return None


async def _try_bcv_calculation() -> Optional[float]:
    """Calcula EUR/VES = (EUR/USD) × (USD/VES del BCV)."""
    try:
        # Obtener EUR/USD (de frankfurter o última guardada)
        eur_usd_tasa = db.get_last_tasa("EUR/USD")
        if not eur_usd_tasa:
            # Intentar frankfurter de nuevo
            try:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    resp = await client.get(
                        f"{FRANKFURTER_URL}/latest",
                        params={"from": "EUR", "to": "USD"},
                        timeout=10,
                    )
                    if resp.status_code == 200:
                        eur_usd = float(resp.json().get("rates", {}).get("USD", 0))
                        if eur_usd:
                            db.save_tasa("EUR/USD", eur_usd, "api_eur_ves", "frankfurter.app")
                            eur_usd_tasa = eur_usd
            except Exception:
                pass

        if not eur_usd_tasa:
            return None

        eur_usd = eur_usd_tasa.tasa if hasattr(eur_usd_tasa, 'tasa') else eur_usd_tasa

        # Obtener USD/VES del BCV (scraper o API)
        usd_ves = await _get_bcv_usd_ves()
        if not usd_ves:
            return None

        db.save_tasa("USD/VES", usd_ves, "bcv", "BCV oficial")

        eur_ves = eur_usd * usd_ves
        return round(eur_ves, 2)
    except Exception as e:
        logger.error("Error cálculo BCV: %s", e)
        return None


async def _get_bcv_usd_ves() -> Optional[float]:
    """Obtiene USD/VES del BCV."""
    try:
        # Intentar API pública BCV
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(
                "https://bcv-exchange-rates.vercel.app/api/rates",
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                # Estructura puede variar, buscar USD
                if isinstance(data, dict):
                    usd = data.get("USD", {}).get("rate") or data.get("usd")
                    if usd:
                        return float(usd)
                elif isinstance(data, list):
                    for item in data:
                        if item.get("moneda", "").upper() in ("USD", "DOLAR"):
                            return float(item.get("tasa", 0))
    except Exception as e:
        logger.warning("BCV API no disponible: %s", e)
    return None


def set_manual_rate(tasa: float, par: str = "EUR/VES"):
    """Líder envía tasa manual via Telegram."""
    db.save_tasa(par, tasa, "manual", "Ingresada por Líder via Telegram")
    logger.info("Tasa %s manual: %.2f", par, tasa)
    return tasa


def convert_eur_to_ves(monto_eur: float, tasa: float = None) -> float:
    """Convierte EUR a VES usando tasa dada o última guardada."""
    if tasa is None:
        last = db.get_last_tasa("EUR/VES")
        tasa = last.tasa if last else 0
    return round(monto_eur * tasa, 2)


def convert_ves_to_eur(monto_ves: float, tasa: float = None) -> float:
    """Convierte VES a EUR."""
    if tasa is None:
        last = db.get_last_tasa("EUR/VES")
        tasa = last.tasa if last else 1
    return round(monto_ves / tasa, 2)


def get_tasa_display() -> str:
    """Retorna string legible de la tasa actual."""
    last = db.get_last_tasa("EUR/VES")
    if last:
        return f"€1 = Bs. {last.tasa:.2f} (fuente: {last.fuente})"
    return "Tasa no disponible"
