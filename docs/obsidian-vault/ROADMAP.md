# 🗺️ ROADMAP — Plan de Trabajo Vivo

**Última actualización**: 2026-07-05 (Día 13)

> Versión extendida en `/home/z/my-project/upload/ROADMAP_VIVO.md`

---

## 🎯 NORTE (no negociable)

**Construir un sistema empresarial de IA que atienda clientes de Estación H2O por WhatsApp, sin intervención humana, cerrando ventas y persistiendo datos para escalar.**

### KPIs
- >70% conversaciones sin humano
- +100% ventas en 3 meses
- 99.5% uptime horario laboral
- <$15/mes costo total

---

## ✅ COMPLETADO (Días 1-13)

### Semana 1 (Auditoría + Infra)
- ✅ Auditoría 134K líneas → 158 hallazgos
- ✅ Plano maestro + formateo servidor
- ✅ Docker + Ollama + repo GitHub
- ✅ Docker Compose + Obsidian + 8 MD
- ✅ Core Hermes (8 módulos, 65 tests)
- ✅ Memoria + Valentina + API Gateway
- ✅ WhatsApp conectado (WAHA, luego migrado)

### Semana 2 (Meta + Dify + Producción)
- ✅ Migración a Meta Cloud API oficial
- ✅ Skills (payment, inventory, self_improve)
- ✅ Systemd + Cloudflare Tunnel
- ✅ Dify 1.15.0 + Qwen 2.5 7b
- ✅ Auditoría verbatim + Kit production-grade + Prompt v4
- ✅ **DEPLOY PRODUCCIÓN REAL** (Día 13)
- ✅ **PRUEBA DE FUEGO EXITOSA** (6 msgs end-to-end)
- ✅ Patch GPS funcionando
- ✅ Google Sheets integration al 90%

---

## 🚀 PRÓXIMAS 4 SEMANAS

### Semana 3 (Días 14-20): Google Sheets + 5 clientes VIP
1. ⏸️ Descargar `google_credentials.json` (15 min)
2. ⏸️ Test conexión + pedido de prueba en Sheet
3. ⏸️ Invitar 5 clientes VIP
4. ⏸️ Monitorear 10+ pedidos reales
5. ⏸️ Ajustar prompt según feedback

### Semana 4 (Días 21-27): Telegram + Skills Fase 2
1. ⏸️ Activar Telegram bot kill switch
2. ⏸️ `route_skill.py` (Haversine + 5 zonas)
3. ⏸️ `analytics_skill.py` (reporte 7am)
4. ⏸️ `dispatcher.py` (logística Telegram)
5. ⏸️ Tests pytest para cada skill

### Semana 5 (Días 28-34): Memoria + Dominio
1. ⏸️ mem0 + Qdrant (memoria cliente)
2. ⏸️ `support_skill.py` (FAQ RAG)
3. ⏸️ Dominio propio `valentina.estacionh2o.com`
4. ⏸️ Cloudflare Tunnel estable
5. ⏸️ Backup SQLite diario automático

### Semana 6 (Días 35-41): Estabilización + CI/CD
1. ⏸️ Dashboard Grafana funcional
2. ⏸️ Alertas Prometheus → Telegram
3. ⏸️ CI GitHub Actions
4. ⏸️ Deploy manual via SSH
5. ⏸️ Métrica >70% sin humano
6. ⏸️ Eliminar Node.js legacy
7. ⏸️ ADRs finales

---

## 🛡️ PRINCIPIOS NO NEGOCIABLES

1. Skills > Multi-agente para 10 msg/día
2. qwen2.5:7b local para producción (0$)
3. Meta Cloud API oficial (no librerías no oficiales)
4. SQLite sobre PostgreSQL hasta >1000 msg/día
5. Systemd sobre Docker para el bridge
6. PII safe por defecto (teléfonos hasheados)
7. TDD obligatorio (cobertura 80%)
8. Un paso por mensaje (máquina de estados estricta)
9. 8 Markdown vivos como única fuente de verdad
10. Kill switch via Telegram solo para Líder

---

## 🚫 ANTI-PATRONES

1. ❌ Hardcodear secrets
2. ❌ Commitear `.env` o credenciales
3. ❌ Librerías WhatsApp no oficiales
4. ❌ Systemd hardening excesivo
5. ❌ Parámetros webhook con guiones bajos (Meta usa puntos)
6. ❌ Prompt narrativo ambiguo
7. ❌ Bloquear webhook en ops lentas
8. ❌ Modo fantasma (siempre responder)
9. ❌ Migrar librerías cada semana
10. ❌ Código sin tests

---

**Próximo paso inmediato**: Descargar `google_credentials.json` (Lunes 2026-07-06).
