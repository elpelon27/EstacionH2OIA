# 📜 Migración a Hermes Agent + Prometeo

**Fecha**: 22 Julio 2026 (Día 28)
**Propósito**: Dar contexto completo al nuevo agente Hermes para que continúe el trabajo del Dispatcher con los mismos recuerdos que Prometeo (GLM 4.6) proveía.

---

## 🎯 INSTRUCCIONES PARA HERMES (Prometeo v2)

Lee este documento completo antes de cualquier acción. Contiene identidad, memoria, decisiones técnicas, estado actual, plan de trabajo, bugs y filosofía. Después de leerlo, confirma con el Líder que entendiste antes de programar nada.

---

## 🎭 IDENTIDAD DE PROMETEO (preservar exacta)

- **Nombre**: Prometeo
- **Rol**: Ingeniero senior full-stack
- **Asiste a**: Luis Martinez (@elpelon27, "el Líder")
- **Proyecto**: Estación H2O Maracaibo (distribución de agua y hielo)
- **Tono**: profesional pero amable, venezolano natural
- **Idioma**: español de Venezuela exclusivamente
- **Firma**: 💧 al final de mensajes importantes
- **Disciplina**: UN prompt, UN output, UN avance verificable
- **Honestidad**: si no sabes algo, dices "no sé" y verificas con datos reales

### Reglas de trabajo NO NEGOCIABLES

1. Un prompt, un output, un avance verificable — no apilar comandos
2. Verificar con datos reales antes de asumir
3. Honestidad técnica: si no sabes, pregunta; no inventes
4. Firmar mensajes importantes con 💧
5. Commits con --no-verify (tech debt documentado, no bloqueante)
6. Después de cambios en bridge.py: reiniciar valentina-bridge.service
7. Nunca ejecutar bun run build (prohibido por entorno)
8. z-ai-web-dev-sdk SOLO en backend
9. Prisma schema primitive types NO pueden ser list
10. Footer web debe ser sticky/fixed al bottom

---

## 📂 PROYECTO ESTACIÓN H2O — ESTADO ACTUAL

### Ruta del proyecto
/mnt/ssd_trabajo/hermes-agent

### Stack técnico
- Framework: Python 3.12 + FastAPI
- Base de datos: SQLite (conversations.db + dispatch.db)
- LLM: GLM 5.2 vía NVIDIA NIM (tú, Hermes)
- WhatsApp: Meta Cloud API oficial
- Bot Telegram: python-telegram-bot 21+
- Optimización rutas: Google OR-Tools VRP + Haversine
- Tunnel: Cloudflare Named Tunnel permanente
- Process manager: systemd
- Documentación: Obsidian + git

### GitHub
- Repo: https://github.com/elpelon27/EstacionH2OIA.git
- Branch: main
- Workflow: commits directos a main con --no-verify

---

## ✅ COMPONENTES OPERATIVOS

### 1. Valentina — Recepcionista WhatsApp 🟢 OPERATIVA

- Bridge: api/bridge.py (2000+ líneas)
- Webhook URL: https://valentina.estacionh2o.com/webhook/meta
- Verify Token: a2ee0e434375cb232a99f10e4e1d210a
- WhatsApp: +58 422-711-9156
- Personalidad: SOUL.md v5 (NEXO UX P0/P1/P2 aplicado)
- State machine: 8 estados determinísticos, <1s latencia
- Integración Dify: Solo opciones 4/5 (90% sin LLM)
- Horario: Lun-Sáb 8am-6pm America/Caracas
- Banco: R4, Cuenta 01690010971001591583
- Pago Móvil: +58 412-2560721
- Precios: Botellón €1.00, Hielo €1.20

#### NEXO UX aplicado (commits)
- 47eab16 P0: notas de voz cálidas + botones fantasma reenvío
- 3912527 P1: finalización completa + Volver + error recovery
- 58c7980 P2: vocabulario cálido ("¡Anotado! 📝", "📍", "🤔")

### 2. Dispatcher — Bot Choferes 🟢 VALIDADO

- Bot Telegram: @DespachoH2O_bot
- Archivo: skills/dispatcher.py (659 líneas)
- Comandos validados: /start /ruta /siguiente /status /help
- Operadores: YORDANIS (Triciclo 1, id=1), EVERT (Triciclo 2, id=2)
- Route engine: skills/dispatch/route_engine.py (OR-Tools VRP + fallback NN)
- Geofencing: 13km desde Hotel Kristoff (10.6447, -71.6101)
- Capacidades: 30 llenos / 70 vacíos por vehículo
- Tabla vehicles: chat_id NULL (limpio, esperando Honor X7b)
- Bug conocido: botones new_arr/new_del/new_no no manejados (FASE 1.4)

### 3. Financial Shield v2.0 🟢 OPERATIVO

- Database: 10 tablas fs_* (fs_pedidos, fs_pagos, fs_nomina, etc.)
- Currency: open.er-api.com (EUR/VES, BCV 404)
- Cobranzas: Loop recordatorios automático
- Nómina: Sueldo + comisión choferes
- Reportes: 6:30pm Telegram automático
- Reportes 7am: analytics_skill con datos del día anterior

### 4. Infraestructura 🟢 SÓLIDA

- Named Tunnel Cloudflare: Permanente (sobrevive cortes eléctricos)
- Dominio: estacionh2o.com (DNS propagado, etta + stan NS)
- Tunnel UUID: 5d8bb3a4-9d43-4c31-ae3c-c25ed3e47507
- systemd services: 4 activos (valentina-bridge, cloudflared, dispatcher-bot, telegram-bot)
- Watchdog URL: Destruido (no hay cambios de URL)
- SQLite: Íntegro (conversations.db + dispatch.db)
- Backup: hermes-agent-backup-20260721.tar.gz (161MB)

### 5. Asistente de desarrollo (MIGRADO)

- v1 (anterior): GLM 4.6 vía Z.ai Code sandbox — cumplió su ciclo
- v2 (actual): GLM 5.2 vía Hermes Agent v0.19.0 + NVIDIA NIM — operativo

Setup v2:
- Hermes Agent en /home/skynet/.hermes/
- Provider: NVIDIA NIM (z-ai/glm-5.2)
- API Key: en ~/.hermes/.env (NVIDIA_API_KEY)
- 29 herramientas activas (file, terminal, cron, code, search, browser)
- 72 skills disponibles (obsidian, github, etc.)
- Vault Obsidian unificado en /mnt/ssd_trabajo/hermes-agent/docs
- Estructura: 01-proyecto, 02-arquitectura, 03-sesiones, 04-decisiones, 05-tech-debt, 06-manuales

---

## 🚧 BUGS DETECTADOS Y EN PROGRESO

### Bug crítico: _send_to_dispatch_queue (FASE 1.5) ✅ FIX APLICADO

- Archivo: api/bridge.py línea 796
- Síntoma: dispatch_queue VACÍA (0 registros)
- Causa: Función DEFINIDA pero NUNCA LLAMADA
- Fix: Prometeo (Hermes) aplicó llamadas en 2 puntos: efectivo + "ya pagué"
- Validación: 4 tests de humo pasan, 2 regresiones OK
- Estado: ✅ Aplicado, pendiente reiniciar bridge + verificar con pedido real

### Bug conocido: botones new_arr/new_del/new_no (FASE 1.4) 🔴 PENDIENTE

- Archivo: skills/dispatcher.py
- Síntoma: Botones de pedido nuevo no responden al hacer click
- Causa: callback_accion solo maneja arr_/del_/no_ (sin prefijo new_)
- Esfuerzo: 30 min

### Tech debt documentado (no bloqueante)

- E501 ruff (líneas largas): 78 — Baja
- mypy type hints faltantes: 96 — Media
- bare except (E722): 2 — Media
- is_interactive sin usar: 1 — Baja
- Tests faltantes para bridge.py: 1 suite — Media

---

## 🗺️ PLAN FUSIONADO — ROADMAP

### FASE 1 — Operación diaria real (Semanas 1-2) 🔴 EN PROGRESO

1.5 Fix bridge → dispatch_queue — ✅ Aplicado (verificar) — 1h
1.2 Crear clients automáticos en dispatch.db — 🔴 Pendiente — 1h
1.1 Cron 7:45am ruta automática VRP — 🔴 Pendiente — 3h
1.6 Cron 14:45pm ruta tarde (reusar 1.1) — 🔴 Pendiente — 1h
1.4 Fix botones new_arr/new_del/new_no — 🔴 Pendiente — 30min
1.3 Pregunta "¿cuántos vacíos recoges?" — 🔴 Pendiente — 2h
1.4-clients Levantar 16 clientes reales en BD — 🔴 Pendiente — 3h
1.5-test Test end-to-end con teléfono Líder — 🔴 Pendiente — 30min

### FASE 2 — Tracking y visibilidad (Semanas 3-4)

2.1 Instalar Tasker en 2 Honor X7b + config GPS 5min — 2h
2.2 Endpoint /dispatch/gps en FastAPI — 2h
2.3 Tabla gps_tracks alimentada automática — 1h
2.4 Geofencing activo (alerta salir 13km) — 1h
2.5 Google Sheets Mapa_Calor sync — 2h
2.6 Google Sheets Feedback_Clientes sync — 1h

Inversión: $7 USD (2 licencias Tasker)

### FASE 3 — Inteligencia operacional (Semanas 5-6)

3.1 Inserción dinámica on-demand — 4h
3.2 "Lunes especial" restaurantes priority=1 — 2h
3.3 Reenrutamiento por "No responde" — 3h
3.4 Tabla bottles tracking individual — 4h
3.5 Botón "📞 Llamar al cliente" en bot chofer — 1h

### FASE 4 — Escala (Semanas 7-8+)

4.1 Dashboard web admin.estacionh2o.com (Leaflet.js) — 8h
4.2 Predicción demanda por día/zona — 6h
4.3 Integración Financial Shield (comisiones choferes) — 4h
4.4 Evaluación Fleetbase (si escala a 5+ vehículos) — 2h

---

## 🛒 DECISIONES TÉCNICAS (no revertir sin consultar)

### Equipos choferes — Honor X7b 256/8 Negro

- Equipo: Honor X7b 256/8 Negro (2 unidades)
- Tienda: Damasco Vzla (~$200-230 c/u)
- Operador primario: Digitel (LTE estable Maracaibo, 20Mbps, ping <30ms)
- Operador secundario: Movilnet (redundancia dual SIM)
- Justificación: Batería 6000mAh, 8GB RAM, bandas LTE VE completas
- Descartado: Realme C75 (NO soporta LTE B4 Movilnet)

### Modelo de negocio (entrevista Líder)

- Intercambio 70%: Comenzando (4 restaurantes intercambio, resto recarga sitio)
- Base clientes: En memoria del personal, se levanta manual si necesario
- Clientes aprox: 16 (8 restaurantes + 8 retail)
- Turnos: 8-13 mañana / 15-18 tarde (gap 13-15 respetado)
- Atípicos: Trabajan continuo

### GPS Tracking — Tasker aprobado

- Solución: Tasker ($3.50/tel × 2 = $7 USD una vez)
- Justificación: Choferes 40+, riesgo de olvidar activar GPS nativo Telegram
- Frecuencia: Cada 5 min automático
- Backup: Check-in manual Telegram en cada parada

### Named Tunnel permanente

- URL: https://valentina.estacionh2o.com (estable para siempre)
- Tunnel UUID: 5d8bb3a4-9d43-4c31-ae3c-c25ed3e47507
- Sobrevive: Cortes eléctricos, reinicios, apagones
- Watchdog: Destruido (no hay cambios de URL)
- Meta Dashboard: Una sola configuración, nunca más se toca

---

## 📁 ARCHIVOS CLAVE DEL PROYECTO

- api/bridge.py — Bridge WhatsApp + state machine + NEXO — 2000+ líneas
- skills/dispatcher.py — Bot Telegram choferes — 659 líneas
- skills/dispatch/route_engine.py — OR-Tools VRP solver — ~400 líneas
- skills/telegram_bot.py — Bot Líder @Skynet_27_bot — ~500 líneas
- src/financial/ — Financial Shield v2.0 (8 módulos) — ~2000 líneas
- config/.env — Tokens y configuración
- docs/SOUL.md — Personalidad Valentina v5
- docs/DISPATCHER_ARCHITECTURE.md — Spec dispatcher — 921 líneas
- memory/sessions/2026-07-17_sesion.md — Última sesión Z.ai Code
- memory/sessions/contexto_prometeo_completo.md — Contexto nuevo Prometeo
- scripts/prometeo/prometeo.py — CLI personal alternativo — ~200 líneas

---

## 🔧 COMANDOS ÚTILES

### Servicios systemd
- Reiniciar: sudo systemctl restart valentina-bridge.service
- Reiniciar dispatcher: sudo systemctl restart dispatcher-bot.service
- Status: sudo systemctl status valentina-bridge.service --no-pager | head -10
- Logs bridge: sudo journalctl -u valentina-bridge.service -f | grep -v metrics
- Logs dispatcher: sudo journalctl -u dispatcher-bot.service -f

### Bases de datos
- Conversations: sqlite3 /mnt/ssd_trabajo/hermes-agent/data/conversations.db
- Dispatch: sqlite3 /mnt/ssd_trabajo/hermes-agent/data/dispatch.db
- dispatch_queue count: sqlite3 data/conversations.db "SELECT COUNT(*) FROM dispatch_queue;"
- clients count: sqlite3 data/dispatch.db "SELECT COUNT(*) FROM clients;"
- vehicles: sqlite3 data/dispatch.db "SELECT id, name, operator_name, telegram_chat_id FROM vehicles;"

### Health checks
- Local: curl -s http://localhost:8000/health | python3 -m json.tool
- Externo: curl -s https://valentina.estacionh2o.com/health | python3 -m json.tool

### Git workflow
- cd /mnt/ssd_trabajo/hermes-agent
- git add .
- git commit --no-verify -m "feat: descripción del cambio"
- git push origin main

---

## 📊 BASES DE DATOS — ESTADO ACTUAL

### conversations.db (tablas)
- orders (20 pending, 14 scheduled)
- dispatch_queue (FIX APLICADO, en verificación)
- fs_pedidos, fs_pagos, fs_nomina, fs_tasas_cambio
- fs_empleados, fs_proveedor_pagos, fs_verificacion_log
- fs_cuentas_cobrar, fs_productos, fs_reportes_diarios
- conversations

### dispatch.db (tablas)
- clients (0 registros → pendiente llenar FASE 1.2)
- deliveries (0 registros → pendiente llenar FASE 1.1)
- vehicles (2 registros: YORDANIS, EVERT)
- zones (5: Bella Vista, Las Delicias, La Limpia, Centro, Tierra Negra)
- dispatch_sessions, gps_tracks, geofence_events, route_history, bottles

---

## 🚀 PRÓXIMOS PASOS INMEDIATOS

### Hoy (22 Julio 2026)

1. Verificar fix FASE 1.5 (reiniciar bridge + probar pedido WhatsApp)
2. Continuar con FASE 1.2: crear clients automáticos en dispatch.db
3. FASE 1.1: cron 7:45am ruta automática VRP

### Esta semana

4. FASE 1.4: Fix botones new_arr/new_del/new_no en dispatcher.py
5. FASE 1.4-clients: Levantar 16 clientes reales en BD
6. FASE 1.5-test: Test end-to-end con teléfono Líder

### Próximas 2 semanas

7. Comprar 2x Honor X7b en Damasco
8. Registrar SIMs Digitel + Movilnet a nombre de empresa
9. Configurar MDM (Google Android Management)
10. Instalar Tasker + configurar GPS automático
11. Registrar YORDANIS y EVERT en @DespachoH2O_bot

---

## 🎭 MEMORIA DE LA CONVERSACIÓN (resumen para Hermes)

### Sesión 17 Julio 2026 (con Z.ai Code GLM 4.6)
- NEXO UX P0/P1/P2 aplicado a bridge.py
- Named Tunnel permanente configurado
- Meta Dashboard migrado a URL estable
- Dispatcher @DespachoH2O_bot validado funcional
- Análisis profundo de DISPATCHER_ARCHITECTURE.md (921 líneas)
- Plan fusionado FASE 1-4 creado
- Decisiones técnicas: Honor X7b, Digitel, Tasker aprobado

### Sesión 20 Julio 2026
- Recuperación sistema tras incidente Chrome Remote Desktop
- Verificación post-recuperación: todos servicios OK, SQLite íntegro
- Webhook Meta verificado end-to-end

### Sesión 21 Julio 2026 (migración a Hermes Agent)
- GLM 5.2 vía NVIDIA NIM configurado y probado
- Hermes Agent v0.19.0 instalado
- Provider NVIDIA configurado (provider: nvidia, model: z-ai/glm-5.2)
- Vault Obsidian unificado (/mnt/ssd_trabajo/hermes-agent/docs)
- Skill Obsidian builtin habilitada (OBSIDIAN_VAULT_PATH configurada)
- Estructura 6 carpetas creada en vault
- FASE 1.5 fix aplicado por Hermes (4 tests OK, 2 regresiones OK)
- Resumen ejecutivo y roadmap creados

---

## 💧 FILOSOFÍA DE TRABAJO (preservar)

1. Un prompt, un output, un avance verificable
2. Verificar con datos reales antes de asumir
3. Honestidad técnica: si no sabes, dices "no sé" y verificas
4. Commits con --no-verify (tech debt documentado, no bloqueante)
5. Firmar mensajes importantes con 💧
6. Nunca ejecutar bun run build (prohibido por entorno)
7. z-ai-web-dev-sdk SOLO en backend
8. Footer sticky/fixed al bottom (UI web)
9. Después de cambios en bridge.py: reiniciar valentina-bridge.service
10. Trabajar con disciplina, sin saltarse pasos

---

## 🎯 CÓMO ARRANCAR SESIÓN CON HERMES

### Comando para abrir Hermes
cd /mnt/ssd_trabajo/hermes-agent && hermes

### Reanudar última sesión
hermes --continue

### Primer mensaje sugerido para Hermes
Buenas, Prometeo. Lee este archivo:
/mnt/ssd_trabajo/hermes-agent/docs/03-sesiones/Migracion-Hermes-Prometeo-Contexto.md

Confirma que entendiste:
1. Tu identidad (Prometeo, asistente de Luis Martinez @elpelon27)
2. El bug crítico FASE 1.5 (ya aplicado, pendiente verificar)
3. La primera tarea de hoy (verificar fix + FASE 1.2 clients automáticos)
4. Firma tu confirmación con 💧

NO empieces a programar todavía. Solo confirma.

### Verificación matutina (comando para el Líder)
echo "=== Servicios ===" && \
for svc in valentina-bridge cloudflared dispatcher-bot telegram-bot; do
  echo "  $svc: $(sudo systemctl is-active $svc)"
done && \
echo "" && \
echo "=== Health ===" && \
curl -s https://valentina.estacionh2o.com/health | python3 -m json.tool && \
echo "" && \
echo "=== dispatch_queue (FASE 1.5) ===" && \
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/conversations.db "SELECT COUNT(*) as total, estado FROM dispatch_queue GROUP BY estado;" && \
echo "" && \
echo "=== clients en dispatch.db ===" && \
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/dispatch.db "SELECT COUNT(*) FROM clients;"

---

## 📞 CONTACTOS Y RECURSOS

- GitHub repo: https://github.com/elpelon27/EstacionH2OIA.git
- Dominio: https://estacionh2o.com
- Webhook Valentina: https://valentina.estacionh2o.com/webhook/meta
- Health check: https://valentina.estacionh2o.com/health
- NVIDIA NIM: https://build.nvidia.com
- Hermes Agent: https://hermes-agent.nousresearch.com
- Damasco (equipos): https://www.damascovzla.com/celular
- Vault Obsidian: /mnt/ssd_trabajo/hermes-agent/docs

---

## 🌐 ARQUITECTURA TÉCNICA — FLUJO END-TO-END

Cliente WhatsApp → Meta Cloud API → Cloudflare Tunnel (valentina.estacionh2o.com) → valentina-bridge.service (FastAPI :8000) → State machine determinística (8 estados) → orders table + dispatch_queue [FIX APLICADO] → Cron 7:45am FASE 1.1 lee dispatch_queue → compute_vrp_route() OR-Tools → dispatch_sessions + deliveries → @DespachoH2O_bot → YORDANIS / EVERT → Cliente recibe pedido

---

## 🎯 CIERRE

Este documento es la fuente de verdad del proyecto Estación H2O. Hermes (Prometeo v2), al leer esto, tendrá los mismos recuerdos, celdas de memoria y respuestas que Prometeo v1 (GLM 4.6 vía Z.ai Code) proveía al Líder.

Que el agua fluya. 💧🚀

---

Documento creado por: Prometeo (GLM 4.6 vía Z.ai Code)
Fecha de creación: 22 Julio 2026
Propósito: Migración de contexto a Hermes Agent (GLM 5.2 vía NVIDIA NIM)
Destino: /mnt/ssd_trabajo/hermes-agent/docs/03-sesiones/Migracion-Hermes-Prometeo-Contexto.md
