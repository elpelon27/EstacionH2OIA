#!/usr/bin/env python3
"""
============================================================================
video_watch_service — lógica compartida de los triggers /watch
============================================================================
Usado por:
  - scripts/prometeo/prometeo.py      (trigger manual CLI)
  - skills/prometeo_telegram.py       (trigger bot Telegram)

Responsabilidades:
  1. Validación de URL (solo youtube.com / youtu.be)
  2. Dedupe: si la URL ya está en Qdrant videos_h2o → path al MD existente
  3. Rate limiting (regla del Líder): 1 video cada 5 min por usuario,
     máx 20 videos/día. Log en logs/video_usage.log (JSON lines).
  4. Ejecución de /home/skynet/watch_video.sh con timeout y captura
     limpia de errores (yt-dlp / Gemini / timeout).
  5. /watch-status: videos de hoy, presupuesto estimado, últimos 5,
     estado de Qdrant videos_h2o.
  6. Post-proceso: corre skill_generator en dry-run (regla del Líder:
     NUNCA crea skills automáticamente) y reporta su decisión.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

REPO = Path("/mnt/ssd_trabajo/hermes-agent")
sys.path.insert(0, str(REPO))

WATCH_SCRIPT = "/home/skynet/watch_video.sh"
USAGE_LOG = REPO / "logs" / "video_usage.log"
QDRANT_URL = "http://localhost:6333"
COLLECTION = "videos_h2o"
DOCS_DIR = REPO / "docs" / "videos"

RATE_INTERVAL_SEC = 5 * 60      # 1 video cada 5 min por usuario
DAILY_LIMIT = 20                # máx 20 videos por día
WATCH_TIMEOUT_SEC = 20 * 60     # video muy largo → abortar a los 20 min

# Costo estimado por video (Gemini 3 Pro preview, ~60 frames + transcript)
# Ajustar cuando haya datos reales de uso.
EST_COST_PER_VIDEO_USD = 0.15

_YT_RE = re.compile(
    r"^https?://(www\.|m\.)?(youtube\.com/(watch\?v=|shorts/)|youtu\.be/)[A-Za-z0-9_-]{4,}"
)


def is_youtube_url(url: str) -> bool:
    return bool(_YT_RE.match(url.strip()))


def extract_youtube_url(text: str) -> str | None:
    """Extrae la primera URL de YouTube de un mensaje libre."""
    for m in re.finditer(
        r"https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?\S*v=|shorts/)\S*|youtu\.be/\S+)",
        text,
    ):
        candidate = m.group(0).split("&")[0].split(" ")[0]
        if is_youtube_url(candidate):
            return candidate
    return None


# ============================================================================
# Log de uso (JSON lines): {"ts": epoch, "user": "...", "url": "..."}
# ============================================================================


def _load_usage() -> list[dict[str, Any]]:
    if not USAGE_LOG.exists():
        return []
    out = []
    for line in USAGE_LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _log_usage(user: str, url: str) -> None:
    USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(USAGE_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(
            {"ts": time.time(), "user": user, "url": url}) + "\n")


def check_rate_limit(user: str) -> tuple[bool, str]:
    """Devuelve (permitido, motivo)."""
    entries = _load_usage()
    mine = [e for e in entries if e.get("user") == user]
    if not mine:
        return True, ""
    last = mine[-1]
    since = time.time() - last["ts"]
    if since < RATE_INTERVAL_SEC:
        wait = int((RATE_INTERVAL_SEC - since) // 60) + 1
        return False, f"Esperá ~{wait} min antes de otro video (límite: 1 cada 5 min)"
    today = datetime.now().strftime("%Y-%m-%d")
    n_today = sum(
        1 for e in mine
        if datetime.fromtimestamp(e["ts"]).strftime("%Y-%m-%d") == today
    )
    if n_today >= DAILY_LIMIT:
        return False, "Demasiados videos hoy, probá mañana"
    return True, ""


# ============================================================================
# Dedupe: URL ya procesada → buscar en Qdrant (y fallback en docs/videos)
# ============================================================================


def find_existing(url: str) -> str | None:
    """Si la URL ya fue procesada, devuelve el path al MD (o descripción)."""
    # 1) Qdrant por payload url
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        client = QdrantClient(url=QDRANT_URL, timeout=10)
        hits, _ = client.scroll(
            collection_name=COLLECTION,
            scroll_filter=Filter(must=[
                FieldCondition(key="url", match=MatchValue(value=url))
            ]),
            limit=1,
            with_payload=True,
        )
        if hits:
            p = hits[0].payload or {}
            vid = p.get("video_id", "")
            md = DOCS_DIR / f"{vid}.md"
            if md.exists():
                return str(md)
    except Exception:
        pass  # Qdrant caído → fallback al filesystem
    # 2) Fallback: buscar en los JSON generados
    if DOCS_DIR.exists():
        for j in DOCS_DIR.glob("*.json"):
            try:
                data = json.loads(j.read_text(encoding="utf-8"))
                if data.get("url") == url:
                    md = j.with_suffix(".md")
                    if md.exists():
                        return str(md)
            except Exception:
                continue
    return None


# ============================================================================
# Ejecución del pipeline
# ============================================================================


class WatchError(Exception):
    """Error de ejecución con mensaje limpio para el usuario."""


def run_watch(url: str, user: str = "lider") -> dict[str, Any]:
    """Ejecuta watch_video.sh. Devuelve dict con resultado parseado.

    Lanza WatchError con mensaje limpio si yt-dlp/Gemini/timeout fallan.
    Registra uso en logs/video_usage.log solo si el pipeline terminó OK.
    """
    allowed, reason = check_rate_limit(user)
    if not allowed:
        raise WatchError(reason)

    try:
        proc = subprocess.run(
            [WATCH_SCRIPT, url],
            capture_output=True,
            text=True,
            timeout=WATCH_TIMEOUT_SEC,
            cwd=REPO,
        )
    except subprocess.TimeoutExpired as exc:
        raise WatchError(
            "⏱️ Timeout: el video es muy largo o la descarga demoró "
            f"más de {WATCH_TIMEOUT_SEC // 60} min. Probá con uno más corto."
        ) from exc

    out = proc.stdout.strip()
    if proc.returncode != 0:
        err = (proc.stderr or out)[-500:]
        if "yt-dlp" in err.lower() or "download" in err.lower() \
                or "unsupported url" in err.lower() or "video unavailable" in err.lower():
            raise WatchError(
                "❌ yt-dlp falló: la URL parece inválida o el video no está "
                f"disponible.\nDetalle: {err}")
        if "llm" in err.lower() or "gemini" in err.lower() or "openrouter" in err.lower():
            raise WatchError(
                "❌ Gemini falló durante el análisis. Reintenta en unos "
                f"minutos.\nDetalle: {err}")
        raise WatchError(f"❌ El pipeline falló (exit {proc.returncode}):\n{err}")

    # watch.py imprime un JSON final en la última línea
    result: dict[str, Any] = {}
    for line in reversed(out.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                result = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
    if not result:
        raise WatchError(
            "⚠️ El pipeline terminó pero no pude parsear el resultado.\n"
            f"Última salida: {out[-300:]}")

    _log_usage(user, url)
    result["skill_decision"] = skill_dry_run(result)
    result["cost_est_usd"] = EST_COST_PER_VIDEO_USD
    return result


def skill_dry_run(result: dict[str, Any]) -> str:
    """Corre skill_generator --dry-run y devuelve su decisión (regla del
    Líder: nunca crea skills automáticamente)."""
    jpath = result.get("json") or ""
    if not jpath or not Path(jpath).exists():
        return "(sin JSON para evaluar skill)"
    try:
        proc = subprocess.run(
            [str(REPO / "venv/bin/python"),
             str(REPO / "scripts/skill_generator.py"),
             "--dry-run", "--json", jpath],
            capture_output=True, text=True, timeout=60, cwd=REPO)
        for line in proc.stdout.splitlines():
            if line.startswith("RESULTADO:"):
                return line.replace("RESULTADO: ", "")
        if "SÍ genera skill" in proc.stdout:
            return "propuesto (dry-run): revisar con el Líder antes de crear"
        return proc.stdout.strip()[-200:] or "(sin salida)"
    except Exception as e:
        return f"(skill_generator falló: {e})"


# ============================================================================
# /watch-status
# ============================================================================


def watch_status() -> str:
    entries = _load_usage()
    today = datetime.now().strftime("%Y-%m-%d")
    today_entries = [e for e in entries
                     if datetime.fromtimestamp(e["ts"]).strftime("%Y-%m-%d") == today]
    last5 = entries[-5:]

    lines = [
        "🎬 /watch-status — claude-watch",
        "",
        f"• Videos hoy: {len(today_entries)}/{DAILY_LIMIT}",
        f"• Presupuesto estimado hoy: ${len(today_entries) * EST_COST_PER_VIDEO_USD:.2f}"
        f" (${EST_COST_PER_VIDEO_USD:.2f}/video)",
        f"• Total histórico: {len(entries)} videos",
    ]
    if last5:
        lines.append("")
        lines.append("Últimos 5:")
        for e in reversed(last5):
            ts = datetime.fromtimestamp(e["ts"]).strftime("%m-%d %H:%M")
            lines.append(f"  • {ts} — {e.get('url', '?')[:70]}")
    else:
        lines.append("• Aún no hay videos procesados")

    # Estado Qdrant
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(url=QDRANT_URL, timeout=10)
        info = client.get_collection(COLLECTION)
        lines.append("")
        lines.append(
            f"• Qdrant {COLLECTION}: ✅ {info.points_count} puntos")
    except Exception as e:
        lines.append("")
        lines.append(f"• Qdrant {COLLECTION}: ❌ {e}")

    lines.append("")
    lines.append("💧")
    return "\n".join(lines)


if __name__ == "__main__":
    # Modo prueba: python video_watch_service.py <subcomando>
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        print(watch_status())
    elif cmd == "validate" and len(sys.argv) > 2:
        print("OK youtube" if is_youtube_url(sys.argv[2]) else "NO youtube")
    elif cmd == "extract" and len(sys.argv) > 2:
        print(extract_youtube_url(" ".join(sys.argv[2:])))
