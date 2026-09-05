#!/usr/bin/env python3
"""
============================================================================
Prometeo Telegram Bot — Interfaz Líder ↔ Agente IA Prometeo
Estación H2O · Maracaibo, Venezuela
============================================================================

Bot dedicado para que el Líder interactúe directamente con Prometeo
(agente IA de desarrollo) via Telegram.

Comandos:
    /status       — Estado del sistema (servicios, BD, health)
    /memory       — Inspeccionar memoria semántica/episódica
    /skills       — Listar/ver skills disponibles
    /review       — Code review último commit o PR
    /health       — Health check completo (bridge, dispatcher, financial)
    /kill         — Toggle kill switch Valentina
    /tasa         — Ver/cambiar tasa EUR/VES
    /deploy       — Estado deploys / rollback
    /logs [svc]   — Logs de servicio (bridge, dispatcher, financial)
    /shell        — Ejecutar comando shell (solo read-only-safe)
    /help         — Esta ayuda
    /pending      — Ver solicitudes de aprobación pendientes
    /approve      — Aprobar una solicitud con respuesta
    /reject       — Rechazar una solicitud

Seguridad:
    Solo el chat_id del Líder (TELEGRAM_CHAT_ID_HERMES) tiene permiso.
    Comandos destructivos requieren confirmación explícita.
"""

import asyncio
import json
import logging
import os
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Cargar .env
env_path = Path("/mnt/ssd_trabajo/hermes-agent/config/.env")
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")
sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent/scripts")

from llm_client import LLMClient, detect_task_type  # noqa: E402
from video_watch_service import (  # noqa: E402
    WatchError,
    extract_youtube_url,
    find_existing,
    is_youtube_url,
    run_watch,
    watch_status,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("prometeo.telegram_bot")

CARACAS_TZ = timezone(timedelta(hours=-4))

# Config desde .env
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN_HERMES", "")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID_HERMES", "1663148211"))
KILL_SWITCH_FILE = os.getenv(
    "KILL_SWITCH_FILE", "/mnt/ssd_trabajo/hermes-agent/data/valentina.kill"
)
SQLITE_PATH = os.getenv("SQLITE_PATH", "/mnt/ssd_trabajo/hermes-agent/data/conversations.db")
DISPATCH_DB = "/mnt/ssd_trabajo/hermes-agent/data/dispatch.db"
BRIDGE_HEALTH_URL = os.getenv("BRIDGE_HEALTH_URL", "http://localhost:8000/health")

# Approval system
APPROVAL_PENDING_DIR = Path("/mnt/ssd_trabajo/hermes-agent/data/prometeo_approvals/pending")
APPROVAL_COMPLETED_DIR = Path("/mnt/ssd_trabajo/hermes-agent/data/prometeo_approvals/completed")

# Servicios systemd conocidos
KNOWN_SERVICES = [
    "valentina-bridge",
    "dispatcher-bot",
    "telegram-bot",
    "cloudflared",
]

# Rutas permitidas para shell read-only
ALLOWED_SHELL_COMMANDS = {
    "health": "curl -s http://localhost:8000/health | jq .",
    "metrics": "curl -s http://localhost:8000/metrics",
    "disk": "df -h /mnt/ssd_trabajo",
    "mem": "free -h",
    "processes": "ps aux | head -20",
    "services": (
        "systemctl status valentina-bridge dispatcher-bot telegram-bot cloudflared --no-pager"
    ),
    "git_log": "cd /mnt/ssd_trabajo/hermes-agent && git log --oneline -10",
    "git_status": "cd /mnt/ssd_trabajo/hermes-agent && git status",
    "ruff_check": (
        "cd /mnt/ssd_trabajo/hermes-agent && "
        "/mnt/ssd_trabajo/hermes-agent/venv/bin/ruff check api/bridge.py"
    ),
    "mypy_check": (
        "cd /mnt/ssd_trabajo/hermes-agent && "
        "PYTHONPATH=/mnt/ssd_trabajo/hermes-agent/src "
        "/mnt/ssd_trabajo/hermes-agent/venv/bin/python -m mypy "
        "src/agents/financial_agent.py --no-error-summary"
    ),
    "test_dispatch": (
        "cd /mnt/ssd_trabajo/hermes-agent && "
        "/mnt/ssd_trabajo/hermes-agent/venv/bin/python -m pytest "
        "tests/integration/test_dispatch_flow.py -v --tb=short"
    ),
}


def _is_authorized(update: Update) -> bool:
    chat = update.effective_chat
    assert chat is not None
    return bool(chat.id == TELEGRAM_CHAT_ID)


async def _unauthorized(update: Update) -> None:
    msg = update.message
    chat = update.effective_chat
    user = update.effective_user
    assert msg is not None
    assert chat is not None
    assert user is not None
    await msg.reply_text("🚫 No autorizado. Este bot es privado de Prometeo (Estación H2O).")
    logger.warning("Acceso no autorizado: chat_id=%s username=%s", chat.id, user.username)


async def _require_confirmation(update: Update, action: str) -> bool:
    """Pide confirmación explícita para acciones destructivas."""
    msg = update.message
    assert msg is not None
    text = msg.text or ""
    if "confirmo" in text.lower() or "sí confirmo" in text.lower() or "si confirmo" in text.lower():
        return True
    await msg.reply_text(
        f'⚠️ Acción sensible: {action}\nResponde con "confirmo" o "sí confirmo" para proceder.'
    )
    return False


async def cmd_watch(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Trigger /watch <url> — pipeline claude-watch en background."""
    if not _is_authorized(update):
        return await _unauthorized(update)
    msg = update.message
    assert msg is not None
    user = update.effective_user
    user_id = str(user.id) if user else "unknown"

    url = " ".join(ctx.args).strip() if ctx.args else ""
    if not url:
        await msg.reply_text("Pasame una URL de YouTube")
        return
    url = extract_youtube_url(url) or url
    if not is_youtube_url(url):
        await msg.reply_text("Solo soporto YouTube (youtube.com/watch?v=... o youtu.be/...)")
        return

    existing = find_existing(url)
    if existing:
        await msg.reply_text(f"Ya procesé ese video. Resumen: {existing}")
        return

    await msg.reply_text("🎬 Procesando video... puede tardar 1-3 min")

    def _run() -> dict[str, Any]:
        return run_watch(url, user=f"telegram-{user_id}")

    try:
        result = await asyncio.to_thread(_run)
    except WatchError as e:
        await msg.reply_text(str(e))
        return

    obsidian_rel = Path(result.get("md", "")).name
    lines = [
        f"✅ {result.get('video_id', 'video')} procesado",
        f"• Tema: {result.get('tema', '?')}",
        f"• Skill: {result.get('skill_decision', '—')}",
        f"• Obsidian: obsidian-vault/videos/{obsidian_rel}",
        f"• Qdrant: {result.get('points', 0)} puntos (videos_h2o)",
    ]
    await msg.reply_text("\n".join(lines) + "\n💧")
    logger.info("Video procesado vía Telegram: %s", url)



async def cmd_watch_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return await _unauthorized(update)
    assert update.message is not None
    await update.message.reply_text(watch_status())


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return await _unauthorized(update)
    assert update.message is not None
    if os.path.exists(KILL_SWITCH_FILE):
        os.remove(KILL_SWITCH_FILE)
        await update.message.reply_text(
            "✅ Kill switch DESACTIVADO\nValentina está respondiendo de nuevo. 💧"
        )
        logger.info("Kill switch desactivado por Líder via Prometeo bot")
    else:
        await update.message.reply_text("ℹ️ El kill switch no estaba activo.\nPrometeo listo. 🔥")


async def cmd_stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return await _unauthorized(update)
    assert update.message is not None
    assert update.effective_user is not None
    if not await _require_confirmation(update, "Activar kill switch (detener Valentina)"):
        return
    import os as _os

    _fd = _os.open(KILL_SWITCH_FILE, _os.O_CREAT | _os.O_WRONLY | _os.O_TRUNC, 0o600)
    with _os.fdopen(_fd, "w") as f:
        f.write(f"killed by {update.effective_user.username} at {datetime.now(CARACAS_TZ)}")
    await update.message.reply_text(
        "🛑 Kill switch ACTIVADO\nValentina NO responderá mensajes nuevos.\nPara reactivar: /start"
    )
    logger.warning("Kill switch activado por Líder via Prometeo bot")


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return await _unauthorized(update)
    assert update.message is not None
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(BRIDGE_HEALTH_URL, timeout=5)
            health = resp.json()
    except Exception as e:
        await update.message.reply_text(f"❌ Bridge no responde: {e}")
        return

    kill_active = health.get("checks", {}).get("kill_switch", False)
    uptime = health.get("uptime_seconds", 0)
    status_emoji = "🛑" if kill_active else ("✅" if health["status"] == "ok" else "⚠️")

    svc_status = {}
    for svc in KNOWN_SERVICES:
        try:
            result = subprocess.run(
                ["systemctl", "is-active", svc], capture_output=True, text=True, timeout=3
            )
            svc_status[svc] = result.stdout.strip()
        except Exception:
            svc_status[svc] = "unknown"

    msg = (
        f"{status_emoji} Estado Sistema Estación H2O\n\n"
        f"• Bridge Status: {health['status']}\n"
        f"• Uptime: {int(uptime // 60)} min\n"
        f"• Dify API: {'✅' if health['checks'].get('dify_api_key') else '❌'}\n"
        f"• Meta API: {'✅' if health['checks'].get('meta_access_token') else '❌'}\n"
        f"• SQLite: {'✅' if health['checks'].get('sqlite') else '❌'}\n"
        f"• Kill Switch: {'🛑 ACTIVO' if kill_active else '✅ inactivo'}\n\n"
        f"🔧 Servicios:\n"
    )
    for svc, status in svc_status.items():
        emoji = "🟢" if status == "active" else ("🔴" if status == "inactive" else "⚪")
        msg += f"  {emoji} {svc}: {status}\n"

    await update.message.reply_text(msg)


async def cmd_health(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return await _unauthorized(update)
    assert update.message is not None

    import httpx

    checks = {}

    # Bridge health
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(BRIDGE_HEALTH_URL, timeout=5)
            checks["bridge"] = resp.json()
    except Exception as e:
        checks["bridge"] = {"error": str(e)}

    # Dispatcher health (via skill)
    try:
        from skills.dispatcher_skill import get_dispatcher_skill

        get_dispatcher_skill()
        checks["dispatcher"] = {
            "skill_loaded": True,
            "actions": [
                "compute_route",
                "notify_driver",
                "update_delivery",
                "record_gps",
                "check_geofence",
                "get_bottle_inventory",
                "get_heatmap_data",
                "assign_bottle_to_client",
                "return_bottle_from_client",
                "send_bottle_to_wash",
                "confirm_delivery",
                "get_driver_status",
                "delivery_delivered",
                "handle_telegram_update",
            ],
        }
    except Exception as e:
        checks["dispatcher"] = {"error": str(e)}

    # Financial Shield health
    try:
        from src.agents.financial_agent import get_agent

        fs = get_agent()
        fs.init()
        checks["financial"] = {"agent_loaded": True}
    except Exception as e:
        checks["financial"] = {"error": str(e)}

    # WorkloadRouter health
    try:
        from core.workload_router import ROUTE_TABLE

        checks["workload_router"] = {"routes": list(ROUTE_TABLE.keys())}
    except Exception as e:
        checks["workload_router"] = {"error": str(e)}

    # DB checks
    try:
        conn = sqlite3.connect(SQLITE_PATH)
        conv_count = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        conn.close()
        checks["conversations_db"] = {"conversations": conv_count, "ok": True}
    except Exception as e:
        checks["conversations_db"] = {"error": str(e)}

    try:
        conn = sqlite3.connect(DISPATCH_DB)
        clients = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
        bottles = conn.execute("SELECT COUNT(*) FROM bottles").fetchone()[0]
        conn.close()
        checks["dispatch_db"] = {"clients": clients, "bottles": bottles, "ok": True}
    except Exception as e:
        checks["dispatch_db"] = {"error": str(e)}

    msg = "🏥 Health Check Completo\n\n"
    for component, data in checks.items():
        if "error" in data:
            msg += f"🔴 {component}: {data['error']}\n"
        else:
            msg += f"🟢 {component}: OK"
            for k, v in data.items():
                msg += f" | {k}={v}"
            msg += "\n"

    await update.message.reply_text(msg)


async def cmd_memory(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return await _unauthorized(update)
    assert update.message is not None

    args = ctx.args
    if not args:
        try:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.row_factory = sqlite3.Row
            recent = conn.execute(
                "SELECT COUNT(*) as cnt FROM conversations WHERE created_at > ?",
                (datetime.now().timestamp() - 86400,),
            ).fetchone()["cnt"]
            total = conn.execute("SELECT COUNT(*) as cnt FROM conversations").fetchone()["cnt"]
            conn.close()

            vault = Path("/mnt/ssd_trabajo/hermes-agent/docs")
            md_files = list(vault.rglob("*.md")) if vault.exists() else []

            msg = (
                "🧠 Memoria Prometeo\n\n"
                f"📅 Episódica (24h): {recent} conversaciones\n"
                f"📚 Episódica (total): {total} conversaciones\n"
                f"📄 Semántica (vault): {len(md_files)} archivos .md\n\n"
                "Uso: /memory semantic <query>  — buscar en vault\n"
                "     /memory episodic <query> — buscar en conversaciones"
            )
        except Exception as e:
            msg = f"❌ Error leyendo memoria: {e}"
    elif args[0] == "semantic":
        query = " ".join(args[1:]) if len(args) > 1 else ""
        if not query:
            msg = "Uso: /memory semantic <término de búsqueda>"
        else:
            # 1er intento: búsqueda SEMÁNTICA vectorial vía UnifiedMemory (Qdrant).
            # (Integración DT-12/F6: la memoria certificada conectada al bot activo.)
            semantic_hits: list[tuple[float, str, str]] = []
            semantic_failed = False
            try:
                from src.memory.unified_memory import UnifiedMemory

                mem = UnifiedMemory()
                for hit in mem.search(query, limit=5):
                    src = hit.entry.metadata.get("source") or hit.entry.metadata.get("title") or ""
                    semantic_hits.append((hit.score, str(src)[:60], hit.entry.content[:160]))
            except Exception as e:
                logger.warning("Memoria semántica no disponible, fallback a grep: %s", e)
                semantic_failed = True

            if semantic_hits and not semantic_failed:
                msg = f"🔍 Memoria semántica (Qdrant) para '{query}':\n\n"
                for score, src, content in semantic_hits:
                    msg += f"• [{score:.3f}] {src or '(fuente desconocida)'}\n  {content}\n\n"
                if len(msg) > 3500:
                    msg = msg[:3500] + "\n... (truncado)"
            elif semantic_failed:
                msg = "⚠️ Memoria semántica (Qdrant) no disponible; usando búsqueda literal:"
            else:
                msg = ""
            # Fallback: búsqueda literal en vault (comportamiento histórico)
            vault = Path("/mnt/ssd_trabajo/hermes-agent/docs")
            results = []
            for md_file in vault.rglob("*.md"):
                try:
                    content = md_file.read_text()
                    if query.lower() in content.lower():
                        rel = md_file.relative_to(vault)
                        lines = content.split("\n")
                        for i, line in enumerate(lines):
                            if query.lower() in line.lower():
                                snippet = "\n".join(lines[max(0, i - 2) : i + 3])
                                results.append(f"📄 {rel}:\n```\n{snippet}\n```")
                                break
                        if len(results) >= 5:
                            break
                except Exception:
                    pass
            if results:
                msg = msg + "\n\n" + "🔍 Resultados (vault):\n\n" + "\n\n".join(results)
            elif not semantic_hits and not semantic_failed:
                msg = "Sin resultados semánticos ni en vault."
    elif args[0] == "episodic":
        query = " ".join(args[1:]) if len(args) > 1 else ""
        if not query:
            msg = "Uso: /memory episodic <término>"
        else:
            try:
                conn = sqlite3.connect(SQLITE_PATH)
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    (
                        "SELECT phone, user_message, assistant_message, created_at "
                        "FROM conversations "
                        "WHERE user_message LIKE ? OR assistant_message LIKE ? "
                        "ORDER BY created_at DESC LIMIT 10"
                    ),
                    (f"%{query}%", f"%{query}%"),
                ).fetchall()
                conn.close()
                if not rows:
                    msg = "Sin resultados."
                else:
                    msg = f"🔍 Resultados episódicos para '{query}':\n\n"
                    for r in rows:
                        ts = datetime.fromtimestamp(r["created_at"], CARACAS_TZ).strftime(
                            "%m-%d %H:%M"
                        )
                        msg += f"📱 {r['phone'][:8]}... | {ts}\n"
                        msg += f"  U: {r['user_message'][:100]}\n"
                        msg += f"  A: {r['assistant_message'][:100]}\n\n"
            except Exception as e:
                msg = f"❌ Error: {e}"
    else:
        msg = "Subcomandos: semantic, episodic"

    await update.message.reply_text(msg)


async def cmd_skills(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return await _unauthorized(update)
    assert update.message is not None

    args = ctx.args
    skills_dir = Path("/mnt/ssd_trabajo/hermes-agent/.hermes/skills")

    if not args:
        skills = []
        for cat_dir in skills_dir.iterdir():
            if cat_dir.is_dir():
                for skill_file in cat_dir.glob("SKILL.md"):
                    skills.append(f"  • {cat_dir.name}/{skill_file.parent.name}")
        msg = f"📦 Skills disponibles ({len(skills)}):\n\n" + "\n".join(skills)
        msg += "\n\nUso: /skills <nombre> — ver detalle"
    else:
        skill_name = args[0]
        found = None
        for cat_dir in skills_dir.iterdir():
            if cat_dir.is_dir():
                skill_path = cat_dir / skill_name / "SKILL.md"
                if skill_path.exists():
                    found = skill_path
                    break
        if not found:
            for skill_dir in skills_dir.iterdir():
                if skill_dir.is_dir() and skill_dir.name == skill_name:
                    found = skill_dir / "SKILL.md"
                    break

        if found:
            content = found.read_text()
            if len(content) > 3500:
                content = content[:3500] + "\n... (truncado)"
            msg = f"📋 Skill: {skill_name}\n\n{content}"
        else:
            msg = f"❌ Skill '{skill_name}' no encontrado"

    await update.message.reply_text(msg)


async def cmd_review(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return await _unauthorized(update)
    assert update.message is not None

    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                "/mnt/ssd_trabajo/hermes-agent",
                "log",
                "-1",
                "--format=%H %s",
                "--name-only",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        commit_info = result.stdout.strip()
        files_changed = [line for line in commit_info.split("\n")[1:] if line.strip()]

        result = subprocess.run(
            ["git", "-C", "/mnt/ssd_trabajo/hermes-agent", "show", "--stat", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        diff_stat = result.stdout.strip()

        msg = "🔍 Code Review - Último Commit\n\n"
        msg += f"```\n{commit_info.split(chr(10))[0]}\n```\n\n"
        msg += f"📁 Archivos ({len(files_changed)}):\n"
        for f in files_changed[:15]:
            msg += f"  • {f}\n"
        if len(files_changed) > 15:
            msg += f"  ... y {len(files_changed) - 15} más\n"
        msg += f"\n📊 Diff stat:\n```\n{diff_stat}\n```"

    except Exception as e:
        msg = f"❌ Error obteniendo review: {e}"

    await update.message.reply_text(msg)


async def cmd_kill(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Alias para /stop /start - toggle kill switch"""
    if not _is_authorized(update):
        return await _unauthorized(update)
    assert update.message is not None

    if os.path.exists(KILL_SWITCH_FILE):
        await cmd_start(update, ctx)
    else:
        await cmd_stop(update, ctx)


async def cmd_tasa(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return await _unauthorized(update)
    assert update.message is not None

    args = ctx.args
    if not args:
        from src.financial.currency import get_tasa_display

        await update.message.reply_text("💱 Tasa actual: " + get_tasa_display())
        return

    try:
        tasa = float(args[0].replace(",", "."))
        from src.financial.currency import set_manual_rate

        set_manual_rate(tasa)
        await update.message.reply_text(f"✅ Tasa actualizada: 1 EUR = {tasa:.2f} VES")
        logger.info("Tasa manual actualizada por Líder: %.2f", tasa)
    except ValueError:
        await update.message.reply_text("❌ Formato inválido. Usa: /tasa 825.50")


async def cmd_deploy(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return await _unauthorized(update)
    assert update.message is not None

    try:
        result = subprocess.run(
            ["git", "-C", "/mnt/ssd_trabajo/hermes-agent", "log", "--oneline", "-5"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        git_log = result.stdout.strip()

        result = subprocess.run(
            ["git", "-C", "/mnt/ssd_trabajo/hermes-agent", "status", "--short"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        git_status = result.stdout.strip() or "clean"

        msg = (
            "🚀 Estado Deploy\n\n"
            f"📜 Últimos commits:\n```\n{git_log}\n```\n\n"
            f"📝 Working tree:\n```\n{git_status}\n```\n\n"
            "Para rollback: /deploy rollback <commit-hash> (requiere confirmo)"
        )

        if ctx.args and ctx.args[0] == "rollback" and len(ctx.args) > 1:
            if not await _require_confirmation(update, f"Rollback a {ctx.args[1]}"):
                return
            commit_hash = ctx.args[1]
            result = subprocess.run(
                ["git", "-C", "/mnt/ssd_trabajo/hermes-agent", "reset", "--hard", commit_hash],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                msg = (
                    f"✅ Rollback a {commit_hash} completado.\n"
                    "Reinicia servicios con: systemctl restart "
                    "valentina-bridge dispatcher-bot"
                )
            else:
                msg = f"❌ Rollback falló:\n{result.stderr}"

    except Exception as e:
        msg = f"❌ Error: {e}"

    await update.message.reply_text(msg)


async def cmd_logs(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return await _unauthorized(update)
    assert update.message is not None

    service = ctx.args[0] if ctx.args else "valentina-bridge"
    if service not in KNOWN_SERVICES:
        service = "valentina-bridge"

    try:
        result = subprocess.run(
            ["journalctl", "-u", service, "-n", "50", "--no-pager", "-o", "cat"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        logs = result.stdout.strip()
    except Exception as e:
        logs = f"❌ Error: {e}"

    if not logs:
        logs = "📭 Sin logs"

    if len(logs) > 3800:
        logs = logs[-3800:] + "\n... (truncado)"

    await update.message.reply_text(f"📋 Logs: {service}\n\n```\n{logs}\n```")


async def cmd_shell(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return await _unauthorized(update)
    assert update.message is not None

    args = ctx.args
    if not args:
        msg = "🐚 Comandos shell permitidos (read-only):\n\n"
        for key, cmd in ALLOWED_SHELL_COMMANDS.items():
            msg += f"  /shell {key}  —  {cmd}\n"
        msg += "\n⚠️ Solo comandos predefinidos por seguridad."
        await update.message.reply_text(msg)
        return

    cmd_key = args[0]
    if cmd_key not in ALLOWED_SHELL_COMMANDS:
        await update.message.reply_text(
            f"❌ Comando '{cmd_key}' no permitido.\nUsa /shell sin args para ver la lista."
        )
        return

    cmd = ALLOWED_SHELL_COMMANDS[cmd_key]
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=15,
            cwd="/mnt/ssd_trabajo/hermes-agent",
        )
        output = result.stdout.strip()
        if result.stderr:
            output += f"\n\nstderr:\n{result.stderr.strip()}"
        if result.returncode != 0:
            output += f"\n\n⚠️ Exit code: {result.returncode}"
    except subprocess.TimeoutExpired:
        output = "⏱️ Timeout (15s)"
    except Exception as e:
        output = f"❌ Error: {e}"

    if not output:
        output = "(sin salida)"

    if len(output) > 3800:
        output = output[:3800] + "\n... (truncado)"

    await update.message.reply_text(f"🐚 `{cmd}`\n\n```\n{output}\n```")


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return await _unauthorized(update)
    assert update.message is not None

    help_text = (
        "🔥 Prometeo — Bot de Control IA\n\n"
        "📊 Estado & Health:\n"
        "  /status      — Estado bridge + servicios\n"
        "  /health      — Health check completo (bridge, dispatcher, financial, router)\n"
        "  /logs [svc]  — Logs systemd (bridge, dispatcher, telegram-bot, cloudflared)\n\n"
        "🎬 Videos:\n"
        "  /watch <url> — Analizar video YouTube (claude-watch)\n"
        "  (URL de YouTube en mensaje libre también dispara /watch)\n"
        "  /watch-status — Estado pipeline videos\n\n"
        "🧠 Memoria & Skills & Chat:\n"
        "  (mensaje libre) — Chatear con Prometeo (cadena LLM 3 tiers)\n"
        "  /memory      — Resumen memoria (semántica/episódica)\n"
        "  /memory semantic <query>  — Buscar en vault Obsidian\n"
        "  /memory episodic <query>  — Buscar en conversaciones\n"
        "  /skills      — Listar skills\n"
        "  /skills <name>  — Ver skill\n\n"
        "🔍 Code & Deploy:\n"
        "  /review      — Code review último commit\n"
        "  /deploy      — Estado git + rollback opcional\n"
        "  /shell <cmd> — Comandos read-only predefinidos\n\n"
        "🛑 Control:\n"
        "  /start       — Desactivar kill switch\n"
        "  /stop        — Activar kill switch (requiere confirmo)\n"
        "  /kill        — Toggle kill switch\n"
        "  /tasa [valor] — Ver/cambiar tasa EUR/VES\n\n"
        "📋 Aprobaciones Asíncronas:\n"
        "  /pending     — Ver solicitudes pendientes\n"
        "  /approve <id> <respuesta> — Aprobar/ingresar valor\n"
        "  /reject <id> — Rechazar solicitud\n\n"
        "💧 Solo chat_id autorizado (Líder)."
    )
    await update.message.reply_text(help_text)


# Cadena de fallback LLM: glm-5.3-paid → glm-5.2-free → ollama-local (solo chat)
llm = LLMClient()

# Historial de chat libre del Líder con el bot
_CHAT_SYSTEM_PROMPT = (
    "Eres Prometeo, ingeniero senior full-stack que asiste a Luis Martinez "
    "(@elpelon27) en el proyecto Estación H2O Maracaibo. Tono profesional pero "
    "amable, venezolano natural, español de Venezuela. Firma con 💧 los "
    "mensajes importantes. Si no sabes algo, dilo y verifica."
)
_chat_messages: list[dict] = [{"role": "system", "content": _CHAT_SYSTEM_PROMPT}]
_CHAT_MAX_TURNS = 20


async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Chat libre con Prometeo vía cadena LLM de 3 tiers.

    Regla del Líder: Ollama local SOLO para chat conversacional.
    Tareas técnicas sin LLM pagado → rechazo explícito.
    """
    if not _is_authorized(update):
        return await _unauthorized(update)
    msg = update.message
    if msg is None or not msg.text:
        return
    user_input = msg.text.strip()

    # "confirmo" fuera de flujo de confirmación no va al LLM
    if user_input.lower() in ("confirmo", "sí confirmo", "si confirmo"):
        await msg.reply_text('✅ Registrado tu "confirmo" (sin acción pendiente).')
        return

    # URL de YouTube en mensaje libre → trigger /watch
    yt_url = extract_youtube_url(user_input)
    if yt_url:
        ctx.args = yt_url.split()
        return await cmd_watch(update, ctx)

    task_type = detect_task_type(user_input)
    _chat_messages.append({"role": "user", "content": user_input})

    def _call_llm() -> str:
        result = llm.complete(list(_chat_messages), task_type=task_type)
        if "error" in result:
            logger.warning("Tarea técnica rechazada vía Telegram (sin LLM pagado)")
            return (
                "❌ " + result.get("message", "Sin LLM pagado disponible.")
                + "\n\n(Ollama local queda reservado SOLO para chat, "
                "no para tareas técnicas.) 💧"
            )
        content = result["content"]
        _chat_messages.append({"role": "assistant", "content": content})
        # Recortar historial: system + últimos N turnos
        while len(_chat_messages) > 1 + 2 * _CHAT_MAX_TURNS:
            _chat_messages.pop(1)
        return content

    try:
        reply = await asyncio.to_thread(_call_llm)
    except Exception as e:
        logger.error("LLM chain falló en Telegram: %s", e)
        reply = f"❌ Error de la cadena LLM: {e}"
    await msg.reply_text(reply)


# ============================================================
# SISTEMA DE APROBACIONES ASÍNCRONAS
# ============================================================


def _escape_md(text: str) -> str:
    """Escapa caracteres especiales de Markdown v2 para texto normal."""
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in escape_chars else c for c in text)


def _escape_md_inline(text: str) -> str:
    """Escapa para inline code (`...`) - solo backtick y backslash."""
    return text.replace("\\", "\\\\").replace("`", "\\`")


async def _approval_notifier(app: Application[Any, Any, Any, Any, Any, Any]) -> None:
    """Background task que detecta solicitudes pendientes y notifica al Líder."""
    logger.info("Approval notifier iniciado")
    notified_ids = set()

    while True:
        try:
            if not APPROVAL_PENDING_DIR.exists():
                await asyncio.sleep(5)
                continue

            for path in APPROVAL_PENDING_DIR.glob("*.json"):
                try:
                    req_id = path.stem
                    if req_id in notified_ids:
                        continue

                    data = json.loads(path.read_text())

                    type_emoji = {
                        "sudo_password": "🔐",
                        "validation": "✅",
                        "confirmation": "❓",
                        "input": "📝",
                    }.get(data.get("type", ""), "📋")

                    prompt_escaped = _escape_md(data.get("prompt", ""))
                    context_json = json.dumps(data.get("context", {}), indent=2, ensure_ascii=False)
                    created_escaped = _escape_md(data.get("created_at", ""))
                    timeout_escaped = _escape_md(str(data.get("timeout_seconds", 3600)))
                    req_id_inline = _escape_md_inline(req_id)
                    type_escaped = _escape_md(data.get("type", "desconocido"))

                    msg = (
                        f"{type_emoji} *Solicitud de Prometeo* \\("
                        f"`{req_id_inline}`\\)\n\n"
                        f"*Tipo:* {type_escaped}\n"
                        f"*Prompt:* {prompt_escaped}\n"
                    )

                    if data.get("context"):
                        msg += f"\n*Contexto:*\n```json\n{context_json}\n```\n"

                    msg += (
                        f"\n*Creada:* {created_escaped}\n"
                        f"*Timeout:* {timeout_escaped}s\n\n"
                        "👉 Responde con:\n"
                        f"  `/approve {req_id_inline} <respuesta>` \u2014 para aprobar/"
                        f"ingresar valor\n"
                        f"  `/reject {req_id_inline}` \u2014 para rechazar\n"
                        f"  `/pending` \u2014 ver todas las pendientes"
                    )

                    await app.bot.send_message(
                        chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode="MarkdownV2"
                    )

                    notified_ids.add(req_id)
                    logger.info(f"Notificada solicitud {req_id} al Líder")

                except Exception as e:
                    logger.error(f"Error procesando approval {path}: {e}")

            current_ids = {p.stem for p in APPROVAL_PENDING_DIR.glob("*.json")}
            notified_ids &= current_ids

        except Exception as e:
            logger.error(f"Error en approval_notifier: {e}")

        await asyncio.sleep(5)


async def cmd_pending(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Lista solicitudes de aprobación pendientes."""
    if not _is_authorized(update):
        return await _unauthorized(update)
    assert update.message is not None

    if not APPROVAL_PENDING_DIR.exists():
        await update.message.reply_text("📭 Sin solicitudes pendientes")
        return

    pending = []
    for path in APPROVAL_PENDING_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text())
            pending.append(data)
        except Exception:
            pass

    if not pending:
        await update.message.reply_text("📭 Sin solicitudes pendientes")
        return

    msg = f"📋 *Solicitudes Pendientes ({len(pending)})*\n\n"
    for p in sorted(pending, key=lambda x: x.get("created_at", "")):
        type_emoji = {
            "sudo_password": "🔐",
            "validation": "✅",
            "confirmation": "❓",
            "input": "📝",
        }.get(p.get("type", ""), "📋")

        req_id = _escape_md_inline(p.get("id", "?"))
        prompt = _escape_md(p.get("prompt", "")[:80])
        created = _escape_md(p.get("created_at", ""))
        ptype = _escape_md(p.get("type", "?"))

        msg += f"{type_emoji} `{req_id}` [{ptype}]\n   {prompt}...\n   ⏱️ {created}\n\n"

    msg += "Usa `/approve <id> <respuesta>` o `/reject <id>`"
    await update.message.reply_text(msg, parse_mode="MarkdownV2")


async def cmd_approve(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Aprueba una solicitud con respuesta."""
    if not _is_authorized(update):
        return await _unauthorized(update)
    assert update.message is not None

    args = ctx.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "Uso: `/approve <id> <respuesta>`\n"
            "Ejemplos:\n"
            "  `/approve abc12345 mipassword123` (para sudo_password)\n"
            "  `/approve abc12345 sí` (para validation/confirmation)\n"
            "  `/approve abc12345 texto libre` (para input)",
            parse_mode="MarkdownV2",
        )
        return

    req_id = args[0]
    response = " ".join(args[1:])

    pending_path = APPROVAL_PENDING_DIR / f"{req_id}.json"
    if not pending_path.exists():
        await update.message.reply_text(f"❌ Solicitud `{req_id}` no encontrada o ya procesada")
        return

    try:
        data = json.loads(pending_path.read_text())
        data["status"] = "completed"
        data["response"] = response
        data["responded_at"] = datetime.now(UTC).isoformat()

        completed_path = APPROVAL_COMPLETED_DIR / f"{req_id}.json"
        completed_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        pending_path.unlink(missing_ok=True)

        req_id_escaped = _escape_md_inline(req_id)
        await update.message.reply_text(
            f"✅ Solicitud `{req_id_escaped}` completada con respuesta", parse_mode="MarkdownV2"
        )
        logger.info(f"Approval {req_id} completada por Líder: {data.get('type')}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_reject(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Rechaza una solicitud."""
    if not _is_authorized(update):
        return await _unauthorized(update)
    assert update.message is not None

    args = ctx.args or []
    if not args:
        await update.message.reply_text("Uso: `/reject <id>`", parse_mode="MarkdownV2")
        return

    req_id = args[0]
    pending_path = APPROVAL_PENDING_DIR / f"{req_id}.json"
    if not pending_path.exists():
        await update.message.reply_text(f"❌ Solicitud `{req_id}` no encontrada o ya procesada")
        return

    try:
        data = json.loads(pending_path.read_text())
        data["status"] = "rejected"
        data["response"] = None
        data["responded_at"] = datetime.now(UTC).isoformat()

        completed_path = APPROVAL_COMPLETED_DIR / f"{req_id}.json"
        completed_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        pending_path.unlink(missing_ok=True)

        req_id_escaped = _escape_md_inline(req_id)
        await update.message.reply_text(
            f"🚫 Solicitud `{req_id_escaped}` rechazada", parse_mode="MarkdownV2"
        )
        logger.info(f"Approval {req_id} rechazada por Líder")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def _post_init(app: Application[Any, Any, Any, Any, Any, Any]) -> None:
    """Inicializa background tasks tras arrancar el bot."""
    asyncio.create_task(_approval_notifier(app))
    logger.info("Background tasks iniciados")


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN_HERMES no configurado en .env")
        sys.exit(1)

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(_post_init).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("watch", cmd_watch))
    app.add_handler(CommandHandler("watch-status", cmd_watch_status))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("health", cmd_health))
    app.add_handler(CommandHandler("memory", cmd_memory))
    app.add_handler(CommandHandler("skills", cmd_skills))
    app.add_handler(CommandHandler("review", cmd_review))
    app.add_handler(CommandHandler("kill", cmd_kill))
    app.add_handler(CommandHandler("tasa", cmd_tasa))
    app.add_handler(CommandHandler("deploy", cmd_deploy))
    app.add_handler(CommandHandler("logs", cmd_logs))
    app.add_handler(CommandHandler("shell", cmd_shell))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("pending", cmd_pending))
    app.add_handler(CommandHandler("approve", cmd_approve))
    app.add_handler(CommandHandler("reject", cmd_reject))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Prometeo Telegram Bot iniciado. Líder chat_id=%s", TELEGRAM_CHAT_ID)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
