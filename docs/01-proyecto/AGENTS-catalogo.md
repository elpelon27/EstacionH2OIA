# 🤖 AGENTS — Catálogo de Agentes y Skills

**Última actualización**: 2026-07-06 (Día 14 — Google Sheets funcional)

---

## 🧠 Arquitecto IA

### Prometeo (antes Hermes Agent)
- **Rol**: Arquitecto senior full-stack del proyecto
- **Decisiones**: Toma decisiones de ingeniería con carta blanca del Líder
- **Especialidades**: Frontend, APIs, backend logic, DB, auth, hosting, cloud, CI/CD, seguridad, rate limiting, cache/CDN, balanceo, monitoreo, disponibilidad, recuperación
- **Horario activo**: Cuando el Líder lo convoca
- **Standby**: Entre sesiones, mantiene celda de memoria actualizada 

---

## 💧 Agente principal (producción)

### Valentina
- **Rol**: Recepcionista WhatsApp (hardcore chatbot)
- **Ubicación**: Dify app "Valentina" + bridge FastAPI
- **Modelo**: qwen2.5:7b @ temp 0.1 (Ollama local, 0$)
- **Prompt**: System Prompt v4 (máquina 8 estados)
- **Estado**: ✅ EN PRODUCCIÓN REAL
- **Primer cliente**: 2026-07-04 22:25 -04
- **Funciones**:
  - Recibir pedidos de agua/hielo
  - Calcular total en EUR + BCV
  - Cobrar pago (móvil o efectivo)
  - Dar datos bancarios
  - Confirmar envío
  - Procesar GPS
  - Persistir en SQLite + Google Sheets

**Documentación**: Ver `01-proyecto/SOUL-valentina.md`

---

## 🛠️ Skills activas (modulo bridge)

### 1. google_sheets.py ✅ FUNCIONAL EN PRODUCCIÓN
- **Ubicación**: `/mnt/ssd_trabajo/hermes-agent/skills/google_sheets.py`
- **Función**: Guarda pedidos en hoja "Pedidos" del spreadsheet compartido
- **17 columnas**: Fecha, Hora, Cliente, Teléfono, Producto, Cant Botellones, Cant Hielo, Dirección, GPS clickable, Monto EUR, Método Pago, Pagado, Frecuencia, Crédito, Estado, Phone Hash, Conversation ID
- **Async**: thread daemon, no bloquea webhook
- **PII_SAFE=false**: guarda teléfonos REALES (decisión Líder Día 14: "los datos son ORO")
- **Spreadsheet**: "Estacion H2O-Control" (10 pestañas, 9 existentes + 1 nuestra)
- **Test de conexión**: ✅ exitoso Día 14
- **Fila TEST escrita**: ✅ (eliminar manualmente)

### 2. telegram_bot.py ⏸️ (pendiente activar)
- **Ubicación**: `/mnt/ssd_trabajo/hermes-agent/skills/telegram_bot.py`
- **Función**: Kill switch + alertas + comandos del Líder
- **7 comandos**: /status, /stop, /start, /orders, /logs, /metrics, /help
- **Seguridad**: solo chat_id 1663148211 autorizado
- **Pendiente**: `TELEGRAM_BOT_TOKEN` vacío en .env

### 3. self_improve_skill.py ⏸️ (pendiente cron)
- **Ubicación**: `/mnt/ssd_trabajo/hermes-agent/skills/self_improve_skill.py`
- **Función**: Análisis nocturno 10pm, reporte Telegram al Líder
- **Métricas**: msgs ok/error/ignored, pedidos, escalamientos, tasa éxito
- **Sugerencias**: automáticas (tasa error >10%, más escalamientos que pedidos, etc.)
- **Pendiente**: activar cron + token Telegram

### 4. Guard de horario ✅ FUNCIONAL EN PRODUCCIÓN (Día 14)
- **Ubicación**: integrado en `bridge.py`
- **Función**: Verifica hora Caracas antes de llamar a Dify
- **Horario**: Lun-Sáb 8am-6pm (BUSINESS_HOURS_DAYS=1,2,3,4,5,6)
- **Comportamiento fuera de horario**: responde mensaje programado, NO consulta Dify, guarda en SQLite como "scheduled"
- **Determinístico**: no depende del LLM
- **Tests**: 5 casos validados (Domingo, 5am, 8am, 6pm, Sábado 12pm)

---

## ⏸️ Skills planificadas (Fase 2 — Semana 4, Días 21-27)

### 5. financial_agent (próxima semana)
- **Función**: Validar pagos, gestionar créditos, anti-fraude
- **LEE**: Pedidos, Saldos_Clientes
- **ESCRIBE**: Pagos, Validacion_Pagos, Saldos_Clientes
- **Prioridad**: API bancaria sobre OCR (esperando integración cuenta)
- **Validacion_Pagos**: migrar de OCR (Qwen2.5-VL) a API bancaria cuando esté disponible

### 6. route_skill.py (próxima semana)
- **Función**: Haversine + 5 zonas Maracaibo
- **LEE**: Mapa_Calor (Sector, Calle/Avenida, Latitud, Longitud, Pasadas, Clientes_Potenciales, Ultima_Visita)
- **ESCRIBE**: Mapa_Calor (actualizar Pasadas + Ultima_Visita)
- **Carga inicial**: 5 zonas (Bella Vista, Las Delicias, La Limpia, Centro, Tierra Negra)

### 7. analytics_skill.py (próxima semana)
- **Función**: Reporte diario 7am via Telegram
- **LEE**: Ventas (Fecha, Teléfono, Producto, Monto Euro), Pedidos
- **Métricas**: pedidos día anterior, ingresos EUR, clientes nuevos, recurrencia

### 8. dispatcher.py (próxima semana)
- **Función**: Logística Telegram para chofer
- **LEE**: Pedidos (cuando Estado = "registrado" y pago confirmado)
- **ESCRIBE**: Feedback_Clientes (chofer, ID_pedido)
- **Acción**: reenvía pedido + GPS clickable al chofer por Telegram

### 9. fidelizacion_agent (Fase 2 tardía)
- **Función**: Recordatorios automáticos a clientes recurrentes
- **LEE**: Categoria_Cliente (Residencial, Oficina, Laboratorio, Clínica, Comercio, Restaurante), Aprendizaje (25 ejemplos)
- **ESCRIBE**: Categoria_Cliente, Saldos_Clientes
- **Base**: 25 ejemplos históricos en Aprendizaje (mensajes reales abril-mayo 2026)

### 10. support_skill.py (Fase 2 tardía)
- **Función**: FAQ RAG con Qdrant
- **Base**: 25 ejemplos en Aprendizaje como corpus inicial
- **Objetivo**: Responder preguntas frecuentes sin escalar a humano

### 11. mem0 + Qdrant (Semana 5)
- **Función**: Memoria de cliente (reconocer recurrentes)
- **Base inicial**: 25 ejemplos de Aprendizaje + Pedidos futuros
- **Categorización**: PEDIDO, RECLAMO, Cotización, Consulta (ya documentada en Aprendizaje)

---

## 🧩 Componentes del sistema (no agentes)

| Componente | Rol | Estado |
|-----------|-----|--------|
| Valentina Bridge (FastAPI) | Puente Meta ↔ Dify ↔ Meta | ✅ prod |
| Dify Chatbot | Workflow conversacional | ✅ prod |
| Ollama | Host de modelos IA | ✅ prod |
| Cloudflare Tunnel | HTTPS público | ✅ prod |
| SQLite | Persistencia local | ✅ prod |
| Google Sheets | Persistencia compartida | 🟡 90% |
| Prometheus | Métricas | ✅ prod |
| Grafana | Dashboards | ✅ prod |
| Qdrant | DB vectorial (mem0) | ✅ up (sin usar aún) |
| Redis | Colas (sin usar aún) | ✅ up |

---

## 📜 ADRs (Architecture Decision Records)

1. **ADR-001**: SQLite sobre PostgreSQL (volumen ~10 msg/día)
2. **ADR-002**: Single uvicorn worker sobre gunicorn (CPU limitada)
3. **ADR-003**: slowapi in-memory sobre Redis (sin infra extra)
4. **ADR-004**: Systemd direct sobre Docker para bridge (restart <2s)
5. **ADR-005**: Cloudflare Tunnel sobre nginx+dominio (HTTPS sin abrir puertos)
6. **ADR-006**: TDD obligatorio pytest+TestClient (cobertura 80%)
7. **ADR-007**: Kill switch via Telegram (chat_id verificado, <3s latencia)

---

## 🔄 Pipeline de mensaje (end-to-end)

```
1. Cliente WhatsApp envía msg
2. Meta Cloud API recibe
3. Meta hace POST a webhook (Cloudflare URL)
4. Cloudflare Tunnel reenvía a localhost:8000
5. Bridge verifica HMAC-SHA256 (APP_SECRET)
6. Bridge check kill switch
7. Bridge deduplica (message_id)
8. Bridge rate limit (30/min phone, 100/min IP)
9. Bridge parcha GPS si type=location
10. Bridge lookup conversation_id en SQLite
11. Bridge POST a Dify /v1/chat-messages
12. Dify envía a qwen2.5:7b con System Prompt v4
13. qwen2.5 genera respuesta (2-5s)
14. Dify devuelve answer + conversation_id
15. Bridge persiste conversation_id en SQLite
16. Bridge POST a Meta Graph API (envía respuesta)
17. Meta entrega respuesta a cliente WhatsApp
18. Bridge parsea respuesta (regex) para Google Sheets
19. Bridge async save_order_async (thread daemon)
20. Google Sheets recibe fila nueva
21. Bridge detecta "✅ Pedido confirmado" → ORDERS_TOTAL.inc()
22. Bridge envía alerta Telegram al Líder (si configurado)
```

---

## 📊 Métricas por agente/skill

| Agente/Skill | Mensajes hoy | Pedidos hoy | Errores | Estado |
|--------------|-------------|-------------|---------|--------|
| Valentina | 6 | 1 | 0 | ✅ prod |
| google_sheets | 0 (pendiente JSON) | 0 | 0 | 🟡 90% |
| telegram_bot | 0 (pendiente token) | - | - | ⏸️ |
| self_improve | 0 (pendiente cron) | - | - | ⏸️ |
| route_skill | - | - | - | ⏸️ Fase 2 |
| analytics_skill | - | - | - | ⏸️ Fase 2 |
| dispatcher | - | - | - | ⏸️ Fase 2 |

---

## 🎯 Próximas incorporaciones (Fase 2-3)

1. **route_skill.py** (Semana 4)
2. **analytics_skill.py** (Semana 4)
3. **dispatcher.py** (Semana 4)
4. **mem0 + Qdrant** (Semana 5) — memoria de cliente
5. **support_skill.py** (Semana 5) — FAQ RAG
6. **Telegram bot activo** (Semana 4) — kill switch
7. **CI/CD GitHub Actions** (Semana 6)

---

**Este catálogo se actualiza al añadir o modificar agentes/skills.**
