"""
 ============================================================================
 Financial Shield — Conversión de monedas (EUR/VES/USD)
 Estación H2O · Maracaibo, Venezuela
 ============================================================================

3 prioridades para obtener tasa EUR/VES:
1. open.er-api.com (gratis, tiene EUR/VES directo, actualizada diariamente)
2. frankfurter.dev (EUR/USD para referencia)
3. Manual (Líder envía /tasa por Telegram)

Cada tasa se guarda en fs_tasas_cambio (inmutable).
"""

import logging
from datetime import timedelta, timezone

import httpx

from . import database as db

logger = logging.getLogger("financial_shield.currency")

CARACAS_TZ = timezone(timedelta(hours=-4))


async def get_eur_ves_rate() -> float | None:
    """
    Obtiene tasa EUR/VES con 3 prioridades:
    1. open.er-api.com (tiene EUR/VES directo)
    2. frankfurter.dev (EUR/USD referencia)
    3. Última tasa guardada en BD

    Returns: tasa EUR/VES o None si no disponible.
    """
    # Prioridad 1: open.er-api.com (tiene EUR/VES directo)
    tasa = await _try_open_er_api()
    if tasa:
        db.save_tasa("EUR/VES", tasa, "open_er_api", "open.er-api.com")
        logger.info("Tasa EUR/VES obtenida de open.er-api.com: %.2f", tasa)
        return tasa

    # Prioridad 2: frankfurter (EUR/USD referencia)
    eur_usd = await _try_frankfurter()
    if eur_usd:
        db.save_tasa("EUR/USD", eur_usd, "frankfurter", "frankfurter.dev")
        logger.info("EUR/USD de frankfurter: %.4f (sin VES)", eur_usd)

    # Prioridad 3: última tasa guardada
    last = db.get_last_tasa("EUR/VES")
    if last:
        logger.warning("Usando última tasa guardada: %.2f (fuente: %s)", last.tasa, last.fuente)
        return last.tasa

    logger.error("No se pudo obtener tasa EUR/VES de ninguna fuente")
    return None


async def _try_open_er_api() -> float | None:
    """Obtiene EUR/VES directo de open.er-api.com."""
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(
                "https://open.er-api.com/v6/latest/EUR",
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                ves = data.get("rates", {}).get("VES")
                if ves:
                    # Guardar también EUR/USD como referencia
                    usd = data.get("rates", {}).get("USD")
                    if usd:
                        db.save_tasa("EUR/USD", float(usd), "open_er_api", "open.er-api.com")
                    return float(ves)
    except Exception as e:
        logger.warning("open.er-api.com no disponible: %s", e)
    return None


async def _try_frankfurter() -> float | None:
    """Obtiene EUR/USD de frankfurter.dev (referencia secundaria)."""
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(
                "https://api.frankfurter.dev/v1/latest?from=EUR&to=USD",
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                usd = data.get("rates", {}).get("USD")
                if usd:
                    return float(usd)
    except Exception as e:
        logger.warning("frankfurter.dev no disponible: %s", e)
    return None


def set_manual_rate(tasa: float, par: str = "EUR/VES") -> float:
    """Líder envía tasa manual via Telegram."""
    db.save_tasa(par, tasa, "manual", "Ingresada por Líder via Telegram")
    logger.info("Tasa %s manual: %.2f", par, tasa)
    return tasa


def convert_eur_to_ves(monto_eur: float, tasa: float | None = None) -> float:
    """Convierte EUR a VES usando tasa dada o última guardada."""
    if tasa is None or tasa == 0:
        last = db.get_last_tasa("EUR/VES")
        tasa = last.tasa if last else 0
    return round(monto_eur * tasa, 2)


def convert_ves_to_eur(monto_ves: float, tasa: float | None = None) -> float:
    """Convierte VES a EUR."""
    if tasa is None or tasa == 0:
        last = db.get_last_tasa("EUR/VES")
        tasa = last.tasa if last else 1
    return round(monto_ves / tasa, 2)


def get_tasa_display() -> str:
    """Retorna string legible de la tasa actual."""
    last = db.get_last_tasa("EUR/VES")
    if last and last.tasa > 0:
        return f"€1 = Bs. {last.tasa:.2f} (fuente: {last.fuente})"
    return "Tasa no disponible"
