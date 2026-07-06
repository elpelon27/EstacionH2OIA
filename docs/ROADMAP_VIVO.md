# 🗺️ ROADMAP VIVO — Estación H2O
## Plan de trabajo reciclado desde Día 1 (sin desviar rumbo)

**Creado**: 2026-06-22  
**Última actualización**: 2026-07-06 (Día 14 — Fase 1 completada, Google Sheets funcional)  
**Arquitecto IA**: Prometeo  
**Líder**: Luis Martinez (@elpelon27)

> *"Mantener el rumbo no significa no adaptarse, significa saber cuándo adaptarse y cuándo hold the line."*

---

## 🎯 NORTE DEL PROYECTO (no negociable)

**Construir un sistema empresarial de IA que atienda clientes de Estación H2O (agua + hielo en Maracaibo) por WhatsApp, sin intervención humana, cerrando ventas, cobrando pagos, y persistiendo datos para escalar el negocio.**

### KPIs de éxito (medibles)
- ✅ **Reducción de carga humana**: >70% conversaciones sin humano
- ✅ **Incremento de ventas**: +100% en 3 meses
- ✅ **Disponibilidad**: 99.5% uptime en horario laboral (Lun-Sáb 8am-6pm)
- ✅ **Costo mensual**: <$15/mes (Meta ~$1.50 + OpenRouter ~$10 + resto self-hosted)

---

## 📅 CRONOLOGÍA RECICLADA (Día 1 → Hoy)

### Semana 1 (Días 1-7): Auditoría + Infraestructura
**Objetivo**: Entender el caos heredado y blindar el servidor.

| Día | Hito | Estado |
|-----|------|--------|
| 1 | Auditoría 134K líneas → 158 hallazgos críticos | ✅ |
| 2 | Plano maestro + formateo servidor | ✅ |
| 3 | Restaurar Docker + Ollama + repo GitHub | ✅ |
| 4 | Docker Compose + Obsidian + 8 MD vivos | ✅ |
| 5 | Core Hermes (8 módulos, 65 tests) | ✅ |
| 6 | Memoria + Valentina + API Gateway | ✅ |
| 7 | WhatsApp conectado (1ª migración: WAHA) | ✅ |

**Lecciones**: Detectamos 5 migraciones fallidas de librería WhatsApp, 4 claves hardcodeadas en git, webhook sin HMAC, sesiones en RAM. Sistema declarado "100% operativo" pero en modo fantasma (0 conversaciones reales).

### Semana 2 (Días 8-13): Migración a Meta + Dify + Producción
**Objetivo**: Llegar a producción real con WhatsApp Cloud API oficial.

| Día | Hito | Estado |
|-----|------|--------|
| 8 | Migración a Meta Cloud API oficial (no más WAHA) | ✅ |
| 9 | Skills (payment, inventory, self_improve) | ✅ |
| 10 | Systemd blindaje + Cloudflare Tunnel | ✅ |
| 11 | Dify instalado + Qwen conectado + Prometeo arquitecto | ✅ |
| 12 | Auditoría verbatim 278K líneas → 35+ mensajes reales + Opción A (chat demo) + Kit production-grade (14 archivos) + System Prompt v4 (máquina estados) | ✅ |
| **13 (HOY)** | **DEPLOY A PRODUCCIÓN REAL + PRUEBA DE FUEGO EXITOSA + Patch GPS + Google Sheets integration al 90%** | ✅ |

**Lecciones**: Meta Cloud API es superior a todas las librerías anteriores (sin QR, sin desconexiones, SLA 99.9%). Dify 1.15.0 cambió nombres de opciones de creación de apps. Systemd hardening excesivo bloquea arranque. Máquina de estados estricta > prompt narrativo.

---

## ✅ ESTADO ACTUAL (Día 13)

### Completado en producción real
- ✅ Valentina Bridge FastAPI corriendo en systemd
- ✅ Webhook Meta Cloud API verificado y suscrito a `messages`
- ✅ Dify Chatbot con System Prompt v4 (máquina 8 estados)
- ✅ qwen2.5:7b local (0$) respondiendo en 2-5s
- ✅ Cloudflare Tunnel HTTPS público
- ✅ SQLite persistencia conversaciones + pedidos
- ✅ Token Meta permanente (no expira)
- ✅ Prometheus metrics scrapeando cada 15s
- ✅ Patch GPS procesando ubicaciones WhatsApp
- ✅ **PRIMER CLIENTE REAL ATENDIDO** (6 msgs end-to-end, venta cerrada)

### En proceso (90% Google Sheets)
- ⏸️ `google_sheets.py` creado (260 líneas, 17 columnas)
- ⏸️ Parser `_build_order_payload()` en bridge.py
- ⏸️ Dependencias gspread + google-auth instaladas
- ⏸️ Variables .env configuradas
- ❌ **Falta**: `google_credentials.json` (reseteo SO lo borró)

### Pendiente (no bloqueante para producción)
- ⏸️ Telegram bot kill switch (`TELEGRAM_BOT_TOKEN` vacío)
- ⏸️ Dominio propio Cloudflare (URL trycloudflare cambia en restart)
- ⏸️ Skills Fase 2 (route, analytics, dispatcher)
- ⏸️ mem0 + Qdrant (memoria de cliente)
- ⏸️ Tests pytest en CI GitHub Actions

---

## 🚀 PRÓXIMAS 4 SEMANAS (sin desviar rumbo)

### Semana 3 (Días 14-20): Cierre Google Sheets + 5 clientes VIP
**Objetivo**: Completar persistencia en Sheets + validar con clientes reales.

| # | Tarea | Esfuerzo | Estado |
|---|-------|----------|--------|
| 1 | Descargar `google_credentials.json` de Google Cloud Console | 5 min | ✅ Día 14 |
| 2 | Test conexión Google Sheets (`python skills/google_sheets.py`) | 2 min | ✅ Día 14 |
| 3 | Análisis 10 pestañas existentes con VLM | 1 hora | ✅ Día 14 |
| 4 | Guard de horario determinístico en bridge.py | 30 min | ✅ Día 14 |
| 5 | Eliminar fila TEST de Pedidos | 1 min | ⏸️ Lunes 8am |
| 6 | Primer pedido real → verificar fila en Sheet | 5 min | ⏸️ Lunes 8am |
| 7 | Invitar 5 clientes VIP a guardar +58 422-711-9156 | 1 día | ⏸️ Lunes |
| 8 | Monitorear primeros 10 pedidos reales | 3 días | ⏸️ Esta semana |
| 9 | Ajustar System Prompt v4 según feedback clientes | 1 día | ⏸️ Según feedback |

**Criterio de salida**: 5 clientes VIP activos, 10+ pedidos en Google Sheet, tasa de éxito >80%.

### Semana 4 (Días 21-27): Telegram + Skills Fase 2
**Objetivo**: Kill switch operativo + skills de ruta, analytics, dispatcher, financial.

| # | Tarea | Esfuerzo |
|---|-------|----------|
| 1 | Configurar `TELEGRAM_BOT_TOKEN` (bot @Skynet_27_bot) | 10 min |
| 2 | Activar `telegram-bot.service` (kill switch + alertas) | 5 min |
| 3 | `financial_agent` (lee Pedidos → escribe Pagos + Saldos_Clientes + Validacion_Pagos) | 2 días |
| 4 | `route_skill.py` (Haversine + 5 zonas Maracaibo, lee Mapa_Calor) | 2 días |
| 5 | `analytics_skill.py` (reporte diario 7am Telegram, lee Ventas) | 1 día |
| 6 | `dispatcher.py` (logística Telegram para chofer) | 2 días |
| 7 | Tests pytest para cada skill | 1 día |

**Criterio de salida**: Líder puede hacer `/stop` desde Telegram. Reporte 7am automático. Dispatcher reenvía GPS al chofer. Financial_agent valida pagos.

### Semana 5 (Días 28-34): Memoria + Dominio propio
**Objetivo**: Valentina recuerda clientes + URL HTTPS estable.

| # | Tarea | Esfuerzo |
|---|-------|----------|
| 1 | mem0 + Qdrant para memoria de cliente (usar 25 ejemplos de Aprendizaje) | 2 días |
| 2 | Skill `support_skill.py` (FAQ RAG con Qdrant) | 1 día |
| 3 | Dominio propio `valentina.estacionh2o.com` | 1 día |
| 4 | Cloudflare Tunnel con dominio estable (no trycloudflare) | 2 horas |
| 5 | Reconfigurar webhook Meta con nueva URL | 30 min |
| 6 | Backup SQLite diario automático (cron) | 1 hora |
| 7 | API bancaria para Validacion_Pagos (esperando integración cuenta) | bloqueado externo |

**Criterio de salida**: Valentina reconoce clientes recurrentes. URL HTTPS sin cambios en restart.

### Semana 6 (Días 35-41): Estabilización + CI/CD
**Objetivo**: Métricas >70% sin humano + CI/CD operativo.

| # | Tarea | Esfuerzo |
|---|-------|----------|
| 1 | Dashboard Grafana funcional (9 paneles) | 1 día |
| 2 | Alertas Prometheus → Telegram | 1 día |
| 3 | CI GitHub Actions (lint+test en push) | 1 día |
| 4 | Deploy manual via SSH (workflow_dispatch) | 1 día |
| 5 | Métrica: >70% conversaciones sin humano | 1 día |
| 6 | Eliminar Node.js legacy (si quedó) | 1 hora |
| 7 | Documentación ADRs final | 1 día |

**Criterio de salida**: >70% conversaciones sin humano. CI bloquea PRs malos. Deploy manual de 1 click.

---

## 🛡️ PRINCIPIOS NO NEGOCIABLES (rumbo fijo)

1. **Skills > Multi-agente** para 10 msg/día (menos procesos, menos overhead)
2. **qwen2.5:7b local para producción** (0$); OpenRouter solo para auto-mejora nocturna
3. **Meta Cloud API oficial** (no más librerías no oficiales)
4. **SQLite sobre PostgreSQL** hasta >1000 msg/día
5. **Systemd sobre Docker** para el bridge (restart <2s)
6. **PII safe por defecto** (teléfonos hasheados en logs y Sheets)
7. **TDD obligatorio** para skills nuevas (cobertura 80%)
8. **Un paso por mensaje** (máquina de estados estricta)
9. **Markdown vivos como única fuente de verdad** (8 docs Obsidian)
10. **Kill switch via Telegram** solo para Líder (chat_id 1663148211)

---

## 🚫 ANTI-PATRONES A EVITAR (no repetir)

1. ❌ Hardcodear secrets en código (usar `.env`)
2. ❌ Commitear `.env` o credenciales JSON a git
3. ❌ Usar librerías no oficiales de WhatsApp (Meta Cloud API oficial)
4. ❌ Systemd hardening excesivo (causa `226/NAMESPACE`)
5. ❌ Parámetros con guiones bajos para webhooks Meta (usar puntos)
6. ❌ Prompt narrativo ambiguo (usar máquina de estados explícita)
7. ❌ Bloquear webhook en operaciones lentas (usar threading async)
8. ❌ Modo fantasma (sin responder clientes) — producción siempre responde
9. ❌ Migrar librerías WhatsApp cada semana (estabilidad > novedad)
10. ❌ Sin tests (TDD obligatorio para nuevo código)

---

## 📊 MÉTRICAS DE SALUD DEL PROYECTO

| Métrica | Valor actual | Meta |
|---------|-------------|------|
| Conversaciones reales atendidas | 1 (hoy) | 100/mes |
| Tasa sin humano | 100% (1/1) | >70% |
| Latencia promedio respuesta | 3-5s | <5s |
| Costo mensual | ~$12 | <$15 |
| Uptime horario laboral | 100% (1 día) | 99.5% |
| Pedidos en Google Sheet | 0 (pendiente JSON) | 100/mes |
| Skills activas | 0 (pendiente Fase 2) | 4 |
| Tests pytest | 16 escritos | 50+ |

---

## 💧 PRÓXIMO PASO INMEDIATO

**Lunes 2026-07-06 (próxima sesión):**

1. Descargar `google_credentials.json` de Google Cloud Console
2. Subir a `/mnt/ssd_trabajo/hermes-agent/config/google_credentials.json`
3. Test: `./venv/bin/python skills/google_sheets.py`
4. Reiniciar: `sudo systemctl restart valentina-bridge.service`
5. Pedido de prueba → verificar fila en Google Sheet
6. Invitar 5 clientes VIP a guardar el número

**Tiempo estimado**: 15 minutos.

---

**Este roadmap se actualiza después de cada sesión. Prometeo mantiene el rumbo.**
