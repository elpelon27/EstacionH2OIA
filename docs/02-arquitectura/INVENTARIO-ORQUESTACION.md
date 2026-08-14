# 🗂️ INVENTARIO ÚNICO DE ORQUESTACIÓN — Estación H2O (fuente de verdad)

**Fecha**: 2026-08-13 · **Autor**: Prometeo · **Actualizado en**: Fase C (hallazgo H1/H10)
**Propósito**: Único registro autoritativo de TODO el trabajo programado y las rutas
de datos. Si algo no está aquí, no está programado.

---

## 1. FUENTES DE TRABAJO PROGRAMADO

| Mecanismo | Almacena | Estado |
|-----------|----------|--------|
| **crontab** (usuario skynet) | 7 jobs Python + scripts | ✅ fuente para jobs diarios/30min |
| **systemd timers** | 7 timers + servicios | ✅ fuente para tareas odoo/backup/r4 |
| **Cron Hermes** (~/.hermes/cron) | — | ⚠️ VACÍO (no usar; documentado como legado) |

> Regla (C1): **Todo trabajo programado va en crontab o systemd timer — una sola fuente de
> verdad = este documento.** El directorio cron de Hermes queda obsoleto (jobs de skills
> corren por crontab directamente).

---

## 2. CRONTAB (7 jobs)

| Horario | Job | Script | Log |
|---------|-----|--------|-----|
| 03:00 diario | Backup BD | scripts/backup_daily.sh | /mnt/ssd_trabajo/backups/backup_cron.log |
| 04:00 dom | Limpieza logs >30d | find | — |
| 07:00 diario | Reporte analytics | skills/run_analytics_7am.py | logs/cron_analytics_7am.log |
| 07:45 diario | VRP route planner | skills/run_route_planner.py | logs/cron_route_planner.log |
| 08:00 diario | Check-in choferes | skills/run_dispatcher_checkin.py | logs/cron_dispatcher_checkin.log |
| 18:30 diario | Reporte Financial Shield | skills/run_fs_reporte.py | logs/cron_fs_reporte.log |
| */30 diario | Recordatorios pagos | skills/run_fs_recordatorios.py | logs/cron_fs_recordatorios.log |

---

## 3. SYSTEMD TIMERS (7)

| Timer | Sincronización | Servicio | NextElapse (2026-08-13) |
|-------|---------------|----------|--------------------------|
| backup-daily | 03:00 (aprox) | backup-daily.service | 08-14 03:03 |
| odoo-ventas-diarias | diario ~23:00 | odoo-ventas-diarias | 08-13 23:00 |
| odoo-inventario-hielo | diario ~08:00 | odoo-inventario-hielo | 08-14 08:09 |
| odoo-inventario-insumos | semanal | odoo-inventario-insumos | 08-17 08:03 |
| odoo-nomina-viernes | viernes | odoo-nomina-viernes | 08-14 17:09 |
| odoo-cierre-semanal | semanal | odoo-cierre-semanal | 08-14 18:10 |
| r4-tasa-bcv | 2x diario (9am/3pm) | r4-tasa-bcv | 08-14 09:01 |

---

## 4. SERVICIOS DE PRODUCCIÓN (systemd, 5 activos)

| Servicio | Rol | Puerto | Estado |
|----------|-----|--------|--------|
| valentina-bridge | FastAPI WhatsApp → Dify/FS | :8000 | ✅ |
| dispatcher-bot | Telegram choferes | — | ✅ |
| telegram-bot | Kill switch + alerts Líder | — | ✅ |
| prometeo-telegram | Bot Líder ↔ Agente | — | ✅ |
| cloudflared | Tunnel valentina.estacionh2o.com | — | ✅ |

---

## 5. RUTAS DE DATOS (verificadas)

```
WhatsApp → Meta Cloud → Cloudflare Tunnel → valentina-bridge (:8000)
    bridge → Dify (Valentina LLM, guardrail) → WhatsApp
    bridge → fs_pedidos (SQLite conversations.db)
    bridge → dispatch_queue (cola) → dispatcher-bot/consumer → choferes Telegram
    Financial Shield ↔ fs_* (conversations.db)
    FS → Odoo (timers x5, XML-RPC)
    R4 Banco → /webhook/r4/* (montado; creds parciales)
    Monitoring: /metrics → Prometheus (hermes job :8000) + node + Grafana
```

---

## 6. OBSERVABILIDAD (C4)

| Componente | Estado |
|------------|--------|
| Prometheus :9090 (Docker) | ✅ scrapeando 3 jobs (hermes/nodo/prometheus) |
| Bridge /metrics | ✅ valentina_messages_total, response_time_histogram |
| Grafana :3001 (Docker) | ✅ corriendo |
| **Reglas de alerta Prometheus** | ❌ **PENDIENTE** (no hay rule_files → sin alertas) |
| GPU/VRAM node-exporter textfile | ❌ PENDIENTE (P2-5) |

---

## 7. DIAGRAMA DE ORQUESTACIÓN (D2 - actualizado 2026-08-13)

```
                    ┌──────────────────────────────────────────────┐
                    │              CLOUD / INFRA                    │
                    │  Meta Cloud API (WhatsApp)  ◄──►  R4 Banco    │
                    └───────────────┬──────────────┬────────────────┘
                                    │              │ /webhook/r4/*
                       Cloudflare   │ HTTPS        ▼
                       Tunnel ◄──────┘   ┌──────────────────┐
                                        │ valentina-bridge │ :8000
                                        │  · HMAC/rate/dedup│
                                        │  · guardrail(lm)  │
                                        └───┬──────────┬────┘
                     conversations.db(<)────┘          │ /metrics
              fs_* + orders + dispatch_queue          Prometheus :9090
                     │  │  │                          node_exporter
        ┌────────────┘  │  └────► daily/30min crontab
        ▼               ▼
  Financial Shield   Dispatcher (Telegram choferes)
  (fs_pagos fixed)   consumer ← dispatch_queue
        │
        ▼
  Odoo (timers x5 XML-RPC) + Google Sheets
```

---

*Regla de mantenimiento: actualizar este documento SIEMPRE que se añada/modifique un cron,
timer o ruta. Es la fuente de verdad de orquestación.*
