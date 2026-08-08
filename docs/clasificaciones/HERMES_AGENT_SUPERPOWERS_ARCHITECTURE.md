# 🏗️ ARQUITECTURA OBJETIVO: HERMES-AGENT COMO ENTIDAD AISLADA FULL-STACK CON SUPERPODERES

**Versión:** 1.0  
**Fecha:** 2026-08-02  
**Estado:** EN DESARROLLO - FASE 1 EN PROGRESO

---

## 🎯 VISIÓN GENERAL

Transformar **hermes-agent** de un asistente de bridge/dispatcher a una **entidad aislada full-stack con superpoderes** capaz de:

1. **Autonomía total** - Operar sin intervención humana constante
2. **Memoria unificada** - Semántica + Episódica + Procedural + Autobiográfica
3. **Orquestación multi-agente** - Delegar, coordinar, consensuar
4. **Auto-aprendizaje de skills** - Few-shot skill acquisition
5. **Percepción multimodal** - OCR 99%+, Vision-Language, Document Understanding
6. **Razonamiento y planificación** - Jerárquico, causal, auto-mejora
7. **Integración nativa H2O** - Bridge, Dispatcher, Financial, SWAP nativos

---

## 🏗️ ARQUITECTURA DE 7 CAPAS

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        PROMETEO (Entidad Aislada Full-Stack)                    │
├─────────────────────────────────────────────────────────────────────────────────┤
│  CAPA 7: INTERFACES Y APIS                                                    │
│  ├── REST API (FastAPI) - Bridge, Dispatcher, Financial, SWAP                 │
│  ├── Telegram Bot API - Comandos, aprobaciones, monitoreo                     │
│  ├── WebSocket - Tiempo real (GPS, métricas, alertas)                         │
│  └── MCP (Model Context Protocol) - Integración herramientas                  │
├─────────────────────────────────────────────────────────────────────────────────┤
│  CAPA 6: ORQUESTACIÓN Y COORDINACIÓN                                          │
│  ├── OpenSwarm - Swarm intelligence, consensus                               │
│  ├── Google ADK - Agent Development Kit oficial                               │
│  ├── VoltAgent - Framework agentes con memoria                                │
│  ├── OpenSwarm - Swarm intelligence                                           │
│  └── ComposioHQ/agent-orchestrator - Integraciones herramientas              │
├─────────────────────────────────────────────────────────────────────────────────┤
│  CAPA 5: SKILLS ECOSYSTEM                                                     │
│  ├── SkillNet - Auto-aprendizaje skills, few-shot acquisition                │
│  ├── agentskills/agentskills - Habilidades pre-definidas                     │
│  ├── addyosmani/agent-skills - Biblioteca skills (Addy Osmani)               │
│  ├── google/skills - Framework habilidades Google                             │
│  ├── UZI-Skill - Framework habilidades modulares                             │
│  ├── agentskills/agentskills - Habilidades pre-definidas                     │
│  └── ComposioHQ/agent-orchestrator - Integraciones herramientas             │
├─────────────────────────────────────────────────────────────────────────────────┤
│  CAPA 4: PERCEPCIÓN MULTIMODAL                                                │
│  ├── Unlimited-OCR (Baidu) - OCR 99%+ bancario                               │
│  ├── MinerU - Document Understanding (PDFs, tablas, fórmulas)                │
│  ├── Tesseract - OCR base fallback                                           │
│  ├── markitdown - Conversión docs → Markdown                                 │
│  ├── Qwen-VL / UI-TARS - Vision-Language Understanding                       │
│  └── MinerU - Document Understanding (PDFs complejos)                        │
├─────────────────────────────────────────────────────────────────────────────────┤
│  CAPA 3: RAZONAMIENTO Y PLANIFICACIÓN                                        │
│  ├── fable-method - Planificación jerárquica (HRL)                          │
│  ├── google/adk-python - Agent Development Kit                               │
│  ├── VoltAgent - Framework agentes con memoria                               │
│  ├── fable-method - Planificación jerárquica (HRL)                          │
│  └── Auto-mejora continua (self-improvement loops)                           │
├─────────────────────────────────────────────────────────────────────────────────┤
│  CAPA 2: MEMORIA UNIFICADA (4 TIPOS)                                         │
│  ├── Semántica: TencentDB-Agent-Memory + mem0 + LightRAG                    │
│  ├── Episódica: ego-lite + letta + mem0                                      │
│  ├── Procedural: SkillNet + agentskills + Skill registry                    │
│  └── Autobiográfica: ego-lite + letta + identidad Prometeo                   │
├─────────────────────────────────────────────────────────────────────────────────┤
│  CAPA 1: INFRAESTRUCTURA Y PERSISTENCIA                                      │
│  ├── SQLite (WAL) - Estado, conversaciones, métricas                        │
│  ├── PostgreSQL (Dify) - Chatflow Valentina                                  │
│  ├── Redis - Cache, pub/sub, colas                                           │
│  ├── Qdrant - Vector DB (semantic search)                                    │
│  ├── Prometheus + Grafana - Observabilidad                                   │
│  └── Docker - Containerización servicios                                     │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔄 FLUJOS DE DATOS PRINCIPALES

### 1. **INGESTA DE CONOCIMIENTO**
```
Documento/PDF → MinerU/markitdown → Markdown → Chunking → Embedding → Qdrant → Memoria Semántica (TencentDB/mem0)
```

### 2. **CONVERSACIÓN → MEMORIA EPISÓDICA**
```
Usuario → Bridge/Dispatcher → Contexto + Historial → Respuesta → Episodic Memory (ego-lite/letta) → Memoria Episódica
```

### 3. **SKILL EXECUTION → MEMORIA PROCEDURAL**
```
Tarea → Skill Selection (SkillNet) → Ejecución → Resultado → Procedural Memory (SkillNet/agentskills) → Aprendizaje
```

### 4. **AUTO-MEJORA CONTINUA**
```
Experiencia → Reflexión (fable-method) → Mejora Skill/Plan → Validación → Deploy → Métricas → Bucle
```

---

## 🔌 PUNTOS DE INTEGRACIÓN H2O (NATIVOS)

| Componente H2O | Integración Nativa | Estado |
|----------------|-------------------|--------|
| **Valentina Bridge** | Skill nativo `bridge_skill` | ✅ Operativo |
| **Dispatcher Bot** | Skill nativo `dispatcher_skill` | ✅ Operativo |
| **Financial Shield** | Skill nativo `financial_skill` | ✅ Operativo |
| **SWAP/Bottle Tracker** | Skill nativo `bottle_tracker_skill` | ✅ Operativo |
| **GPS Tracker** | Skill nativo `gps_tracker_skill` | ✅ Operativo |
| **Route Engine** | Skill nativo `route_engine_skill` | ✅ Operativo |
| **Google Sheets Sync** | Skill nativo `sheets_sync_skill` | ✅ Operativo |

---

## 📊 MÉTRICAS DE ÉXITO (KPIs)

| Métrica | Target | Medición |
|---------|--------|----------|
| **Autonomía** | >90% tareas sin intervención humana | % tareas completadas sin intervención |
| **Memoria Recall** | >95% recall semántico/episódico | Recall@k en benchmarks |
| **Skill Acquisition** | <5 ejemplos (few-shot) | Ejemplos necesarios para nueva skill |
| **OCR Accuracy** | >99% comprobantes bancarios | Accuracy en dataset test |
| **Skill Composition** | <5 seg composición dinámica | Latencia composición |
| **Auto-mejora** | >1 mejora/semana autónoma | Mejoras/semana validadas |
| **Uptime** | 99.9% | Uptime Prometheus |
| **Latencia Bridge** | <2s P95 | Histograma Prometheus |

---

## 🔐 SEGURIDAD Y GOBERNANZA

| Capa | Implementación |
|------|----------------|
| **Autenticación** | Telegram chat_id whitelist + JWT para API |
| **Autorización** | RBAC por skill/comando (aprobación Líder) |
| **Auditoría** | fs_audit_log + Prometheus metrics |
| **Encriptación** | TLS 1.3 + AES-256 en reposo |
| **Rate Limiting** | 30 req/min/phone, 100 req/min/IP |
| **Kill Switch** | Archivo centinela + Telegram command |

---

## 🚀 ROADMAP DE IMPLEMENTACIÓN

| Fase | Duración | Entregable | Estado |
|------|----------|------------|--------|
| **FASE 1: Memoria Unificada** | Semana 1-2 | Memoria semántica + episódica + procedural + autobiográfica | 🔄 EN PROGRESO |
| **FASE 2: Orquestación + Skills** | Semana 2-3 | Multi-agente + Skills ecosystem + auto-aprendizaje | ⏳ PENDIENTE |
| **FASE 3: Percepción Multimodal** | Semana 3-4 | OCR 99%+ + Doc Understanding + Vision-Language | ⏳ PENDIENTE |
| **FASE 4: Razonamiento + Auto-mejora** | Semana 4-5 | Planificación jerárquica + auto-mejora continua | ⏳ PENDIENTE |
| **FASE 5: Integración Completa H2O** | Semana 5-6 | Entidad aislada full-stack operativa 100% | ⏳ PENDIENTE |

---

## 📁 ESTRUCTURA DE ARCHIVOS DEL PROYECTO

```
/mnt/ssd_trabajo/hermes-agent/
├── src/                    # Código principal hermes-agent
├── skills/                 # Skills nativos (bridge, dispatcher, financial, etc.)
├── external_repos/         # Repos externos clonados (git submodules)
│   ├── memory/             # TencentDB, mem0, letta
│   ├── orchestration/      # OpenSwarm, ADK, VoltAgent
│   ├── skills/             # SkillNet, agentskills, agent-skills, google/skills
│   ├── perception/         # Unlimited-OCR, MinerU, tesseract, markitdown
│   ├── reasoning/          # fable-method, ADK, VoltAgent
│   └── tools/              # OpenSwarm, n8n, markitdown, tesseract
├── docs/clasificaciones/   # Documentación y clasificaciones
│   ├── ESTUDIO_REPOSITORIOS_PLAN_ACCION.md
│   ├── HERMES_AGENT_SUPERPOWERS_ARCHITECTURE.md
│   ├── TRADING_ENTITY_REPOS.json
│   ├── AGRO_ENTITY_REPOS.json
│   ├── H2O_PRODUCTION_REPOS.json
│   └── REPOS_PRIORIZADOS_HERMES_AGENT.json
├── external_repos/         # Submódulos git
└── config/                 # Configuración (.env, etc.)
```

---

## 🔐 VARIABLES DE ENTORNO REQUERIDAS (NUEVAS)

```bash
# Memoria
TENCENT_DB_MEMORY_API_KEY=xxx
MEM0_API_KEY=xxx
LETTA_API_KEY=xxx

# Orquestación
OPENAI_API_KEY=xxx  # Para ADK
ANTHROPIC_API_KEY=xxx  # Para VoltAgent

# Percepción
BAIDU_OCR_API_KEY=xxx
MINERU_API_KEY=xxx
QWEN_VL_API_KEY=xxx

# Razonamiento
OPENAI_API_KEY=xxx  # Para fable-method/ADK
ANTHROPIC_API_KEY=xxx  # Para VoltAgent/fable-method

# Skills
SKILLNET_API_KEY=xxx
```

---

## 🎯 PRÓXIMO PASO INMEDIATO

```bash
# Iniciar FASE 1: Memoria Unificada
cd /mnt/ssd_trabajo/hermes-agent/external_repos/memory

# Verificar estructura
ls -la TencentDB-Agent-Memory/ mem0/ letta/

# Leer documentación de cada uno
cat TencentDB-Agent-Memory/README.md
cat mem0/README.md
cat letta/README.md

# Crear script de integración inicial
cat > integrate_memory.py << 'PYEOF'
#!/usr/bin/env python3
"""
Integración inicial de memoria unificada en hermes-agent
"""
# TODO: Implementar conectores para TencentDB, mem0, letta
# TODO: Definir interfaz unificada MemoryInterface
# TODO: Implementar 4 tipos de memoria
PYEOF
```

---

**¡ARQUITECTURA DOCUMENTADA Y LISTA PARA IMPLEMENTACIÓN!** 💧
