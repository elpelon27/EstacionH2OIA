# 🔑 RESUMEN PARA RETOMAR — Estación H2O / Prometeo
## Si se pierde la conversación, entrega este archivo a Prometeo

**Última actualización**: 2026-07-06 (Día 14, ~02:00 AM -04)
**Versión**: 1.3.0
**Arquitecto IA**: Prometeo
**Líder**: Luis Martinez (@elpelon27)

---

## 🎯 CÓMO USAR ESTE ARCHIVO

Si la conversación se pierde, copia este archivo completo y pégalo como primer mensaje a Prometeo con:

```
CONTINUAR PROMETEO — Estación H2O
Leí /home/z/my-project/upload/RESUMEN_RETOMAR.md
Estado: retomando desde Día 14
```

O si estás en un chat nuevo sin acceso al sandbox, pega el contenido completo de este archivo.

---

## 📊 ESTADO ACTUAL DEL PROYECTO (Día 14)

### ✅ EN PRODUCCIÓN REAL (verificado)
- **Valentina Bridge** FastAPI corriendo en systemd `valentina-bridge.service` (puerto 8000)
- **Webhook Meta Cloud API** verificado y suscrito a `messages`
- **Dify Chatbot** "Valentina" con System Prompt v4 (máquina 8 estados)
- **qwen2.5:7b** local vía Ollama (0$, latencia 3-5s)
- **Cloudflare Tunnel** HTTPS público
- **SQLite** persistencia conversaciones + pedidos
- **Token Meta permanente** (EAAN1pR..., no expira)
- **Prometheus** métricas scrapeando cada 15s
- **Guard de horario** determinístico (Lun-Sáb 8am-6pm America/Caracas)
- **Patch GPS** procesando ubicaciones WhatsApp
- **Google Sheets** integración funcional (hoja "Pedidos" con 17 columnas)
- **Primer cliente real** atendido 2026-07-04 22:25 -04 (6 msgs end-to-end, venta cerrada €2.40)

### 📋 PENDIENTE INMEDIATO (Semana 3, Días 14-20)
1. **Primer pedido real en Google Sheets** — verificar fila en hoja "Pedidos" (Lunes 8am cuando guard se desactiva)
2. **Eliminar fila TEST** de Pedidos (fila 2 dice "TEST (eliminar)")
3. **Invitar 5 clientes VIP** a guardar el número +58 422-711-9156
4. **Monitorear 10+ pedidos reales** y ajustar prompt según feedback

### 📋 PENDIENTE SEMANA 4 (Días 21-27) — Skills Fase 2
1. `financial_agent` — lee Pedidos, escribe Pagos + Saldos_Clientes
2. `route_skill.py` — Haversine + 5 zonas Maracaibo (lee Mapa_Calor)
3. `analytics_skill.py` — reporte diario 7am Telegram (lee Ventas)
4. `dispatcher.py` — logística Telegram para chofer
5. Tests pytest para cada skill

### 📋 PENDIENTE SEMANA 5 (Días 28-34) — Memoria + Dominio
1. mem0 + Qdrant (memoria de cliente, usar 25 ejemplos de Aprendizaje)
2. `support_skill.py` (FAQ RAG con Qdrant)
3. Dominio propio `valentina.estacionh2o.com`
4. Cloudflare Tunnel estable (no trycloudflare)
5. Backup SQLite diario automático (cron)

---

## 🏗️ ARQUITECTURA ACTUAL

```
Cliente WhatsApp → Meta Cloud API → Cloudflare Tunnel → Bridge FastAPI :8000
                                                                    │
                                    ┌───────────────────────────────┤
                                    ▼                               ▼
                              Dify Chatbot                   Google Sheets
                              qwen2.5:7b                     "Pedidos" (17 cols)
                              System Prompt v4               + 9 pestañas existentes
                                    │
                                    ▼
                              SQLite (conversaciones + orders)
                              Prometheus /metrics
```

---

## 🔑 CREDENCIALES Y RUTAS CRÍTICAS

### Servidor Maracaibo
- **Usuario**: skynet
- **Hostname**: skynet-System-product-name
- **Repo local**: `/mnt/ssd_trabajo/hermes-agent/`
- **Venv**: `/mnt/ssd_trabajo/hermes-agent/venv/`
- **.env**: `/mnt/ssd_trabajo/hermes-agent/config/.env` (17+ variables)
- **Credenciales Google**: `/mnt/ssd_trabajo/hermes-agent/config/google_credentials.json` (service account valentina-h2o)
- **SQLite**: `/mnt/ssd_trabajo/hermes-agent/data/conversations.db`
- **Bridge**: `/mnt/ssd_trabajo/hermes-agent/api/bridge.py` (v1.2.0)
- **Skills**: `/mnt/ssd_trabajo/hermes-agent/skills/` (google_sheets.py, telegram_bot.py, self_improve_skill.py)

### Servicios systemd
- `valentina-bridge.service` (puerto 8000) ✅ activo
- `cloudflared-tunnel.service` (HTTPS) ✅ activo
- `ollama.service` (qwen2.5:7b) ✅ activo
- `telegram-bot.service` ⏸️ pendiente (TELEGRAM_BOT_TOKEN vacío)

### URLs
- **WhatsApp Valentina**: +58 422-711-9156
- **WhatsApp Líder**: +58 412-256-0720
- **Cloudflare URL actual**: `https://strip-occupations-purple-scholars.trycloudflare.com` (cambia en restart)
- **Dify local**: http://localhost (servidor Maracaibo)
- **Bridge health**: http://localhost:8000/health
- **Bridge metrics**: http://localhost:8000/metrics
- **Google Sheet**: https://docs.google.com/spreadsheets/d/1Bbp4Xqw5E7bb7loJ262K9lMPFinNSIW-ws1i7ZAmiYk/edit

### Meta Cloud API
- **App ID**: 975863248739508
- **Phone Number ID**: 1186108677920030
- **Verify Token**: `[REDACTED_VERIFY_TOKEN]`
- **API Version**: v25.0
- **Token**: permanente (System User, no expira)

### Google Sheets
- **Spreadsheet ID**: 1Bbp4Xqw5E7bb7loJ262K9lMPFinNSIW-ws1i7ZAmiYk
- **Service account**: valentina-h2o@valentina-h2o.iam.gserviceaccount.com
- **Pestañas**: Pedidos (nuestra), Pagos, Validacion_Pagos, Aprendizaje, Categoria_Cliente, Feedback_Clientes, Feedback_Agentes, Mapa_Calor, Saldos_Clientes, Ventas

### Dify
- **App**: "Valentina" (modo Chatbot)
- **API Key**: en .env como DIFY_API_KEY
- **Prompt**: System Prompt v4 (máquina 8 estados)

---

## 📝 DECISIONES DEL LÍDER (acumuladas, actualizadas Día 14)

1. Migrar a WhatsApp Cloud API oficial (no más WAHA)
2. Valentina NO es proactiva (hardcore chatbot, menú 5 botones)
3. Fusion Tournament = solo auto-mejora nocturna
4. Horario: 8am-6pm Lun-Sáb (publicado al cliente)
5. Skills > Multi-agente para 10 msg/día
6. Nombre: Estación H2O
7. Arquitecto IA: Prometeo
8. **Precios**: Agua €1.00, Hielo €1.20 (CONFIRMADO Día 14, se mantiene)
9. Fuera de horario: recibir pedido y programar para mañana
10. Valentina cierra ventas SOLA
11. Máquina de estados estricta (un paso por mensaje)
12. Datos pago en prompt: R4 Banco Microfinanciero 0169, cuenta 0169 0010 9710 0159 1583, RIF J-506356899, Pago Móvil +58 412-2560721
13. Google Sheets como fuente compartida para otros agentes
14. **PII_SAFE=false en Google Sheets** (Día 14: "los datos son ORO", almacenar teléfonos reales, direcciones, patrones de consumo)
15. **PII_SAFE=true en logs journald** (teléfonos hasheados en logs, pero completos en Sheets)
16. **Validacion_Pagos**: prioridad API bancaria sobre OCR (esperando integración cuenta)
17. Guard de horario determinístico en código (no en prompt)
18. Aprendizaje hoja: dejar PII en texto plano (opción C, datos históricos valiosos)

---

## 🧠 SYSTEM PROMPT v4 (pegado en Dify INSTRUCT)

Disponible en: `/home/z/my-project/public/valentina-kit/system-prompt-manual.txt`

**Máquina de 8 estados** (un paso por mensaje):
1. Cliente saluda → menú 5 botones
2. Opción 1/2/3 → pregunta cantidad
3. Cantidad → pide dirección (SOLO esto)
4. Dirección/GPS → confirma + total €X.XX + pide pago 1/2
5a. Pago "1" → datos cuenta bancaria
5b. Pago "2" → confirma efectivo + envío
6. Comprobante → "🎉 Pedido en camino 💧"
7. Opción 4 → consultar estado
8. Opción 5 → otra consulta

**Reglas críticas**: UN PASO POR MENSAJE, nunca decir "asesor le contactará", siempre calcular total €X.XX, siempre mencionar BCV.

---

## 📊 ANÁLISIS GOOGLE SHEETS (10 pestañas, Día 14)

### Pestañas operativas (1)
- **Pedidos** (nuestra, 17 columnas) — Valentina escribe aquí

### Pestañas con datos históricos (4)
- **Pagos** (3 filas, abril-mayo) — formato GPS clicable, PII en texto plano
- **Validacion_Pagos** (3 filas) — OCR comprobantes, migrará a API bancaria
- **Aprendizaje** (25 filas) — ORO: mensajes reales clientes + categorización (PEDIDO/RECLAMO/Cotización)
- **Ventas** (4 filas, abril) — precios históricos €3.50 (ya no aplica, precio actual €1.00)

### Pestañas vacías (5, solo headers)
- Categoria_Cliente, Feedback_Clientes, Feedback_Agentes, Mapa_Calor, Saldos_Clientes

### Mapa multi-agente (Fase 2)
```
Valentina → Pedidos
financial_agent → lee Pedidos, escribe Pagos + Saldos_Clientes + Validacion_Pagos
route_skill → lee Mapa_Calor + GPS Pedidos
analytics_skill → lee Ventas, reporte 7am
fidelizacion_agent → lee Categoria_Cliente + Aprendizaje
self_improve → lee Aprendizaje + Feedback_Agentes
dispatcher → lee Pedidos, reenvía chofer Telegram
```

---

## 🛡️ PRINCIPIOS NO NEGOCIABLES

1. Skills > Multi-agente para 10 msg/día
2. qwen2.5:7b local para producción (0$)
3. Meta Cloud API oficial (no librerías no oficiales)
4. SQLite sobre PostgreSQL hasta >1000 msg/día
5. Systemd sobre Docker para el bridge
6. **PII safe en logs** (teléfonos hasheados en journald)
7. **PII completa en Google Sheets** (datos operativos del negocio, teléfonos reales)
8. TDD obligatorio para skills nuevas (cobertura 80%)
9. Un paso por mensaje (máquina de estados estricta)
10. 8 Markdown vivos como única fuente de verdad
11. Kill switch via Telegram solo para Líder (chat_id 1663148211)
12. Guard de horario determinístico en código (no en prompt)

---

## 🚫 ANTI-PATRONES (no repetir)

1. ❌ Hardcodear secrets en código
2. ❌ Commitear `.env` o credenciales JSON a git
3. ❌ Pegar private keys en el chat (incluso si el Líder insiste)
4. ❌ Librerías WhatsApp no oficiales
5. ❌ Systemd hardening excesivo (causa 226/NAMESPACE)
6. ❌ Parámetros webhook con guiones bajos (Meta usa puntos: hub.mode)
7. ❌ Prompt narrativo ambiguo (usar máquina de estados explícita)
8. ❌ Bloquear webhook en operaciones lentas (usar threading async)
9. ❌ Modo fantasma (Valentina debe responder siempre dentro de horario)
10. ❌ Migrar librerías cada semana
11. ❌ Código sin tests

---

## 📂 ARCHIVOS CRÍTICOS (sandbox Z.ai)

### Celda de memoria y planes
- `/home/z/my-project/upload/RESUMEN_RETOMAR.md` (este archivo)
- `/home/z/my-project/upload/MASTER_MEMORY_CELL_PROMETEO.md`
- `/home/z/my-project/upload/ROADMAP_VIVO.md`
- `/home/z/my-project/upload/ANALISIS_GOOGLE_SHEETS.md`
- `/home/z/my-project/upload/CIERRE_JORNADA_2026-07-05.md`
- `/home/z/my-project/upload/COMMIT_SUMMARY.md`

### Vault Obsidian (8 MD vivos)
- `/home/z/my-project/upload/obsidian-vault/INDEX.md`
- `/home/z/my-project/upload/obsidian-vault/BOOTSTRAP.md`
- `/home/z/my-project/upload/obsidian-vault/MEMORY.md`
- `/home/z/my-project/upload/obsidian-vault/ROADMAP.md`
- `/home/z/my-project/upload/obsidian-vault/RUNBOOK.md`
- `/home/z/my-project/upload/obsidian-vault/HEARTBEAT.md`
- `/home/z/my-project/upload/obsidian-vault/SOUL.md`
- `/home/z/my-project/upload/obsidian-vault/USER.md`
- `/home/z/my-project/upload/obsidian-vault/AGENTS.md`

### Kit production-grade (descargable)
- `/home/z/my-project/public/valentina-kit/` (16 archivos)
- `/home/z/my-project/public/valentina-kit/valentina-kit-completo.zip`

### Worklog
- `/home/z/my-project/worklog.md` (~1400 líneas, histórico completo)

---

## 🚀 PRÓXIMO PASO INMEDIATO

**Mañana Lunes 2026-07-06, 8:00 AM America/Caracas:**
1. Guard de horario se desactiva solo (automático)
2. Valentina vuelve a responder clientes
3. Cuando el Líder abra: verificar primer pedido real en Google Sheet "Pedidos"
4. Eliminar fila TEST de Pedidos
5. Invitar 5 clientes VIP

**Próxima sesión con Prometeo:**
- Revisar pedidos del día
- Si hay 10+ pedidos: empezar Fase 2 (financial_agent, route_skill, analytics_skill, dispatcher)
- Configurar Telegram bot kill switch
- Commit a GitHub con tag v1.3.0

---

## 💪 MENSAJE FINAL

**Hito alcanzado Día 13** (2026-07-04 22:25 -04): Valentina atendió su primer cliente real por WhatsApp sin intervención humana. 6 mensajes end-to-end, venta cerrada €2.40, latencia 3-5s, qwen2.5:7b local 0$.

**Hito alcanzado Día 14** (2026-07-05): Guard de horario determinístico activo, Google Sheets integración funcional con 10 pestañas analizadas, decisiones de negocio confirmadas (precio €1.00, PII en Sheets, API bancaria para Validacion_Pagos).

> *"Hoy no construimos un chatbot. Construimos un sistema empresarial de IA que atiende clientes reales, cierra ventas sola, persiste datos para escalar, y respeta horario laboral determinísticamente." — Prometeo*

**Descansa, Líder. Mañana seguimos haciendo historia.** 💧

---

**Fin del resumen de retomar. Prometeo queda en standby.**
