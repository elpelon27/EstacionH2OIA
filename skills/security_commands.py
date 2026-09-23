#!/usr/bin/env python3
"""Comandos de seguridad del operador (@Skynet_27_bot) — FASE 4.

Se integra como módulo: telegram_bot.py llama register_security_handlers(app).
Guard: SOLO el chat_id del Líder (TELEGRAM_CHAT_ID=1663148211) puede usarlos.

Comandos:
  /blacklist_add <phone> <reason> [permanent]
  /blacklist_remove <phone>
  /block <phone>            (1h)
  /unblock <phone>
  /observe <phone>
  /credit_client <phone>    (marca cliente con crédito — pedido sin pagar NO es ofensa)
  /cliente_info <phone>     (historial completo)
  /ataque_detectado         (ataques recientes)
  /lockdown_status
  /lockdown_release         (solo operador — saca del lockdown)
  /stats                    (estadísticas del día)
"""
import json
import sys
import time
from pathlib import Path

_REPO = Path("/mnt/ssd_trabajo/hermes-agent")
sys.path.insert(0, str(_REPO / "scripts" / "security"))

import audit_logger as al  # noqa: E402
import attack_detector as ad  # noqa: E402
import geofence as gf  # noqa: E402
import rate_limiter as rl  # noqa: E402


def _ts_fmt(ts: float) -> str:
    from datetime import datetime
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


# ---- guard ---------------------------------------------------------------

def _authorized(update) -> bool:
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "1663148211")
    try:
        allowed = int(chat_id)
    except ValueError:
        allowed = 1663148211
    if update.effective_chat and update.effective_chat.id == allowed:
        return True
    al.log_event("intento_fallo_acceso",
                 phone=None,
                 details={"origen": "telegram_comando_seguridad",
                          "chat_id": update.effective_chat.id if update.effective_chat else None},
                 action_taken="rechazado")
    return False


import os  # noqa: E402  (usado en _authorized)


# ---- helpers --------------------------------------------------------------

async def _reply(update, context, text: str):
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text[:4000])


def _arg(context, n, default=None):
    try:
        return context.args[n]
    except (IndexError, TypeError):
        return default


# ---- comandos -------------------------------------------------------------

async def cmd_blacklist_add(update, context):
    if not _authorized(update):
        return
    phone = _arg(context, 0)
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "razón no especificada"
    permanent = "permanent" in context.args or "permanente" in context.args
    if not phone:
        await _reply(update, context, "Uso: /blacklist_add <phone> <reason> [permanent]")
        return
    rl.add_to_blacklist(phone, reason, permanent=permanent)
    al.log_event("operador_decision", phone=phone,
                 details={"cmd": "blacklist_add", "reason": reason, "permanent": permanent},
                 action_taken="blacklisted", operator_decision="Líder")
    await _reply(update, context, f"🔒 +{phone} agregado a blacklist "
            f"({'permanente' if permanent else 'temporal 1h'}).\nRazón: {reason}")


async def cmd_blacklist_remove(update, context):
    if not _authorized(update):
        return
    phone = _arg(context, 0)
    if not phone:
        await _reply(update, context, "Uso: /blacklist_remove <phone>")
        return
    ok = rl.remove_from_blacklist(phone)
    al.log_event("operador_decision", phone=phone,
                 details={"cmd": "blacklist_remove"},
                 action_taken="removed" if ok else "not_found",
                 operator_decision="Líder")
    await _reply(update, context, f"✅ blacklist limpiada para {phone}" if ok
           else f"⚠️ {phone} no estaba en blacklist")


async def cmd_block(update, context):
    if not _authorized(update):
        return
    phone = _arg(context, 0)
    if not phone:
        await _reply(update, context, "Uso: /block <phone> (bloqueo 1h)")
        return
    rl.add_to_blacklist(phone, "bloqueo manual operador", permanent=False)
    al.log_event("cliente_bloqueado", phone=phone,
                 details={"cmd": "block", "duracion": "1h"}, action_taken="bloqueo_1h",
                 operator_decision="Líder")
    await _reply(update, context, f"🔇 {phone} silenciado 1h (bloqueo manual).")


async def cmd_unblock(update, context):
    if not _authorized(update):
        return
    phone = _arg(context, 0)
    if not phone:
        await _reply(update, context, "Uso: /unblock <phone>")
        return
    ok = rl.remove_from_blacklist(phone)
    al.log_event("operador_decision", phone=phone, details={"cmd": "unblock"},
                 action_taken="unblocked" if ok else "not_found", operator_decision="Líder")
    await _reply(update, context, "🔓 desbloqueado." if ok else "⚠️ no estaba bloqueado.")


async def cmd_observe(update, context):
    if not _authorized(update):
        return
    phone = _arg(context, 0)
    if not phone:
        await _reply(update, context, "Uso: /observe <phone>")
        return
    al.log_event("cliente_observacion", phone=phone,
                 details={"cmd": "observe"}, action_taken="observado",
                 operator_decision="Líder")
    await _reply(update, context, f"👁 {phone} bajo observación.")


async def cmd_credit_client(update, context):
    if not _authorized(update):
        return
    phone = _arg(context, 0)
    if not phone:
        await _reply(update, context, "Uso: /credit_client <phone> — marca cliente con crédito")
        return
    ad.mark_registered(phone)
    al.log_event("operador_decision", phone=phone,
                 details={"cmd": "credit_client", "nota": "cliente con crédito — "
                          "pedido sin pagar NO cuenta como ofensa"},
                 action_taken="marcado_credito", operator_decision="Líder")
    await _reply(update, context, f"💳 {phone} marcado como cliente con crédito (conocido).")


async def cmd_cliente_info(update, context):
    if not _authorized(update):
        return
    phone = _arg(context, 0)
    if not phone:
        await _reply(update, context, "Uso: /cliente_info <phone>")
        return
    import re
    d = re.sub(r"\D", "", str(phone))
    lines = [f"📱 Cliente {phone} (hash dígitos: {d[:4]}...)"]
    # blacklist
    c = rl._conn()
    row = c.execute("SELECT reason, blocked_at, is_permanent, expires_at "
                    "FROM blacklist_phone WHERE phone=?", (d,)).fetchone()
    c.close()
    if row:
        lines.append(f"🔒 Blacklist: {'PERMANENTE' if row['is_permanent'] else 'temporal'}"
                     f" | razón: {row['reason']}"
                     f" | desde {_ts_fmt(row['blocked_at'])}")
    else:
        lines.append("✅ No está en blacklist")
    # ofensas
    n_off = rl.count_offenses(d)
    lines.append(f"⚖️ Ofensas (24h): {n_off}")
    # conocido
    lines.append(f"📌 Conocido/registrado: {'sí' if ad.is_known_number(d) else 'no'}")
    # audit historial
    evs = al.get_events(phone=d, limit=10)
    lines.append(f"🗂 Últimos {len(evs)} eventos de auditoría:")
    for e in evs:
        lines.append(f"  • {_ts_fmt(e['timestamp'])} {e['event_type']} "
                     f"{e['action_taken'] or ''}")
    await _reply(update, context, "\n".join(lines))


async def cmd_ataque_detectado(update, context):
    if not _authorized(update):
        return
    atks = ad.recent_attacks(15)
    if not atks:
        await _reply(update, context, "Sin ataques registrados 🛡")
        return
    lines = [f"🚨 Ataques recientes ({len(atks)}):"]
    for a in atks:
        det = json.loads(a["details_json"]) if a["details_json"] else {}
        extra = ""
        if "numeros" in det:
            extra = f" → {len(det['numeros'])} números"
        if "valor" in det:
            extra = f" → {det['valor']}"
        lines.append(f"  • {_ts_fmt(a['detected_at'])} {a['attack_type']}{extra}")
    await _reply(update, context, "\n".join(lines))


async def cmd_lockdown_status(update, context):
    if not _authorized(update):
        return
    active = ad.is_lockdown()
    reason = ad._state_get("lockdown_reason")
    d, h, m = ad.mensajes_por_dia(), ad.mensajes_por_hora(), ad.mensajes_por_minuto()
    await _reply(update, context,
           f"🔒 Lockdown: {'ACTIVO' if active else 'inactivo'}"
           f"{f' — motivo: {reason}' if active and reason else ''}\n"
           f"📊 Volúmenes: {m}/min · {h}/hora · {d}/día "
           f"(límites 29/100/700)")


async def cmd_lockdown_release(update, context):
    if not _authorized(update):
        return
    ad.release_lockdown("operador")
    al.log_event("operador_decision", details={"cmd": "lockdown_release"},
                 action_taken="lockdown_liberado", operator_decision="Líder")
    await _reply(update, context, "🔓 Lockdown liberado por el operador. "
           "Nota: si el volumen diario sigue ≥700, se re-activará automáticamente.")


async def cmd_stats(update, context):
    if not _authorized(update):
        return
    day_start = time.time() - 86400
    evs = al.get_events(since=day_start, limit=10000)
    from collections import Counter
    cc = Counter(e["event_type"] for e in evs)
    d, h, m = ad.mensajes_por_dia(), ad.mensajes_por_hora(), ad.mensajes_por_minuto()
    nuevos = ad.numeros_nuevos_en_10min()
    fut = gf.future_zone_notify_pending()
    await _reply(update, context,
           "📊 ESTADÍSTICAS (24h)\n"
           f"• Mensajes: {m}/min · {h}/h · {d}/día\n"
           f"• Números nuevos (10min): {nuevos}\n"
           f"• Bloqueos: {cc.get('cliente_bloqueado', 0)}\n"
           f"• Observaciones: {cc.get('cliente_observacion', 0)}\n"
           f"• Ataques detectados: {cc.get('ataque_coordinado_detectado', 0)}\n"
           f"• Pagos confirmados: {cc.get('pago_confirmado', 0)}\n"
           f"• Decisiones operador: {cc.get('operador_decision', 0)}\n"
           f"• Intentos fallo acceso: {cc.get('intento_fallo_acceso', 0)}\n"
           f"• Fuera de zona (aparte, no audit): {len(fut)}")


# ---- registro ------------------------------------------------------------

def register_security_handlers(app):
    """Registra todos los comandos de seguridad en la app de telegram_bot.py."""
    # wiring: asegurar esquema DB antes del primer comando
    rl.init_db()
    ad.init_db()
    al.init_db()
    gf.init_db()
    from telegram.ext import CommandHandler
    cmds = {
        "blacklist_add": cmd_blacklist_add,
        "blacklist_remove": cmd_blacklist_remove,
        "block": cmd_block,
        "unblock": cmd_unblock,
        "observe": cmd_observe,
        "credit_client": cmd_credit_client,
        "cliente_info": cmd_cliente_info,
        "ataque_detectado": cmd_ataque_detectado,
        "lockdown_status": cmd_lockdown_status,
        "lockdown_release": cmd_lockdown_release,
        "stats": cmd_stats,
    }
    for name, fn in cmds.items():
        app.add_handler(CommandHandler(name, fn))
    return len(cmds)
