#!/usr/bin/env python3
"""Whatsscanbot — parser regex de exports de WhatsApp (DT-WSIMPORT 2B).

Determinista: SOLO stdlib + regex, NUNCA LLM/Ollama (regla del Líder).

Formatos de _chat.txt soportados:
  [12/09/2026, 15:30] Luis: mensaje
  [12/09/2026, 15:30:45] +58 412-1234567: mensaje
  12/09/26, 15:30 - Luis: mensaje           (AM/PM opcional)
  12/09/2026, 15:30 - Luis: mensaje
  2026-09-12, 15:30 - Luis: mensaje
  [15:30, 12/09/2024] Luis: mensaje

API:
  parse_txt(file_path)  -> ParseResult
  parse_paste(text)     -> ParseResult
  parse_zip(zip_path)   -> list[ChatExport]
"""

from __future__ import annotations

import hashlib
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

# ── Modelos ────────────────────────────────────────────────────────────

@dataclass
class Message:
    timestamp: str | None   # ISO 8601 si se pudo parsear
    sender: str               # nombre visible o teléfono
    direction: str            # 'in' | 'out' | 'unknown'
    text: str
    message_type: str = "text" # 'text' | 'media' | 'system'
    media_path: str | None = None
    msg_hash: str = ""


@dataclass
class ChatExport:
    contact_name: str                 # carpeta del zip o "unknown"
    contact_phone: str | None       # normalizado +58...
    messages: list[Message] = field(default_factory=list)


@dataclass
class ParseResult:
    contact_name: str = "unknown"
    contact_phone: str | None = None
    messages: list[Message] = field(default_factory=list)


# ── Regex de encabezados de mensaje ───────────────────────────────────

# [dd/mm/yyyy, hh:mm(:ss)] Sender: text
RE_BRACKET = re.compile(
    r"^\[(?P<date>\d{1,2}/\d{1,2}/\d{2,4}),\s*(?P<time>\d{1,2}:\d{2}(?::\d{2})?)"
    r"(?P<ampm>\s*[APap]\.?[Mm]\.?)?\]\s*(?P<rest>.*)$"
)
# [hh:mm, dd/mm/yyyy] Sender: text
RE_BRACKET_TIME_FIRST = re.compile(
    r"^\[(?P<time>\d{1,2}:\d{2}(?::\d{2})?)"
    r"(?P<ampm>\s*[APap]\.?[Mm]\.?)?,\s*(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\]\s*(?P<rest>.*)$"
)
# dd/mm/yy(yy), hh:mm(:ss) (AM/PM)? - Sender: text
RE_DASH = re.compile(
    r"^(?P<date>\d{1,2}/\d{1,2}/\d{2,4}),?\s+(?P<time>\d{1,2}:\d{2}(?::\d{2})?)"
    r"(?P<ampm>\s*[APap]\.?[Mm]\.?)?\s*-\s*(?P<rest>.*)$"
)
# yyyy-mm-dd, hh:mm - Sender: text
RE_ISO_DASH = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2}),?\s+(?P<time>\d{1,2}:\d{2}(?::\d{2})?)"
    r"(?P<ampm>\s*[APap]\.?[Mm]\.?)?\s*-\s*(?P<rest>.*)$"
)
# Sender: text  (continuación multilínea NO; solo si línea arranca con multimedia)
RE_MEDIA = re.compile(
    r"(multimedia omitido|multimedia omitted|<media omitted>|"
    r"document omitted|documento omitido|audio omitido|"
    r"sticker omitted|video omitted|image omitted|imagen omitida|"
    r"gif omitted|contact card omitted|tarjeta de contacto omitida)",
    re.IGNORECASE,
)
RE_PHONE = re.compile(r"\+?[\d\s\-()]{7,20}")
RE_SYSTEM = re.compile(
    r"(creó este grupo|created this group|cambió el asunto|changed the subject|"
    r"se unió|joined using|añadió a|added \+?58|"
    r"los mensajes y las llamadas están cifrados|messages and calls are encrypted|"
    r"desapareció|left|salieron del grupo| eliminated)",
    re.IGNORECASE,
)


# ── Helpers ───────────────────────────────────────────────────────────

def normalize_phone(raw: str) -> str | None:
    """Normaliza a +58XXXXXXXXXX estilo import_contacts_vcf. None si no es VE."""
    digits = re.sub(r"[^\d]", "", raw)
    if not digits:
        return None
    if digits.startswith("58") and len(digits) == 12:
        return f"+{digits}"
    if digits.startswith("0") and len(digits) == 11:  # 0412...
        return f"+58{digits[1:]}"
    if len(digits) == 10 and not raw.strip().startswith("+"):
        # Ambiguo: 10 dígitos sin país — asumimos VE local
        return f"+58{digits}"
    if raw.strip().startswith("+") and digits:
        return f"+{digits}"
    return None


def _iso(date: str, time: str, ampm: str | None) -> str | None:
    try:
        d = date.strip()
        if "-" in d:  # yyyy-mm-dd
            y, mo, da = d.split("-")
        else:         # dd/mm/yyyy (formato WhatsApp en español)
            da, mo, y = d.split("/")
        if len(y) == 2:
            y = "20" + y
        hh, mm, *rest = time.split(":")
        ss = rest[0] if rest else "00"
        if ampm:
            a = ampm.strip().replace(".", "").lower()
            h = int(hh)
            if a.startswith("p") and h < 12:
                hh = str(h + 12 if h != 12 else 12)
            elif a.startswith("a") and h == 12:
                hh = "0"
        return f"{int(y):04d}-{int(mo):02d}-{int(da):02d}T{int(hh):02d}:{int(mm):02d}:{int(ss):02d}"
    except (ValueError, IndexError):
        return None


def _split_sender(rest: str) -> tuple[str, str, str]:
    """Divide 'Sender: text' → (sender, text, direction). System msg → ('','' , 'sys')."""
    if RE_SYSTEM.search(rest):
        return "", rest, "system"
    m = re.match(r"^(?P<sender>[^:]{1,60}?):\s?(?P<text>.*)$", rest)
    if not m:
        return "", rest, "system"
    sender = m.group("sender").strip()
    text = m.group("text")
    direction = "out" if sender.lower() in {"yo", "you", "tú"} else "in"
    # sender con forma de teléfono
    if RE_PHONE.fullmatch(sender.strip()) or sender.strip().startswith("+"):
        direction = "in"
    return sender, text, direction


def _hash_msg(ts: str, sender: str, text: str) -> str:
    return hashlib.sha256(f"{ts}|{sender}|{text}".encode()).hexdigest()[:32]


# ── Núcleo de parseo ──────────────────────────────────────────────────

def _parse_lines(lines: list[str]) -> list[Message]:
    msgs: list[Message] = []
    for raw in lines:
        line = raw.rstrip("\n").rstrip("\ufeff")
        if not line.strip():
            continue
        matched = False
        for rx in (RE_BRACKET, RE_BRACKET_TIME_FIRST, RE_DASH, RE_ISO_DASH):
            m = rx.match(line)
            if not m:
                continue
            matched = True
            ts = _iso(m.group("date"), m.group("time"), m.group("ampm"))
            sender, text, direction = _split_sender(m.group("rest"))
            mtype = "media" if RE_MEDIA.search(text) else (
                "system" if direction == "system" else "text"
            )
            msgs.append(Message(
                timestamp=ts, sender=sender, direction=direction,
                text=text.strip(), message_type=mtype,
                msg_hash=_hash_msg(ts or "", sender, text.strip()),
            ))
            break
        if not matched:
            # continuación multilínea del mensaje anterior
            if msgs and msgs[-1].message_type != "system":
                msgs[-1].text += "\n" + line.strip()
                msgs[-1].msg_hash = _hash_msg(
                    msgs[-1].timestamp or "", msgs[-1].sender, msgs[-1].text
                )
            elif not msgs:
                msgs.append(Message(
                    timestamp=None, sender="", direction="system",
                    text=line.strip(), message_type="system",
                    msg_hash=_hash_msg("", "", line.strip()),
                ))
    return msgs


def _extract_phone(msgs: list[Message], fallback: str | None) -> str | None:
    for m in msgs:
        if m.sender and re.search(r"\+?\d[\d\s\-()]{6,}", m.sender):
            return normalize_phone(m.sender)
    if fallback:
        return normalize_phone(fallback)
    return None


# ── API pública ───────────────────────────────────────────────────────

def parse_txt(file_path: str | Path) -> ParseResult:
    p = Path(file_path)
    text = p.read_text(encoding="utf-8", errors="replace")
    res = ParseResult(contact_name=p.stem)
    res.messages = _parse_lines(text.splitlines())
    res.contact_phone = _extract_phone(res.messages, None)
    return res


def parse_paste(text: str) -> ParseResult:
    res = ParseResult(contact_name="paste")
    res.messages = _parse_lines(text.splitlines())
    res.contact_phone = _extract_phone(res.messages, None)
    return res


def parse_zip(zip_path: str | Path) -> list[ChatExport]:
    exports: list[ChatExport] = []
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            if not name.endswith("_chat.txt"):
                continue
            # carpeta contenedora = nombre del contacto
            parts = name.split("/")
            contact_name = parts[0] if len(parts) > 1 else Path(name).stem
            # intento extraer teléfono del nombre de carpeta: "+58 412 1234567 - Luis"
            phone = None
            pm = re.search(r"\+?5?8?\s?4\d{2}[\s\-]?\d{3}[\s\-]?\d{4}|\b04\d{9}\b", contact_name)
            if pm:
                phone = normalize_phone(pm.group(0))
            raw = zf.read(name).decode("utf-8", errors="replace")
            msgs = _parse_lines(raw.splitlines())
            if not phone:
                phone = _extract_phone(msgs, None)
            exports.append(ChatExport(
                contact_name=contact_name, contact_phone=phone, messages=msgs,
            ))
    return exports


def parse_zip_bytes(data: bytes) -> list[ChatExport]:
    """Para el bot (recibe bytes del documento Telegram)."""
    import io
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        exports = []
        for name in zf.namelist():
            if not name.endswith("_chat.txt"):
                continue
            parts = name.split("/")
            contact_name = parts[0] if len(parts) > 1 else Path(name).stem
            phone = None
            pm = re.search(r"\+?5?8?\s?4\d{2}[\s\-]?\d{3}[\s\-]?\d{4}|\b04\d{9}\b", contact_name)
            if pm:
                phone = normalize_phone(pm.group(0))
            raw = zf.read(name).decode("utf-8", errors="replace")
            msgs = _parse_lines(raw.splitlines())
            if not phone:
                phone = _extract_phone(msgs, None)
            exports.append(ChatExport(
                contact_name=contact_name, contact_phone=phone, messages=msgs,
            ))
        return exports
