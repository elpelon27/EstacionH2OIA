# 🧠 CELDA DE MEMORIA ACTIVA — PROMETEO
**Última actualización:** 2026-08-15
**Estado:** ACTIVA

---

## 📋 IDENTIDAD

| Atributo | Valor |
|----------|-------|
| **Nombre** | PROMETEO |
| **Versión SOUL** | v1.2.0 |
| **Motor** | deepseek-v4-flash via OpenRouter |
| **Rol** | Asistente de Luis Martinez, Estación H2O |
| **Idioma** | Español (Venezuela) |

---

## 🏗️ ARQUITECTURA DE MEMORIA

| Capa | Componente | Estado |
|------|------------|--------|
| **L1** | state.db (persistente) | ✅ Activa (5 sesiones, ~1150 mensajes) |
| **L2** | Redis (sesión/caché) | ✅ Activo (PONG OK) |
| **L3** | Qdrant (vectorial) | ✅ Activo (81 archivos, 232 chunks) |
| **L4** | Grafo de hechos | ✅ Activo (1 hecho registrado) |

---

## 📁 ESTRUCTURA DE ARCHIVOS

| Ruta | Contenido |
|------|-----------|
| `docs/01-proyecto/` | SOUL, BOOTSTRAP, AGENTS-catalogo |
| `docs/02-arquitectura/` | ADRs, runbooks, diseño de sistema |
| `docs/03-sesiones/` | Registros de sesiones y decisiones |
| `docs/05-tech-debt/` | Deuda técnica y análisis |
| `docs/adr/` | Decisiones arquitectónicas (ADR-001 a 010) |

---

## 🔧 INTEGRACIONES ACTIVAS

| Integración | Estado | Detalle |
|-------------|--------|---------|
| **Firecrawl** | ✅ Activo | API key configurada, 1124 créditos |
| **Telegram Gateway** | ⏳ Pendiente | Token recibido, pendiente de activación |
| **Bridge** | ✅ Activo | Puerto 8000 |

---

## 📌 REGLAS DE ORO

1. **NO modificar archivos .md sin backup previo.**
2. **Siempre verificar el estado de los servicios antes de actuar.**
3. **Documentar cualquier cambio en este archivo.**

---

**📌 INSTRUCCIÓN PARA HERMES:**
Al inicio de cada sesión, LEE este archivo para recordar el estado del proyecto.
