# Diseño: Whatsscanbot — Bot de Telegram para importar chats de WhatsApp

**Tarea:** DT-WSIMPORT · **Orquestador:** Prometeo · **Estado:** DISEÑO (sin implementar)
**Fecha:** 2026-09-10 · **Repo:** /mnt/ssd_trabajo/hermes-agent (rama feat/odoo-r4-integration)

---

## 0. ANTECEDENTES ENCONTRADOS (FASE 0 — verificado en vivo 2026-09-10)

### 0.1 Qué existe y es REUTILIZABLE

| Antecedente | Ubicación | Reuso |
|---|---|---|
| Patrón de bot Telegram autorizado (chat_id + `/help` + systemd) | `skills/telegram_bot.py` (corriendo, PID 5053) | Plantilla directa: `_is_authorized()`, logging, carga de .env, estructura de comandos |
| Bot Telegram del Líder↔Prometeo (comandos /status /health…) | `skills/prometeo_telegram.py` (corriendo, PID 947963) | Patrón de commands + filters, LLMClient |
| Tabla `clients` (phone, phone_hash, name, address, zone, notas) | `data/dispatch.db` | UPSERT de contactos detectados en chats — clave `phone` UNIQUE ya existe |
| Tablas `conversations` (phone_hash↔dify_id) y `orders` | `data/conversations.db` | Referencia de phone_hash; NO se reusan para mensajes históricos |
| Tablas `fs_cuentas_cobrar` (cuentas por cobrar) | `data/conversations.db` | Referencia para detectar clientes con pagos pendientes |
| Importador vCard → 104 clientes + JSON por cliente | `scripts/import_contacts_vcf.py` → `docs/clientes-activos/*.json` | **Reuso directo**: la carpeta `data/whatsapp_exports/` ya existe y es el destino natural de los archivos del bot; el importador normaliza teléfonos +58 (misma normalización usará el bot) |
| Skill Meta Cloud API | `skills/meta-business-guru/SKILL.md` | Referencia de formato de mensajes WhatsApp (NO se toca el bridge) |
| Orquestador con agente Valentina (whatsapp_sender, order_parser) | `src/orchestration/orchestrator.py` | Consumidor futuro de los datos importados |
| Qdrant 1.12.2 activo con collections: mem0migrations, videos_h2o, biblioteca_h2o, hermes_memory | localhost:6333 | NO existe `whatsapp_conversations` → se crea nueva |
| python-telegram-bot 21.11.1, qdrant-client 1.12.2 en venv | `venv/` | Cero installs nuevos para el bot base |

### 0.2 Qué NO existe (creación nueva)

- Ninguna tabla `whatsapp_imports` / `whatsapp_messages` / `whatsapp_contacts` en ninguna DB del sistema (verificado en las 7 DBs: conversations(.archive), dispatch, hermes_memory, interactions, state.db, verification_evidence).
- Ningún parser de exports de WhatsApp (.zip/.txt) en Python en el repo.
- Ninguna collection Qdrant de conversaciones históricas.
- Ningún commit previo sobre "whatsscan" ni "chat import" (git log verificado; solo hay 2 commits de importador vCard de contactos: `c0b89f4`, `5b8f5ad`).
- **Hallazgo crítico:** `whatsapp-chat-parser` NO existe en PyPI (verificado con pip download: "No matching distribution"). Es un paquete npm/JS. → El parser del .zip será **código propio** en Python (el formato _chat.txt es simple y determinista; regex propia, sin LLM para parseo).
- **Hallazgo crítico 2:** NO hay variable `DEEPSEEK*` en `config/.env`. El resumen con "DeepSeek V4 Flash" debe configurarse vía OpenRouter (proveedor `openrouter`, modelo del estilo `deepseek/deepseek-v4-flash`) — se requiere confirmar el nombre exacto del modelo con el Líder o contra la API de OpenRouter antes de implementar. Fallback: LLMClient existente del repo.

### 0.3 Conclusión de FASE 0

Hay infraestructura sólida que reusar (patrón de bot, DB clients, Qdrant, venv), pero el dominio "import de chats" es **nuevo desde cero**: schema, parser, collection y bot son creación nueva integrada sobre lo existente.

---

## 1. Arquitectura (diagrama ASCII)

```
                       Telegram (Líder: 1663148211 / @elpelon27 — ÚNICO autorizado)
                              │
                              ▼
                   ┌─────────────────────┐
                   │   whatsscan_bot.py  │  systemd: whatsscanbot.service
                   │  (python-telegram-  │  Token: WHATSSCAN_BOT_TOKEN (.env)
                   │      bot 21.11)     │
                   └────────┬────────────┘
        Input 1: .zip  ─────┤
        Input 2: .txt  ─────┤     1. Auth check (chat_id != 1663148211 → rechazo + log)
        Input 3: paste ─────┘     2. Guardar raw → data/whatsapp_exports/raw/<ts>_<hash>/
                                  3. Dedup: sha256(raw) vs whatsapp_imports.raw_hash
                            ┌─────┴──────────────────────────────────────┐
                            ▼                                            ▼
                ┌──────────────────┐                        ┌─────────────────────┐
                │  whatsapp_parser │ (puro Python+regex,    │ telegram reply     │
                │  (propio, NUEVO) │  SIN LLM en parseo)    │ (progreso/errores) │
                └───────┬──────────┘                        └─────────────────────┘
                        │ mensajes estructurados
        ┌───────────────┼───────────────────────┬─────────────────────┐
        ▼               ▼                       ▼                     ▼
┌──────────────┐ ┌──────────────┐   ┌────────────────────┐  ┌──────────────────┐
│ SQLite NUEVA │ │ UPSERT       │   │ Qdrant             │  │ Resumen LLM      │
│ whatsapp_bot │ │ dispatch.db  │   │ whatsapp_          │  │ vía OpenRouter    │
│ .db (3 tbls) │ │ .clients     │   │ conversations      │  │ (DeepSeek V4     │
│              │ │ (phone UNIQUE)│  │ (embeddings)       │  │  Flash, pend.    │
└──────────────┘ └──────────────┘   └────────────────────┘  │ confirmar modelo)│
                                                          └──────────────────┘
        Detección (regex + LLM-resumen): pedidos · pagos · entregas · problemas
        → tablas whatsapp_messages.flags_json + whatsapp_imports.summary_json
```

**Decisión de DB nueva (`data/whatsapp_bot.db`) y no tocar dispatch.db/conversations.db:**
- Aislamiento: regla del Líder de no romper producción; dispatch.db solo recibe UPSERT de contacts.
- Un solo writer para tablas nuevas → sin riesgo de lock con otros servicios.

---

## 2. Schema SQLite (data/whatsapp_bot.db — NUEVA)

```sql
CREATE TABLE whatsapp_imports (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_hash      TEXT NOT NULL UNIQUE,        -- sha256 del archivo/texto original
    input_type    TEXT NOT NULL,               -- 'zip' | 'txt' | 'paste'
    source_name   TEXT,                        -- nombre de archivo o 'paste_<ts>'
    contact_phone TEXT,                        -- teléfono del chat exportado (normalizado +58)
    contact_name  TEXT,                        -- nombre de la carpeta/vCard del export
    msg_count     INTEGER DEFAULT 0,
    date_min      TEXT,                        -- rango temporal del chat
    date_max      TEXT,
    summary_json  TEXT,                        -- resumen LLM: {tema, pedidos, pagos, problemas}
    status        TEXT NOT NULL DEFAULT 'processing',  -- processing|ok|error|duplicate
    error_text    TEXT,
    created_at    REAL NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE TABLE whatsapp_messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    import_id    INTEGER NOT NULL REFERENCES whatsapp_imports(id) ON DELETE CASCADE,
    ts           TEXT NOT NULL,                -- timestamp del mensaje (ISO)
    sender       TEXT NOT NULL,                -- 'me' | phone | nombre visible
    direction     TEXT NOT NULL,               -- 'in' | 'out' | 'unknown'
    text         TEXT NOT NULL,
    flags_json   TEXT,                         -- {"pedido":..,"pago":..,"entrega":..,"problema":..,"monto":..,"divisa":..}
    msg_hash     TEXT NOT NULL,                -- sha256(ts+sender+text), dedup intra/inter-import
    UNIQUE(import_id, msg_hash)
);
CREATE INDEX idx_wa_msg_import ON whatsapp_messages(import_id);
CREATE INDEX idx_wa_msg_ts ON whatsapp_messages(ts);

CREATE TABLE whatsapp_contacts (
    phone        TEXT PRIMARY KEY,             -- normalizado +58XXXXXXXXXX
    display_name TEXT,
    last_import  INTEGER REFERENCES whatsapp_imports(id),
    total_msgs   INTEGER DEFAULT 0,
    first_seen   TEXT,                         -- fecha del msg más antiguo
    last_seen    TEXT,
    client_id    INTEGER,                      -- FK lógica a dispatch.db clients.id (nullable)
    updated_at   REAL NOT NULL DEFAULT (strftime('%s','now'))
);
```

**Integración con dispatch.db.clients:** después de cada import exitoso, UPSERT por `phone` (columna UNIQUE ya existente): si el cliente existe → actualizar `updated_at` y `notes`; si no → INSERT con `client_type='retail'`. Se guarda el `clients.id` resultante en `whatsapp_contacts.client_id`.

---

## 3. Schema Qdrant: collection `whatsapp_conversations` (NUEVA)

- Vector size: según modelo de embeddings disponible en el stack (usar el mismo embedding que `hermes_memory` para reusar configuración; confirmar dimensión con la config existente antes de implementar — probablemente 384/768/1024 según Ollama/OpenRouter local).
- Distance: Cosine.
- Payload por punto (1 punto = 1 mensaje O 1 ventana de 5 mensajes concatenados, a decidir en implementación; recomendado: ventana):
  ```json
  {
    "import_id": 12,
    "phone": "+584241234567",
    "contact_name": "Luis M.",
    "ts": "2026-09-01T14:32:00",
    "sender": "me",
    "text": "…",
    "flags": {"pedido": true, "monto": 2.5, "divisa": "EUR"}
  }
  ```
- ID de punto = uuid5(namespace_fijo, msg_hash) → idempotente: reimportar no duplica vectores.
- Búsqueda `/search <consulta>` → query_embedding → top-k → respuesta formateada con teléfono/fecha/texto.

---

## 4. Flujo del bot (3 tipos de input)

Comandos: `/start` `/import` `/status` `/search <q>` `/list` `/contact <tel>` `/production`
(`<query>` opcional en /search; `/production` = ver pedidos/pagos detectados en los imports).

### 4.1 .zip (export "completo" de WhatsApp)
1. Recibir Document → validar extensión .zip y tamaño (< 50 MB).
2. Guardar en `data/whatsapp_exports/raw/<UTCts>_<sha256[:12]>.zip`.
3. sha256 del archivo → si existe en `whatsapp_imports.raw_hash` → responder "ya importado" (status=duplicate) y NO reprocesar.
4. Abrir con `zipfile` (stdlib): buscar `*_chat.txt` en cada subcarpeta (cada carpeta = 1 contacto). Extraer también `message_1.docx`/adjuntos SOLO para conteo (no parseo de binarios).
5. Parsear cada `_chat.txt` → INSERT import + messages.
6. Responder al Líder: contactos, N mensajes, rango de fechas, resumen.

### 4.2 .txt
Igual que zip pero con el contenido directo; nombre de contacto = nombre de archivo (fallback: primer número detectado).

### 4.3 Texto pegado
MessageHandler con filters.TEXT y keyword de activación: el Líder responde al mensaje `/import` y luego pega, o pega precedido por `/import`. El texto se procesa idéntico a .txt.

### 4.4 Parser `_chat.txt` (propio, regex determinista, SIN LLM)
Formatos soportados (AM/PM 12h y 24h, español/inglés):
```
[01/09/2026, 14:32:05] Luis: texto...
1/9/26, 2:32 PM - Luis: texto...
2026-09-01, 14:32 - Luis: texto
```
Líneas sin encabezado → se adosan al mensaje anterior (multilínea). Adjuntos: `<Multimedia omitido>`, `document omitted` → flag `attachment`.
Detección de flags por regex sobre cada mensaje (NO LLM):
- pedido: r/([0-9]+)\s*(bidones?|garrafones?|botellas?|botellones?)|pedido|quiero|envíame/i
- pago: transferencia|pago|pagué|pagado|Bs|EUR|zelle|pago móvil|banesco|mercantil + extracción de monto
- entrega: entrega|entregado|llegó|recibí|confirmo
- problema: no llegó|tarde|reclamo|devuelv|mal|queja|problema
- monto: r/(\d+[.,]?\d*)\s*(EUR|€|Bs|USD|\$)/

### 4.5 Resumen LLM (DeepSeek V4 Flash vía OpenRouter)
- SOLO el resumen del import completo (input: los textos de mensajes, truncado a contexto seguro) → `summary_json`.
- NUNCA se usa LLM para parsear mensajes individuales. Ollama NUNCA se usa en este pipeline.
- Modelo exacto a confirmar (ver 0.2): variable `WHATSSCAN_LLM_MODEL` en .env.

---

## 5. Reglas de seguridad

1. SOLO chat_id `1663148211`; cualquier otro → "🚫 No autorizado" + log warning (patrón existente de telegram_bot.py).
2. Token en `config/.env` como `WHATSSCAN_BOT_TOKEN` — NUNCA en código ni en commit. (Nota: el token ya viajó en la directiva del Líder; al implementar, guardarlo solo en .env.)
3. Archivos recibidos: máximo 50 MB, solo .zip/.txt; guardar SIEMPRE el raw antes de parsear (auditoría).
4. Parser = regex propio determinista; LLM solo para resumen global; Ollama prohibido en este flujo.
5. NO tocar: vehicles/dispatch schema existentes, DT-01, bridge Meta/webhook, OpenNotebook, SOUL FASE 3. dispatch.db solo recibe UPSERT en `clients`.
6. Servicio corre con venv del proyecto (`python-telegram-bot` ya instalado), usuario `skynet`, systemd `whatsscanbot.service` (modelo igual a telegram-bot.service).
7. Dedup triple: raw_hash (archivo), msg_hash (mensaje), uuid5 (vector Qdrant) — reimportar es idempotente.

---

## 6. Dependencias

- Ya en venv: python-telegram-bot 21.11.1, qdrant-client 1.12.2. **Cero dependencias nuevas** (zipfile, hashlib, re, sqlite3 = stdlib).
- Parser: código propio (`whatsapp-chat-parser` de PyPI NO existe; es npm).

## 7. Archivos nuevos (cuando se implemente)

```
scripts/whatsscan/whatsscan_bot.py     # bot Telegram
scripts/whatsscan/whatsapp_parser.py   # parser regex _chat.txt + flags
scripts/whatsscan/importer.py          # dedup, SQLite, Qdrant, UPSERT clients
scripts/whatsscan/summarizer.py        # resumen LLM vía OpenRouter
config/whatsscanbot.service            # systemd unit
```

## 8. Config .env (nuevas variables)

```
WHATSSCAN_BOT_TOKEN=8834764302:...     # NO commitear .env
WHATSSCAN_AUTH_CHAT_ID=1663148211
WHATSSCAN_DB=/mnt/ssd_trabajo/hermes-agent/data/whatsapp_bot.db
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION_WHATSAPP=whatsapp_conversations
WHATSSCAN_LLM_MODEL=<deepseek-v4-flash vía OpenRouter — confirmar nombre exacto>
```

## 9. Estimación de implementación

| Paso | Estimación |
|---|---|
| Parser + tests con exports reales | 3-4 h |
| Bot + auth + 3 inputs | 2-3 h |
| SQLite schema + dedup + UPSERT clients | 2 h |
| Qdrant indexación + /search | 2-3 h |
| Resumen LLM + detección flags | 1-2 h |
| systemd + E2E con export real del Líder | 1-2 h |
| **Total** | **~12-16 h** |

Checkpoint verificable por sección (regla del Líder): parser → importer → bot → E2E, con backup de DBs antes de cada UPSERT en dispatch.db.

---

**Fase 1 (diseño) completa. Sin implementación, conforme a directiva.**