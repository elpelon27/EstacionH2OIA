#!/usr/bin/env python3
"""
============================================================================
Whatsscanbot — Bot de Telegram para importar chats de WhatsApp
Estación H2O · DT-WSIMPORT 2F
============================================================================

El Líder exporta chats de WhatsApp (.zip / .txt / texto pegado) y el bot
los procesa: parseo regex (sin LLM), dedup por hash, SQLite whatsapp_bot.db,
indexado Qdrant, UPSERT clients en dispatch.db, detección de producción y
resumen con DeepSeek V4 Flash (OpenRouter) con cadena de fallback propia.

Seguridad:
    SOLO el chat_id del Líder (WHATSSCAN_AUTHORIZED_CHAT_ID) tiene permiso.
    Rate limit: 1 import cada WHATSSCAN_RATE_LIMIT_SECONDS.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path

import indexer as ix
import llm_client
import parser as wsp
from production_detector import detect_batch
from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import db as wdb

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("whatsscan.bot")

ROOT = Path("/mnt/ssd_trabajo/hermes-agent")
RAW_DIR = ROOT / "data" / "whatsapp_exports" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

ENV_PATH = ROOT / "config" / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

TOKEN = os.environ.get("WHATSSCAN_BOT_TOKEN", "")
AUTHORIZED_CHAT_ID = int(os.environ.get("WHATSSCAN_AUTHORIZED_CHAT_ID", "1663148211"))
RATE_LIMIT_S = int(os.environ.get("WHATSSCAN_RATE_LIMIT_SECONDS", "30"))
MAX_FILE_MB = 50

_last_import_ts: float = 0.0


# ── Auth ───────────────────────────────────────────────────────────────

def _is_authorized(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.id == AUTHORIZED_CHAT_ID)


async def _unauthorized(update: Update) -> None:
    msg = update.message
    chat = update.effective_chat
    user = update.effective_user
    if msg and chat:
        await msg.reply_text("🚫 No autorizado. Bot privado de Estación H2O.")
    logger.warning("Acceso NO autorizado: chat_id=%s user=%s",
                    chat.id if chat else "?", user.username if user else "?")


# ── Comandos ───────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        await _unauthorized(update)
        return
    await update.message.reply_text(
        "💧 *Whatsscanbot* — Estación H2O\n\n"
        "Importador de chats de WhatsApp.\n\n"
        "Enviame un export y lo proceso:\n"
        "• Archivo .zip (export completo de WhatsApp)\n"
        "• Archivo .txt con el contenido del chat\n"
        "• Texto pegado (precedido de /import)\n\n"
        "Comandos:\n"
        "/import — activar modo pegado de texto\n"
        "/status — estado del bot\n"
        "/list — últimos imports\n"
        "/search <q> — búsqueda semántica\n"
        "/contact <tel> — datos de un contacto\n"
        "/production — pedidos/pagos/problemas detectados",
        parse_mode="Markdown",
    )


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        await _unauthorized(update)
        return
    try:
        imports = wdb.list_imports(limit=1000)
        n_msgs = 0
        with wdb._conn() as c:  # noqa: SLF001
            row = c.execute("SELECT COUNT(*) FROM whatsapp_messages").fetchone()
            n_msgs = row[0] if row else 0
        qd = "OK" if ix.client().collection_exists(ix.COLLECTION) else "SIN collection"
        await update.message.reply_text(
            f"🟢 Whatsscanbot operativo\n"
            f"Imports totales: {len(imports)}\n"
            f"Mensajes indexados (SQLite): {n_msgs}\n"
            f"Qdrant {ix.COLLECTION}: {qd}\n"
            f"LLM primario: {llm_client.DEFAULT_CHAIN[0][0]}"
        )
    except Exception as e:  # noqa: BLE001
        await update.message.reply_text(f"🔴 Error en status: {e}")


async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        await _unauthorized(update)
        return
    rows = wdb.list_imports(limit=15)
    if not rows:
        await update.message.reply_text("Sin imports todavía.")
        return
    lines = ["📋 Últimos imports:"]
    for r in rows:
        lines.append(
            f"#{r['id']} [{r['source_type']}] {r['contact_name'] or '?'} "
            f"({r['contact_phone'] or 's/tel'}) — {r['message_count']} msgs "
            f"{r['period_start'] or ''}→{r['period_end'] or ''}"
        )
    await update.message.reply_text("\n".join(lines))


async def cmd_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        await _unauthorized(update)
        return
    query = " ".join(ctx.args) if ctx.args else ""
    if not query:
        await update.message.reply_text("Uso: /search <consulta>")
        return
    try:
        hits = ix.search(query, limit=5)
        if not hits:
            hits = wdb.search_messages(query, limit=5)
        if not hits:
            await update.message.reply_text("Sin resultados.")
            return
        lines = [f"🔎 '{query}':"]
        for h in hits:
            msg = h.get("message", h.get("message_text", ""))
            phone = h.get("phone", "?")
            score = h.get("score", "")
            lines.append(f"• [{phone}] {msg[:150]} {f'({score:.2f})' if score else ''}")
        await update.message.reply_text("\n".join(lines)[:4000])
    except Exception as e:  # noqa: BLE001
        await update.message.reply_text(f"🔴 Error búsqueda: {e}")


async def cmd_contact(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        await _unauthorized(update)
        return
    if not ctx.args:
        await update.message.reply_text("Uso: /contact <teléfono>")
        return
    phone = wsp.normalize_phone(ctx.args[0]) or ctx.args[0]
    c = wdb.get_contact(phone)
    if not c:
        await update.message.reply_text(f"Sin datos de {phone}.")
        return
    await update.message.reply_text(
        f"👤 {c['name'] or 'sin nombre'} ({c['phone']})\n"
        f"Mensajes: {c['total_messages']}\n"
        f"Primera: {c['first_seen_at'] or '?'}  Última: {c['last_seen_at'] or '?'}\n"
        f"Cliente dispatch: {'sí (#%s)' % c['client_id'] if c['is_client'] else 'no'}"
    )


async def cmd_production(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        await _unauthorized(update)
        return
    rows = wdb.list_imports(limit=50)
    if not rows:
        await update.message.reply_text("Sin imports todavía.")
        return
    lines = ["🏭 Producción detectada (últimos imports):"]
    with wdb._conn() as c:  # noqa: SLF001
        c.row_factory = None
        for r in rows[:10]:
            cur = c.execute(
                "SELECT message_text FROM whatsapp_messages "
                "WHERE import_id=? AND message_type='text'", (r["id"],),
            )
            agg = detect_batch([{"message_text": row[0]} for row in cur.fetchall()])
            lines.append(
                f"#{r['id']} {r['contact_name'] or '?'}: "
                f"pedidos={agg['pedidos']} pagos={agg['pagos']} "
                f"entregas={agg['entregas']} problemas={agg['problemas']} "
                f"montos={agg['montos']}"
            )
    await update.message.reply_text("\n".join(lines)[:4000])


# ── Import pipeline ────────────────────────────────────────────────────

def _process_export(source_type: str, source_name: str, raw: bytes | str,
                    export) -> str:
    """Procesa un ChatExport. Devuelve el reporte de texto para el Líder."""
    phone = export.contact_phone
    msgs_data = []
    for m in export.messages:
        msgs_data.append({
            "phone": phone,
            "sender_name": m.sender,
            "message_text": m.text,
            "timestamp": m.timestamp,
            "direction": m.direction,
            "message_type": m.message_type,
            "media_path": m.media_path,
            "msg_hash": m.msg_hash,
        })
    text_repr = raw if isinstance(raw, str) else raw.decode("utf-8", errors="replace")
    fhash = hashlib.sha256(text_repr.encode("utf-8", errors="replace")).hexdigest()

    if wdb.get_import_by_hash(fhash):
        return "♻️ Import duplicado (hash ya existente) — no se procesó."

    import_id = wdb.insert_import(phone, export.contact_name, source_type,
                                  fhash, text_repr[:500])
    inserted = sum(1 for md in msgs_data if wdb.insert_message(import_id, md) is not None)
    ts_list = [m["timestamp"] for m in msgs_data if m["timestamp"]]
    wdb.finalize_import(import_id, inserted,
                        min(ts_list) if ts_list else None,
                        max(ts_list) if ts_list else None)
    wdb.upsert_contact(phone, export.contact_name,
                       min(ts_list) if ts_list else None,
                       max(ts_list) if ts_list else None, inserted)
    try:
        ix.index_messages(import_id, msgs_data)
    except Exception as e:  # noqa: BLE001
        logger.warning("Qdrant falló (import sigue en SQLite): %s", e)

    production = detect_batch(msgs_data)
    summary_txt = ""
    tier = ""
    try:
        s = llm_client.summarize_chat(export.contact_name, phone,
                                      msgs_data, production)
        wdb.set_import_summary(import_id, {"raw": s["summary"], "tier": s["tier"]})
        summary_txt = s["summary"][:1500]
        tier = f"\n🧠 Resumen ({s['tier']}):"
    except Exception as e:  # noqa: BLE001
        logger.warning("LLM falló: %s", e)
        summary_txt = "(resumen no disponible)"
        tier = "\n🧠 Resumen:"

    return (
        f"✅ Import #{import_id} [{source_type}] '{source_name}'\n"
        f"👤 {export.contact_name or '?'} — {phone or 'sin teléfono'}\n"
        f"💬 {inserted} mensajes ({min(ts_list) if ts_list else '?'} → "
        f"{max(ts_list) if ts_list else '?'})\n"
        f"🏭 pedidos={production['pedidos']} pagos={production['pagos']} "
        f"entregas={production['entregas']} problemas={production['problemas']}\n"
        f"💰 montos: {production['montos'][:5]}"
        f"{tier}\n{summary_txt}"
    )


async def _do_import(update: Update, raw: bytes | str, source_type: str,
                     source_name: str) -> None:
    global _last_import_ts
    now = time.time()
    if now - _last_import_ts < RATE_LIMIT_S:
        wait = int(RATE_LIMIT_S - (now - _last_import_ts))
        await update.message.reply_text(f"⏳ Rate limit: espera {wait}s.")
        return
    _last_import_ts = now

    try:
        if source_type == "zip":
            exports = wsp.parse_zip_bytes(raw if isinstance(raw, bytes) else raw.encode())
            if not exports:
                await update.message.reply_text("⚠️ El zip no contiene _chat.txt.")
                return
            for e in exports:
                report = _process_export("zip", source_name, raw, e)
                await update.message.reply_text(report[:4000])
        else:  # txt / paste
            res = wsp.parse_paste(raw if isinstance(raw, str)
                                  else raw.decode("utf-8", errors="replace"))
            if not res.messages:
                await update.message.reply_text(
                    "⚠️ No detecté mensajes con formato WhatsApp. "
                    "Pegá el chat con sus timestamps ([fecha, hora] Nombre: msg).")
                return
            res.contact_name = res.contact_name if source_type == "paste" else source_name
            report = _process_export(source_type, source_name,
                                     raw if isinstance(raw, str)
                                     else raw.decode("utf-8", errors="replace"), res)
            await update.message.reply_text(report[:4000])
    except Exception as e:  # noqa: BLE001
        logger.exception("error import")
        await update.message.reply_text(f"🔴 Error procesando: {e}")


async def cmd_import(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        await _unauthorized(update)
        return
    await update.message.reply_text(
        "📥 Modo import activado. Pegá el texto del chat como respuesta "
        "a este mensaje (o enviá un .zip / .txt directamente).")


async def on_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        await _unauthorized(update)
        return
    doc = update.message.document
    if not doc:
        return
    name = doc.file_name or "archivo"
    if not name.lower().endswith((".zip", ".txt")):
        await update.message.reply_text("⚠️ Solo acepto .zip o .txt")
        return
    if doc.file_size and doc.file_size > MAX_FILE_MB * 1024 * 1024:
        await update.message.reply_text(f"⚠️ Máximo {MAX_FILE_MB} MB.")
        return
    tg_file = await doc.get_file()
    data = await tg_file.download_as_bytearray()
    data = bytes(data)
    # guardar raw SIEMPRE (auditoría)
    h = hashlib.sha256(data).hexdigest()[:12]
    (RAW_DIR / f"{int(time.time())}_{h}_{name}").write_bytes(data)
    source_type = "zip" if name.lower().endswith(".zip") else "txt"
    await update.message.reply_text(f"⚙️ Procesando {name} ({len(data)} bytes)...")
    await _do_import(update, data, source_type, name)


async def on_pasted_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        await _unauthorized(update)
        return
    text = update.message.text or ""
    # solo activar si es respuesta al mensaje de /import o contiene formato WA
    reply_to = update.message.reply_to_message
    if not (reply_to and "Modo import activado" in (reply_to.text or "")):
        has_wa = any(rx.match(text.splitlines()[0]) if text.splitlines() else False
                     for rx in (wsp.RE_BRACKET, wsp.RE_DASH, wsp.RE_BRACKET_TIME_FIRST))
        if not has_wa:
            return  # texto normal, ignorar silenciosamente
    await _do_import(update, text, "paste", "paste")


async def on_error(update: object, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Error no manejado: %s", ctx.error)


# ── Main ───────────────────────────────────────────────────────────────

async def post_init(app: Application) -> None:
    await app.bot.set_my_commands([
        BotCommand("start", "Ayuda del bot"),
        BotCommand("import", "Activar modo pegado de texto"),
        BotCommand("status", "Estado del sistema"),
        BotCommand("list", "Últimos imports"),
        BotCommand("search", "Búsqueda semántica"),
        BotCommand("contact", "Datos de un contacto"),
        BotCommand("production", "Pedidos/pagos/problemas detectados"),
    ])
    logger.info("Whatsscanbot iniciado. Auth chat_id=%s", AUTHORIZED_CHAT_ID)


def main() -> None:
    if not TOKEN:
        raise SystemExit("WHATSSCAN_BOT_TOKEN no configurado en .env")
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("import", cmd_import))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("contact", cmd_contact))
    app.add_handler(CommandHandler("production", cmd_production))
    app.add_handler(MessageHandler(filters.Document.ALL, on_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_pasted_text))
    app.add_error_handler(on_error)
    logger.info("Whatsscanbot arrancando (polling)...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
