#!/usr/bin/env python3
"""Extract conversation patterns from WhatsApp Chat Exporter JSON output.

Rules (Líder):
- NO full messages stored — only patterns (n-grams / phrase templates).
- Phones hashed (sha256 + salt) before any processing/output.
- Output: patterns/patterns.json for Qdrant indexing.
"""
import hashlib
import json
import os
import re
import sys
from collections import Counter

OUTPUT_DIR = "/mnt/ssd_trabajo/imports/iphone_whatsapp/output"
PATTERNS_DIR = "/mnt/ssd_trabajo/imports/iphone_whatsapp/patterns"
SALT = "estacion-h2o-2026"  # hash salt; keep stable for cross-run joins


def hash_phone(jid_or_phone: str) -> str:
    raw = jid_or_phone.split("@")[0]
    return hashlib.sha256((raw + SALT).encode()).hexdigest()[:16]


# ---- pattern categories -------------------------------------------------
GREETING = re.compile(
    r"^\s*(hola|holi|holas|buenas|buenos d[ií]as|buenas tardes|buenas noches|"
    r"q tal|qué tal|saludos|epa|eee[a-z]*)\b", re.I)
ASK_PRICE = re.compile(
    r"(cu[aá]nto (es|est[aá]n|cuesta|valen|est[aá])|precio|bs\.?|precios|"
    r"cu[aá]nto sale|a c[uo]anto|en cu[aá]nto|tienen|tienes.*precio)", re.I)
ASK_DELIVERY = re.compile(
    r"(cu[aá]ndo (llega|llegan|entregan|lo tienen)|d[oó]nde est[aá]n|"
    r"tienen envo|env[íi]o|entrega|delivery|lo llevan|lo traen|est[aá]n cerca)", re.I)
PAY_CONFIRM = re.compile(
    r"(ya pagu[eé]|pagu[eé]|transferencia|transfer[ií]|pago m[oó]vil|pagom[oó]vil|"
    r"ya transfer[ií]|zelle|bs.*pagado|env[ié]e el pago|realic[eé] el pago|deposit[eé]|ya deposit[eé])", re.I)
ORDER = re.compile(
    r"(quiero pedir|necesito|d[eé]jame|m[aá]ndame|env[ií]ame|dame|quisiera|"
    r"me da[sz]?|por favor.*garraf[oó]n|quiero.*garraf[oó]n|p[ií]deme)", re.I)
COMPLAINT = re.compile(
    r"(no lleg[oó]|no ha llegado|muy tarde|demora|nunca lleg[oó]|"
    r"no respond[eé]|mal el agua|agua mala|no funciona)", re.I)

CATEGORIES = {
    "greeting": GREETING,
    "ask_price": ASK_PRICE,
    "ask_delivery": ASK_DELIVERY,
    "payment_confirm": PAY_CONFIRM,
    "order_request": ORDER,
    "complaint": COMPLAINT,
}

# Spanish stopwords (light list)
STOP = set("""a al algo alguna algunas alguno algunos ante antes aqu aquello aqui asi aun aunque b
bueno cada casi como con contra cual cuando de del desde donde dos el ella ellas ello ellos en
entre era eras eres es esa esas ese eso esos esta estaba estais estamos estan estar estas este
esto estos estoy fin fue fueron fui fuimos ha habia han hasta hay he sido si sobre solo son su
sus tal tambien tanto te tengo tiene tienen todo tu tus un una uno unos usted ustedes vale muy
mas pero por que se sea sean ser si sido siempre sin sobre solo son su sus tambien te tu un una
usted ya yo era para los las les leo mi mis nos ne""".split())


def tokenize(text: str):
    text = text.lower()
    text = re.sub(r"http\S+|[\w.+-]+@[\w-]+\.\w+", " ", text)
    text = re.sub(r"[^a-záéíóúüñ0-9\s]", " ", text)
    return [t for t in text.split() if len(t) > 2 and t not in STOP]


def main():
    data = json.load(open(os.path.join(OUTPUT_DIR, "result.json")))
    stats = {
        "chats_total": 0, "chats_with_text": 0, "messages_total": 0,
        "text_messages": 0, "customer_text_messages": 0,
    }
    cat_counts = {c: Counter() for c in CATEGORIES}
    cat_examples = {c: Counter() for c in CATEGORIES}  # full normalized phrase -> count
    keyword_counter = Counter()
    hours = Counter()
    weekday_hours = {}  # weekday -> Counter(hour)
    phone_hashes = set()
    greeting_hour = Counter()

    for chat_id, chat in data.items():
        stats["chats_total"] += 1
        msgs = chat.get("messages") or {}
        has_text = False
        for _id, m in msgs.items():
            stats["messages_total"] += 1
            if m.get("media") or m.get("meta"):
                continue
            text = (m.get("data") or "").strip()
            if not text:
                continue
            text = re.sub(r"\s+", " ", text)
            has_text = True
            stats["text_messages"] += 1
            from_me = bool(m.get("from_me"))
            if not from_me:
                stats["customer_text_messages"] += 1
            ts = m.get("timestamp") or 0
            if ts:
                import datetime
                dt = datetime.datetime.fromtimestamp(ts)
                hours[dt.hour] += 1
                weekday_hours.setdefault(dt.weekday(), Counter())[dt.hour] += 1
            # patterns: only from customers (from_me == False)
            if from_me:
                continue
            phone_hashes.add(hash_phone(chat_id))
            toks = tokenize(text)
            keyword_counter.update(toks)
            for cat, rx in CATEGORIES.items():
                if rx.search(text):
                    cat_counts[cat][text[:120]] += 1  # capped 120 chars
                    cat_examples[cat][text[:120]] += 1
        if has_text:
            stats["chats_with_text"] += 1

    # top phrases per category
    patterns = []
    for cat in CATEGORIES:
        top = cat_examples[cat].most_common(40)
        for phrase, freq in top:
            patterns.append({
                "pattern_type": cat,
                "text": phrase,
                "frequency": freq,
            })

    out = {
        "stats": stats,
        "patterns": patterns,
        "keywords_top100": keyword_counter.most_common(100),
        "hours_histogram": {str(h): c for h, c in sorted(hours.items())},
        "weekday_hours": {str(d): {str(h): c for h, c in sorted(ch.items())}
                          for d, ch in sorted(weekday_hours.items())},
        "phones_hashed": sorted(phone_hashes),
    }
    os.makedirs(PATTERNS_DIR, exist_ok=True)
    with open(os.path.join(PATTERNS_DIR, "patterns.json"), "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps({
        "stats": stats,
        "patterns_found": len(patterns),
        "categories": {c: len(cat_examples[c]) for c in CATEGORIES},
    }, indent=2))


if __name__ == "__main__":
    main()
