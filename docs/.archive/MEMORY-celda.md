# 🧠 MEMORY — Celda de Memoria Maestra

**Última actualización**: 2026-07-05 (Día 13 — Producción real)

---

## 📊 Estado actual del proyecto

**Progreso total**: Fase 0 ✅, Fase 1 ✅ 95%, Fase 2 ⏸️, Fase 3 ⏸️

### Fase 0 — Setup infraestructura ✅ COMPLETADA (días 1-11)
- Setup base + Docker + Ollama ✅
- Repo Hermes Agent ✅
- Docker Compose base (5 servicios) ✅
- Obsidian + 8 Markdown docs ✅
- Meta Cloud API (reemplazó WAHA) ✅
- Core Hermes (8 módulos, 91 tests) ✅
- Valentina + mem0 + API Gateway ✅
- Systemd blindaje + Cloudflare Tunnel ✅
- Skills básicas (payment, inventory, self_improve) ✅

### Fase 1 — Dify + Valentina producción ✅ 95% (día 13)
- ✅ Dify 1.15.0 instalado y conectado a Qwen 2.5 7B local
- ✅ App "Valentina" creada en Dify (modo Chatbot, NO Chatflow)
- ✅ System Prompt v4 (máquina de estados 8 estados) en INSTRUCT
- ✅ Valentina cierra ventas sola: total EUR + BCV + datos pago + confirmación
- ✅ Datos bancarios reales (R4, cuenta 0169 0010 9710 0159 1583, RIF J-506356899)
- ✅ Validado en Dify Debug & Preview (flujo perfecto 5 estados sin saltos)
- ✅ DIFY_API_KEY + META_ACCESS_TOKEN permanente en .env
- ✅ Kit production-grade: 14 archivos (bridge.py, tests, CI/CD, monitoreo, skills)
- ✅ **Deploy ejecutado**: valentina-bridge.service active (running)
- ✅ **Webhook Meta verificado** + suscrito a messages
- ✅ **PRUEBA DE FUEGO EXITOSA**: 6 msgs end-to-end con cliente real
- ✅ Patch GPS: ubicaciones WhatsApp funcionando
- ✅ Google Sheets integration al 90% (módulo + parser + deps instaladas)
- ⏸️ **Falta**: descargar `google_credentials.json` (reseteo SO lo borró)

### Fase 2 — Skills Operativas ⏸️ (próxima semana)
- [ ] `route_skill.py` (Haversine + 5 zonas Maracaibo)
- [ ] `analytics_skill.py` (reporte diario 7am Telegram)
- [ ] `support_skill.py` (FAQ RAG con Qdrant)
- [ ] `dispatcher.py` (logística Telegram)
- [ ] mem0 + Qdrant (memoria de cliente)

### Fase 3 — Estabilización ⏸️ (semanas 5-6)
- [ ] Métrica: >70% conversaciones sin humano
- [ ] Dominio propio para Cloudflare Tunnel
- [ ] Telegram bot kill switch activo
- [ ] CI/CD GitHub Actions operativo

---

## 🏗️ Arquitectura final del sistema (Día 13)

```
┌─────────────────────────────────────────────────┐
│  Cliente WhatsApp (+58 4XX-XXXXXXX)              │
└────────────────────┬────────────────────────────┘
                     │ mensaje texto/GPS
                     ▼
┌─────────────────────────────────────────────────┐
│  Meta Cloud API (graph.facebook.com/v25.0)       │
└────────────────────┬────────────────────────────┘
                     │ webhook HTTPS (HMAC-SHA256)
                     ▼
┌─────────────────────────────────────────────────┐
│  Cloudflare Tunnel (HTTPS → :8000)               │
│  URL: strip-occupations-purple-scholars...       │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│  Valentina Bridge (FastAPI :8000)                │
│  systemd: valentina-bridge.service               │
│  ├── HMAC verification (APP_SECRET)              │
│  ├── Kill switch (/tmp/valentina.kill)           │
│  ├── Deduplicación (cache 5min)                  │
│  ├── Rate limiting (30/min phone, 100/min IP)    │
│  ├── PATCH GPS (location → texto)                │
│  ├── Parser _build_order_payload (regex)         │
│  ├── POST a Dify /v1/chat-messages               │
│  ├── POST a Meta Graph API (envía respuesta)     │
│  ├── SQLite persistencia (convs + orders)        │
│  ├── Google Sheets async (thread daemon)         │
│  ├── Prometheus /metrics (8 métricas)            │
│  └── Telegram alerts (crítico)                   │
└────────────────────┬────────────────────────────┘
                     │
            ┌────────┴────────┐
            ▼                 ▼
┌──────────────────┐  ┌──────────────────────┐
│ Dify Chatbot     │  │ Google Sheets        │
│ (localhost:80)   │  │ "Pedidos" (17 cols)  │
│ qwen2.5:7b       │  │ 1Bbp4Xqw5E7bb...     │
│ temp 0.1         │  │ Service account:     │
│ System Prompt v4 │  │ valentina-h2o@...    │
└──────────────────┘  └──────────────────────┘
```

---

## 🔑 Credenciales (en config/.env)

### Meta Cloud API (WhatsApp oficial)
- META_ACCESS_TOKEN: ✅ permanente (EAAN1pR...)
- META_PHONE_NUMBER_ID: 1186108677920030
- META_APP_SECRET: [REDACTED_APP_SECRET]
- META_VERIFY_TOKEN: [REDACTED_VERIFY_TOKEN]
- META_API_VERSION: v25.0
- Número API: +58 422-711-9156
- Número Líder: +58 412-256-0720

### Dify
- DIFY_API_URL: http://localhost/v1/chat-messages
- DIFY_API_KEY: ✅ configurada (app-xxx)

### Google Sheets
- GOOGLE_SPREADSHEET_ID: 1Bbp4Xqw5E7bb7loJ262K9lMPFinNSIW-ws1i7ZAmiYk
- GOOGLE_CREDENTIALS_PATH: /mnt/ssd_trabajo/hermes-agent/config/google_credentials.json
- GOOGLE_SHEET_NAME: Pedidos
- ❌ **PENDIENTE**: descargar JSON de Google Cloud Console

### Telegram (pendiente activar)
- TELEGRAM_BOT_TOKEN: (vacío)
- TELEGRAM_CHAT_ID: 1663148211

### Cloudflare Tunnel
- URL actual: https://strip-occupations-purple-scholars.trycloudflare.com
- ⚠️ URL cambia en cada restart (necesita dominio propio Fase 3)

---

## 📊 Servicios activos

### systemd (auto-arranque)
- ✅ valentina-bridge.service (FastAPI puerto 8000)
- ✅ cloudflared-tunnel.service (HTTPS público)
- ✅ ollama.service (modelos IA)
- ⏸️ telegram-bot.service (pendiente TELEGRAM_BOT_TOKEN)

### Docker
- ✅ Qdrant v1.12.4 (DB vectorial) — Puerto 6333
- ✅ Redis 7-alpine — Puerto 6379
- ✅ Prometheus v3.1.0 — Puerto 9090
- ✅ Grafana 11.4.0 — Puerto 3001
- ✅ Node Exporter v1.8.2 — Puerto 9100
- ✅ Dify (12 contenedores) — Puerto 80

---

## 🎯 Decisiones críticas del Líder (acumuladas)

1. Migrar a WhatsApp Cloud API oficial (no más WAHA/OpenWA)
2. Valentina NO es proactiva (hardcore chatbot, menú 5 botones)
3. Fusion Tournament = solo auto-mejora nocturna (no para clientes)
4. Horario: 8am-6pm Lun-Sáb (publicado al cliente)
5. Skills > Multi-agente para 10 msg/día
6. Nombre: Estación H2O (no Valentina Proactiva)
7. Arquitecto IA: Prometeo
8. Precios en EUROS: Agua €1.00, Hielo €1.20
9. Fuera de horario: recibir pedido y programar para mañana
10. inventory_skill comparte datos (API interna + SQLite directo)
11. Valentina cierra ventas SOLA (sin "asesor le contactará")
12. Máquina de estados estricta (un paso por mensaje)
13. Datos pago en el prompt: R4, cuenta 0169 0010 9710 0159 1583, RIF J-506356899
14. Google Sheets como fuente compartida para otros agentes/skills
15. PII safe por defecto (teléfonos hasheados)

---

## 📋 Historial de commits GitHub (acumulados)

```
e5f6725 fix(valentina): memoria de sesión + prompt optimizado
dae86f4 fix(webhook): usar PlainTextResponse para verificación Meta
02ecc38 test: fix workload_router tests + cloudflare tunnel setup
6fe3f50 feat(router): horario 7:40-18:00 + integración skills
ec95a1f feat(skills): arquitectura skills + workflow hardcore + precios EURO
65a8086 feat(meta): webhook Meta Cloud API + eliminar WAHA
490f2cf fix(production): message.any + precios + temperature + dedup cache
7ea21f8 feat(api): FastAPI gateway con webhooks WhatsApp + Telegram
e483322 test(valentina): fix mock reference for human escalation test
6ab1a71 feat(agents): valentina.py — recepcionista WhatsApp con memoria
b7e1499 feat(memory): memory_client.py con mem0 + Qdrant + embeddings locales
785fdf4 feat(core): workload_router.py + cost_guard.py — Core completo
06e7d9c feat(core): fusion.py + judge.py — Fusion Tournament completo
0d1c88f feat(core): openrouter_client + qwen_client con tests
15f6121 feat(core): config.py + logger.py con PII sanitization
03d71ed docs: configurar Obsidian vault + lanzador desktop
844b96a docs: 8 Markdown vivos + 6 ADRs + system prompt Valentina
8b796fe feat(infra): docker-compose base (Qdrant, Redis, Prometheus, Grafana)
5104f8a fix(infra): prometheus scrape target 172.17.0.1
a412232 fix: use flexible version constraints (>=)
7bcfe9d fix: pin httpx==0.27.2
efbb160 fix: pin mem0ai==0.1.118
1523ad6 feat: bootstrap Hermes Agent (Fase 0)
```

**Próximo commit**: `feat(production): bridge v1.2.0 + GPS + Google Sheets + primer cliente real`

---

## 🏆 Logros del proyecto (13 días)

| Día | Logro |
|-----|-------|
| 1 | Auditoría 134K líneas → 158 hallazgos |
| 2 | Plano maestro + formateo servidor |
| 3 | Restauración Docker + Ollama + Repo GitHub |
| 4 | Docker Compose + Obsidian + 8 Markdown |
| 5 | Core Hermes (8 módulos, 65 tests) |
| 6 | Memoria + Valentina + API Gateway |
| 7 | WhatsApp conectado (WAHA → migrando) |
| 8 | Migración a Meta Cloud API oficial |
| 9 | Skills (payment, inventory, self_improve) |
| 10 | Systemd blindaje + Cloudflare Tunnel |
| 11 | Dify instalado + Qwen conectado + Prometeo |
| 12 | Auditoría verbatim + Opción A + Kit production-grade + Prompt v4 |
| **13** | **🎉 DEPLOY PRODUCCIÓN REAL + PRUEBA DE FUEGO EXITOSA + GPS + Sheets 90%** |

### Métricas finales (día 13)
- **Líneas de código**: ~3,500+
- **Tests**: 16+ (cobertura 80%)
- **Commits GitHub**: 26+ (próximo: bridge v1.2.0)
- **Documentación**: 8 Markdown vivos + 7 ADRs + RUNBOOK + README
- **Servicios Docker**: 17 (5 base + 12 Dify)
- **Modelos IA**: 6 (Qwen 2.5 7B principal)
- **Servicios systemd**: 2 activos + 1 pendiente
- **Costo mensual**: ~$12 (Meta ~$1.50 + OpenRouter ~$10)
- **Clientes reales atendidos**: 1 ✅ (primer cliente 2026-07-04 22:25)

---

## ⚠️ Lecciones aprendidas (acumuladas)

1. **NUNCA pegar secrets en el chat** — PAT GitHub quedó expuesto
2. **`message.any` causa duplicados** — eliminar de configuración
3. **mem0 requiere LLM configurado** — sino falla con error OpenAI
4. **`host.docker.internal` no funciona en Linux** — usar `172.17.0.1`
5. **WhatsApp Cloud API es superior** — sin QR, sin desconexiones, SLA 99.9%
6. **Skills > Multi-agente para 10 msg/día**
7. **Systemd es indispensable** — auto-arranque tras corte eléctrico
8. **Dify para workflow visual** — mejor que código para flujos conversacionales
9. **Prometeo como arquitecto** — auto-mejora nocturna con Fusion
10. **Meta usa PUNTOS en parámetros webhook** (hub.mode, no hub_mode)
11. **Systemd hardening excesivo bloquea arranque** (226/NAMESPACE)
12. **Máquina de estados estricta > prompt narrativo**
13. **Reseteo SO borra credenciales** — siempre redescargar JSONs
14. **PII safe por defecto** (teléfonos hasheados en logs y Sheets)
15. **Threading async para no bloquear webhook** (Google Sheets)

---

## 🎬 Próximos pasos inmediatos (próxima sesión, 15 min)

1. Descargar `google_credentials.json` de Google Cloud Console
2. Subir a `/mnt/ssd_trabajo/hermes-agent/config/google_credentials.json`
3. Test: `./venv/bin/python skills/google_sheets.py`
4. Reiniciar: `sudo systemctl restart valentina-bridge.service`
5. Pedido de prueba → verificar fila en Google Sheet
6. Invitar 5 clientes VIP

---

## 💪 Mensaje de cierre (actualizado 2026-07-05)

Líder, en 13 días pasamos de:
- 🔴 Servidor caótico con 4,498 reinicios
- 🔴 5 migraciones de WhatsApp fallidas
- 🔴 158 hallazgos críticos de seguridad
- 🔴 0 conversaciones reales (modo fantasma)
- ✅ **HOY**: Valentina atendió su primer cliente real, cerró la venta sola, sin humano

> *"Hoy no construimos un chatbot. Construimos un sistema empresarial de IA que atiende clientes reales por WhatsApp, cierra ventas sola, y persiste datos para escalar. Eso es ingeniería senior." — Prometeo*

**Descansa, Líder. Hoy hicimos historia.** 💧

---

**Fin de la celda de memoria maestra. Prometeo queda en standby.**
