#!/usr/bin/env python3
"""Comandos de clasificación de clientes (plan de peso) — @Skynet_27_bot.

Se integra como módulo: telegram_bot.py llama register_client_handlers(app).
Guard: SOLO el chat_id del Líder (TELEGRAM_CHAT_ID=1663148211).

NIVELES DEL LÍDER:
  NIVEL 1 (CRÍTICO AUTOMÁTICO): restaurante, clinica, escuela
    → is_priority=1, is_automatic=1. Reparto diario obligatorio;
      lunes duplica botellones (domingo no se atiende).
  NIVEL 2 (PESO ON-DEMAND): gimnasio, hotel, condominios, farmacias,
    talleres, comercios, empresa → is_priority=1, is_automatic=0.
  NIVEL 3 (RESIDENCIAL): residencial → is_priority=0, is_automatic=0.

Comandos:
  /set_peso <telefono> <tipo> [notas]
  /unset_peso <telefono>
  /list_peso
  /list_tipo <tipo>
  /client_info <telefono>
"""
import os
import sys
from pathlib import Path
from typing import Any

_REPO = Path("/mnt/ssd_trabajo/hermes-agent")
sys.path.insert(0, str(_REPO / "scripts" / "security"))

import audit_logger as al  # noqa: E402

DISPATCH_DB = os.getenv(
    "DISPATCH_DB_PATH", "/mnt/ssd_trabajo/hermes-agent/data/dispatch.db"
)

# Tipos válidos (11) → nivel
NIVEL_1 = ("restaurante", "clinica", "escuela")
NIVEL_2 = (
    "gimnasio", "hotel", "condominios", "farmacias",
    "talleres", "comercios", "empresa",
)
TIPOS_VALIDOS = NIVEL_1 + NIVEL_2 + ("residencial",)


def _norm_phone(phone: str) -> str:
    import re
    return re.sub(r"\D", "", str(phone or ""))


def _authorized(update: Any) -> bool:  # noqa: ANN001
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "1663148211")
    try:
        allowed = int(chat_id)
    except ValueError:
        allowed = 1663148211
    if update.effective_chat and update.effective_chat.id == allowed:
        return True
    al.log_event(
        "intento_fallo_acceso",
        phone=None,
        details={
            "origen": "telegram_comando_clientes",
            "chat_id": (
                update.effective_chat.id if update.effective_chat else None
            ),
        },
        action_taken="rechazado",
    )
    return False


async def _reply(update: Any, context: Any, text: str) -> None:
    await update.message.reply_text(text)


def _arg(context: Any, n: int, default: Any = None) -> Any:
    try:
        v = context.args[n]
        return v if v else default
    except (IndexError, TypeError):
        return default


def _level_of(tipo: str) -> int:
    if tipo in NIVEL_1:
        return 1
    if tipo in NIVEL_2:
        return 2
    return 3


def _find_client_row(phone: str) -> Any:
    """Busca cliente por phone exacto/dígitos. Devuelve sqlite3.Row o None."""
    import sqlite3

    d = _norm_phone(phone)
    if not d:
        return None
    conn = sqlite3.connect(DISPATCH_DB)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM clients WHERE phone = ? OR phone = ? OR phone = ?",
        (phone, f"+{d}", d),
    ).fetchone()
    if not row:
        row = conn.execute(
            "SELECT * FROM clients WHERE phone LIKE ?",
            (f"%{d}%",),
        ).fetchone()
    conn.close()
    return row


def _apply_peso(client_id: int, tipo: str, notas: str | None) -> int:
    """Escribe client_type/is_priority/is_automatic/priority_notes.

    Devuelve el nivel asignado (1, 2 o 3).
    """
    import sqlite3

    nivel = _level_of(tipo)
    is_priority = 1 if nivel in (1, 2) else 0
    is_automatic = 1 if nivel == 1 else 0
    conn = sqlite3.connect(DISPATCH_DB)
    conn.execute(
        "UPDATE clients SET client_type = ?, is_priority = ?, "
        "is_automatic = ?, priority_notes = ?, "
        "updated_at = strftime('%s','now') WHERE id = ?",
        (tipo, is_priority, is_automatic, notas, client_id),
    )
    conn.commit()
    conn.close()
    return nivel


# ---- comandos ------------------------------------------------------------


async def cmd_set_peso(update: Any, context: Any) -> None:
    """/set_peso <telefono> <tipo> [notas]"""
    if not _authorized(update):
        return
    phone = _arg(context, 0)
    tipo = (_arg(context, 1) or "").lower()
    notas = " ".join(context.args[2:]) if len(context.args) > 2 else None
    if not phone or not tipo:
        await _reply(
            update, context,
            "Uso: /set_peso <telefono> <tipo> [notas]\n"
            f"Tipos: {', '.join(TIPOS_VALIDOS)}",
        )
        return
    if tipo not in TIPOS_VALIDOS:
        await _reply(
            update, context,
            f"❌ Tipo '{tipo}' inválido. Tipos: {', '.join(TIPOS_VALIDOS)}",
        )
        return
    row = _find_client_row(phone)
    if not row:
        al.log_event(
            "operador_decision", phone=phone,
            details={"cmd": "set_peso", "tipo": tipo,
                     "error": "cliente no existe"},
            action_taken="rechazado", operator_decision="Líder",
        )
        await _reply(update, context,
                     f"❌ Cliente {phone} no existe en dispatch.db.")
        return
    nivel = _apply_peso(row["id"], tipo, notas)
    modo = "Automático" if nivel == 1 else (
        "On-Demand" if nivel == 2 else "Residencial"
    )
    al.log_event(
        "operador_decision", phone=phone,
        details={"cmd": "set_peso", "tipo": tipo, "nivel": nivel,
                 "notas": notas, "client_id": row["id"]},
        action_taken=f"nivel_{nivel}_asignado", operator_decision="Líder",
    )
    await _reply(
        update, context,
        f"✅ Cliente {phone} marcado como NIVEL {nivel} ({tipo}). {modo}.",
    )


async def cmd_unset_peso(update: Any, context: Any) -> None:
    """/unset_peso <telefono> — quita prioridad sin tocar client_type."""
    if not _authorized(update):
        return
    phone = _arg(context, 0)
    if not phone:
        await _reply(update, context, "Uso: /unset_peso <telefono>")
        return
    row = _find_client_row(phone)
    if not row:
        await _reply(update, context,
                     f"❌ Cliente {phone} no existe en dispatch.db.")
        return
    import sqlite3

    conn = sqlite3.connect(DISPATCH_DB)
    conn.execute(
        "UPDATE clients SET is_priority = 0, is_automatic = 0, "
        "priority_notes = NULL, updated_at = strftime('%s','now') "
        "WHERE id = ?",
        (row["id"],),
    )
    conn.commit()
    conn.close()
    al.log_event(
        "operador_decision", phone=phone,
        details={"cmd": "unset_peso", "client_id": row["id"]},
        action_taken="prioridad_quitada", operator_decision="Líder",
    )
    await _reply(update, context,
                 f"✅ Cliente {phone} quitado de prioridad.")


async def cmd_list_peso(update: Any, context: Any) -> None:
    """/list_peso — tabla de clientes prioritarios por nivel."""
    if not _authorized(update):
        return
    import sqlite3

    conn = sqlite3.connect(DISPATCH_DB)
    conn.row_factory = sqlite3.Row
    n1 = conn.execute(
        "SELECT phone, name, client_type, priority_notes FROM clients "
        "WHERE is_priority = 1 AND is_automatic = 1 ORDER BY name"
    ).fetchall()
    n2 = conn.execute(
        "SELECT phone, name, client_type, priority_notes FROM clients "
        "WHERE is_priority = 1 AND is_automatic = 0 ORDER BY name"
    ).fetchall()
    conn.close()

    lines = ["🚚 NIVEL 1 — Automáticos (reparto diario, lunes x2):"]
    if n1:
        for r in n1:
            nota = f" — {r['priority_notes']}" if r["priority_notes"] else ""
            lines.append(f"  📍 {r['name'] or r['phone']} ({r['client_type']}){nota}")
    else:
        lines.append("  (ninguno)")
    lines.append("")
    lines.append("📦 NIVEL 2 — On-Demand (prioridad al pedir):")
    if n2:
        for r in n2:
            nota = f" — {r['priority_notes']}" if r["priority_notes"] else ""
            lines.append(f"  📍 {r['name'] or r['phone']} ({r['client_type']}){nota}")
    else:
        lines.append("  (ninguno)")
    await _reply(update, context, "\n".join(lines))


async def cmd_list_tipo(update: Any, context: Any) -> None:
    """/list_tipo <tipo>"""
    if not _authorized(update):
        return
    tipo = (_arg(context, 0) or "").lower()
    if tipo not in TIPOS_VALIDOS:
        await _reply(
            update, context,
            f"❌ Tipo '{tipo}' inválido. Tipos: {', '.join(TIPOS_VALIDOS)}",
        )
        return
    import sqlite3

    conn = sqlite3.connect(DISPATCH_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT phone, name, is_priority, is_automatic, priority_notes "
        "FROM clients WHERE client_type = ? ORDER BY name",
        (tipo,),
    ).fetchall()
    conn.close()
    if not rows:
        await _reply(update, context, f"No hay clientes de tipo '{tipo}'.")
        return
    lines = [f"📋 Clientes tipo '{tipo}':"]
    for r in rows:
        nivel = "N1-auto" if r["is_automatic"] else (
            "N2-ondemand" if r["is_priority"] else "N3"
        )
        nota = f" — {r['priority_notes']}" if r["priority_notes"] else ""
        lines.append(f"  📍 {r['name'] or r['phone']} [{nivel}]{nota}")
    await _reply(update, context, "\n".join(lines))


async def cmd_client_info(update: Any, context: Any) -> None:
    """/client_info <telefono> — ficha completa del cliente."""
    if not _authorized(update):
        return
    phone = _arg(context, 0)
    if not phone:
        await _reply(update, context, "Uso: /client_info <telefono>")
        return
    row = _find_client_row(phone)
    if not row:
        await _reply(update, context,
                     f"❌ Cliente {phone} no existe en dispatch.db.")
        return
    nivel = "NIVEL 1 (Automático, lunes x2)" if row["is_automatic"] else (
        "NIVEL 2 (On-Demand)" if row["is_priority"] else "NIVEL 3 (Residencial)"
    )
    coords = (
        f"{row['lat']:.5f}, {row['lng']:.5f}"
        if row["lat"] is not None and row["lng"] is not None
        else "sin GPS"
    )
    lines = [
        f"👤 {row['name'] or '(sin nombre)'}",
        f"📞 {row['phone']}",
        f"🏷 Tipo: {row['client_type']}",
        f"⚖️ Nivel: {nivel}",
        f"📍 Coordenadas: {coords}",
        f"🏠 Dirección: {row['address_text'] or '(sin dirección)'}",
        f"🚚 Visita promedio: {row['avg_bottles_per_visit']} botellones",
        f"🗺 Zona: {row['zone_id']}",
        f"📝 Notas: {row['priority_notes'] or '(ninguna)'}",
    ]
    await _reply(update, context, "\n".join(lines))


# ---- registro ------------------------------------------------------------


def register_client_handlers(app: Any) -> int:
    """Registra los comandos de clasificación en la app de telegram_bot.py."""
    from telegram.ext import CommandHandler

    cmds = {
        "set_peso": cmd_set_peso,
        "unset_peso": cmd_unset_peso,
        "list_peso": cmd_list_peso,
        "list_tipo": cmd_list_tipo,
        "client_info": cmd_client_info,
        "resumen": cmd_resumen,
        "revoke_vehicle": cmd_revoke_vehicle,
        "activate_vehicle": cmd_activate_vehicle,
        "reset_pin": cmd_reset_pin,
    }
    for name, fn in cmds.items():
        app.add_handler(CommandHandler(name, fn))
    return len(cmds)


async def cmd_resumen(update: Any, context: Any) -> None:
    """/resumen <telefono> — estado de cuenta del cliente (Bloque 4 Fase 4.3).

    Genera el resumen semanal de crédito al instante (on-demand) y opcionalmente
    lo envía al cliente por WhatsApp (Valentina, Meta Cloud API) con /resumen <tel> send.
    """
    if not _authorized(update):
        return
    phone = _arg(context, 0)
    if not phone:
        await _reply(update, context, "Uso: /resumen <telefono> [send]")
        return
    from scripts.credit_summary import generate_weekly_summary, send_summary_via_valentina

    summary = generate_weekly_summary(phone)
    if not summary:
        await _reply(update, context, f"✅ {phone}: sin pedidos pendientes.")
        return
    if len(context.args) > 1 and context.args[1] == "send":  # type: ignore[index]
        ok = send_summary_via_valentina(phone, summary)
        await _reply(
            update, context,
            f"{'✅ Enviado' if ok else '❌ Falló el envío'} a {phone}:\n\n{summary}",
        )
    else:
        hint = f"(preview — usa '/resumen {phone} send' para enviar)\n\n{summary}"
        await _reply(update, context, hint)


# ---- Kill-switch revocable PWA (Bloque 5, Fase 5.1) ------------------------


async def cmd_revoke_vehicle(update: Any, context: Any) -> None:
    """/revoke_vehicle <vehicle_id> — revoca el token del vehículo.

    La PWA deja de funcionar para ese vehículo (403) y sus PODs offline
    sin sincronizar quedan marcados como 'compromised' (validación manual).
    """
    if not _authorized(update):
        return
    vid = _arg(context, 0)
    if not vid or not vid.isdigit():
        await _reply(update, context, "Uso: /revoke_vehicle <vehicle_id>")
        return
    from api.pod_router import revoke_vehicle

    n = revoke_vehicle(int(vid))
    await _reply(
        update, context,
        f"⚠️ Vehículo {vid} revocado. PWA desactivada.\n"
        f"{n} POD(s) offline marcados como comprometidos.",
    )


async def cmd_activate_vehicle(update: Any, context: Any) -> None:
    """/activate_vehicle <vehicle_id> — reactiva el token del vehículo."""
    if not _authorized(update):
        return
    vid = _arg(context, 0)
    if not vid or not vid.isdigit():
        await _reply(update, context, "Uso: /activate_vehicle <vehicle_id>")
        return
    from api.pod_router import activate_vehicle

    ok = activate_vehicle(int(vid))
    if ok:
        await _reply(update, context, f"✅ Vehículo {vid} reactivado.")
    else:
        await _reply(update, context, f"ℹ️ Vehículo {vid} no estaba revocado.")


async def cmd_reset_pin(update: Any, context: Any) -> None:
    """/reset_pin <vehicle_id> — resetea intentos fallidos de PIN y desbloquea."""
    if not _authorized(update):
        return
    vid = _arg(context, 0)
    if not vid or not vid.isdigit():
        await _reply(update, context, "Uso: /reset_pin <vehicle_id>")
        return
    from api.pod_router import reset_pin

    reset_pin(int(vid))
    await _reply(update, context, f"🔓 PIN del vehículo {vid} desbloqueado (intentos en 0).")
