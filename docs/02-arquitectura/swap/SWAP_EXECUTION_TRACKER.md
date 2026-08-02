# SWAP Migration — Execution Tracker
**Estación H2O · Maracaibo, Venezuela**  
**Inicio planificado:** Por definir (pendiente teléfonos empresa)  
**Duración:** 3 semanas  
**Responsable:** Prometeo + Líder + Choferes (YORDANIS + EVERT)  

---

## 📋 RESUMEN EJECUTIVO DEL PLAN

| Semana | Fase | Clientes | Botellas objetivo | Responsable |
|--------|------|----------|-------------------|-------------|
| **1-2** | B2B + Multifamiliares | 11 (6 B2B + 5 Multi) | 80-100 en rotación | YORDANIS + EVERT |
| **3** | Unifamiliares | 5 | 140-155/165 totales | YORDANIS + EVERT |

**Modelo:** 1:1 (entrega lleno → recoge vacío)  
**Vehículos:** 2 triciclos (30 llenos / 70 vacíos c/u)  
**Botellas loaner:** 165 (H2O-001 a H2O-165)  

---

## 🗓️ SEMANA 1-2: B2B + MULTIFAMILIARES (Clientes 1-11)

### Clientes a activar

| # | Cliente | Tipo | Frecuencia | Botellas/visita | Horas retorno | Zona | Vehículo asignado |
|---|---------|------|------------|-----------------|---------------|------|-------------------|
| 1 | Hotel del Lago | B2B | Daily | 8-12 | 24 | Norte | Triciclo 1 |
| 2 | Restaurante El Faro | B2B | Daily | 4-6 | 24 | Centro | Triciclo 2 |
| 3 | Clínica San Rafael | B2B | Daily | 6-10 | 24 | Norte | Triciclo 1 |
| 4 | Oficinas Corp. Polar | B2B | Weekly | 15-20 | 36 | Oeste | Triciclo 1 |
| 5 | Universidad del Zulia | B2B | Weekly | 10-15 | 36 | Norte | Triciclo 1 |
| 6 | Centro Comercial Sambil | B2B | Daily | 12-18 | 24 | Centro | Triciclo 2 |
| 7 | Condominio Los Naranjos | Multi | Weekly | 20-30 | 36 | Norte | Triciclo 1 |
| 8 | Residencias El Soler | Multi | Weekly | 15-25 | 36 | Sur-Este | Triciclo 2 |
| 9 | Edificio Las Palmas | Multi | Weekly | 12-18 | 36 | Norte | Triciclo 1 |
| 10 | Torres del Lago | Multi | Weekly | 15-20 | 36 | Norte | Triciclo 1 |
| 11 | Conjunto Res. Veritas | Multi | Weekly | 18-25 | 36 | Norte | Triciclo 1 |

### Capacidad semanal
```
Triciclo 1 (YORDANIS): 30 llenos/día × 6 días = 180 llenos/semana
Triciclo 2 (EVERT):     30 llenos/día × 6 días = 180 llenos/semana
TOTAL:                  360 llenos/semana
```

**Demanda estimada Semanas 1-2:** ~345-505 botellas/semana → Límite de capacidad, priorizar B2B daily

---

## 📅 CRONOGRAMA OPERATIVO SEMANA 1

| Día | Acción | Responsable | Checklist |
|-----|--------|-------------|-----------|
| **Lunes S1** | Asignar H2O-001 a H2O-050 → Triciclo 1; H2O-051 a H2O-100 → Triciclo 2 | Planta | ☐ Botellas etiquetadas ☐ Cargadas en vehículos |
| **Lunes S1** | Entrega inicial B2B daily (Hotel, Restaurante, Clínica, Sambil) | YORDANIS + EVERT | ☐ 4 clientes visitados ☐ Vacíos recogidos ☐ GPS registrado |
| **Martes S1** | Recogida vacíos B2B daily → Lavado | Planta | ☐ 100% vacíos recibidos ☐ Lavado completado |
| **Miércoles S1** | Entrega B2B weekly (Polar, UZ) + Multifamiliares (5) | Ambos | ☐ 7 clientes visitados ☐ Botellas asignadas en tracker |
| **Jueves S1** | Recogida vacíos semanales → Lavado | Planta | ☐ Vacíos recibidos ☐ Ciclo completo verificado |
| **Viernes S1** | **CORTE INVENTARIO**: Botellas en cliente vs planta vs tránsito | Prometeo/Planta | ☐ Conciliación tracker = física ☐ Alertas overdue revisadas |
| **Sábado S1** | Ajuste rutas, reasignar botellas disponibles | Dispatcher | ☐ Próxima semana optimizada |
| **Domingo S1** | **DESCANSO OPERATIVO** - solo alertas críticas | — | ☐ Monitoreo pasivo |

### Semana 2: Repetir ciclo + incorporar lecciones S1

---

## 📅 SEMANA 3: UNIFAMILIARES (Clientes 12-16)

### Clientes a activar

| # | Cliente | Tipo | Frecuencia | Botellas/visita | Horas retorno | Zona |
|---|---------|------|------------|-----------------|---------------|------|
| 12 | Familia Pérez | Unifam. | Biweekly | 2-3 | 48 | Norte |
| 13 | Familia González | Unifam. | Biweekly | 2-3 | 48 | Norte |
| 14 | Familia Rodríguez | Unifam. | Biweekly | 2-3 | 48 | Norte |
| 15 | Familia Hernández | Unifam. | Biweekly | 2-3 | 48 | Norte |
| 16 | Familia Martínez | Unifam. | Biweekly | 2-3 | 48 | Norte |

### Ajustes operativos Semana 3
- **Ruta dedicada unifamiliares:** Agrupar en ruta Norte → 1 viaje/semana por triciclo
- **Stock buffer:** Mantener 15-20 botellas disponibles en planta
- **Comunicación proactiva:** Recordatorio 24h antes de recogida (bot Telegram choferes)

---

## 📊 KPIs DE SEGUIMIENTO DIARIO

### Dashboard en Grafana (Panel: SWAP - Bottle Inventory Tracking)

| KPI | Target Semanas 1-2 | Target Semana 3 | Alerta si |
|-----|-------------------|-----------------|-----------|
| **Tasa retorno botellón** | ≥ 95% | ≥ 96% | < 90% |
| **Tiempo ciclo (lleno→vacío→lleno)** | ≤ 48h | ≤ 36h | > 72h |
| **Botellas perdidas/dañadas/semana** | ≤ 2 | ≤ 1 | > 5 |
| **Cobertura demanda B2B daily** | 100% | N/A | < 95% |
| **Stock disponible en planta (EOD)** | ≥ 20 | ≥ 15 | < 10 |
| **Total botellas en rotación** | 80-100 | 140-155/165 | — |
| **Alertas overdue resueltas < 24h** | 100% | 100% | < 100% |

---

## ✅ CHECKLIST GO/NO-GO SEMANA 3 → PRODUCCIÓN COMPLETA

- [ ] ≥ 150 botellas en rotación activa
- [ ] Tasa retorno ≥ 96% (promedio 3 semanas)
- [ ] 0 alertas críticas sin resolver > 24h
- [ ] Choferes operando autónomos (sin supervisión directa)
- [ ] Planta lavado procesando ≥ 50 botellas/día
- [ ] Dashboard Grafana verde (todos los paneles OK)
- [ ] Líder aprueba: **"SWAP OPERATIVO"**

---

## 📋 TRACKING DIARIO (TEMPLATE)

### Día: ___________ | Semana: __ | Chofer: ___________

| Métrica | Triciclo 1 (YORDANIS) | Triciclo 2 (EVERT) | Total |
|---------|----------------------|-------------------|-------|
| Botellas cargadas (AM) | | | |
| Entregas completadas | | | |
| Vacíos recogidos | | | |
| Botellas devueltas a planta | | | |
| Km recorridos | | | |
| Alertas overdue generadas | | | |
| Alertas overdue resueltas | | | |
| Botellas perdidas/dañadas | | | |

### Incidentes / Observaciones:
```
________________________________________________________________________
________________________________________________________________________
________________________________________________________________________
```

### Firmas:
- Chofer 1: ___________
- Chofer 2: ___________
- Supervisor: ___________

---

## 🔄 CONCILIACIÓN SEMANAL (VIERNES 15:00)

| Origen | Botellas contadas | Diferencia vs Tracker | Acción |
|--------|-------------------|----------------------|--------|
| Tracker (BD) | | — | |
| Física en planta | | | |
| Física en triciclos | | | |
| Reportadas en clientes | | | |
| **TOTAL** | | | |

**Responsable conciliación:** ___________  
**Firma:** ___________  
**Fecha:** ___________

---

## 🚨 PLAN DE CONTINGENCIA

| Riesgo | Trigger | Acción inmediata | Responsable |
|--------|---------|------------------|-------------|
| Rotura masiva (>10/semana) | Alerta `BottleInventoryLow` | Activar stock seguridad 20 + proveedor backup 48h | Planta |
| Chofer enfermo / triciclo averiado | Chofer no check-in 8am | Cross-training activado + triciclo reserva | Dispatcher |
| Cliente B2B no devuelve vacíos | Alerta `BottleOverdueHigh` (overdue > 5) | Escalamiento automático 6h/24h/48h → humano | Prometeo/Líder |
| Demanda > capacidad (pico calor) | Cobertura B2B < 95% | Priorizar B2B daily, diferir unifamiliares 1 semana | Líder |
| Error tracking (duplicados/perdidos) | Conciliación viernes > 5 diff | Auditoría física inmediata + freeze asignaciones | Prometeo/Planta |

---

## 📞 COMUNICACIÓN Y ESCALAMIENTO

| Canal | Uso | Destinatarios |
|-------|-----|---------------|
| **Telegram Bot** `@DespachoH2O_bot` | Órdenes diarias, check-ins, alertas | Choferes (YORDANIS, EVERT) |
| **Telegram Líder** | KPIs, alertas críticas, decisiones Go/No-Go | Líder (chat_id: 1663148211) |
| **Grafana Alertas** | Alertas automáticas (P95, overdue, inventory) | Prometeo + Líder |
| **Llamada directa** | Emergencias operativas (chofer accidentado, triciclo averiado) | Líder + Planta |

---

## 📁 ARCHIVOS RELACIONADOS

| Archivo | Descripción |
|---------|-------------|
| `skills/dispatch/seed_data.py` | Pobla BD: zonas, vehículos, 16 clientes, 165 botellas |
| `skills/dispatch/bottle_tracker.py` | Tracker estados: available → in_transit_full → with_client → in_transit_empty → maintenance → available |
| `skills/dispatch/telegram_bot.py` | Bot choferes: asignar, entregar, recoger, lavar, alertas |
| `skills/dispatch/route_engine.py` | VRP con OR-Tools (haversine) |
| `docs/03-sesiones/PLAN_MIGRACION_SWAP_2026-07-30.md` | Plan maestro original |
| `monitoring/grafana/dashboards/swap_inventory.json` | Dashboard SWAP en Grafana |

---

## 📝 BITÁCORA DE EJECUCIÓN

| Fecha | Semana | Hito completado | Observaciones | Firmas |
|-------|--------|-----------------|---------------|--------|
| | | | | |
| | | | | |
| | | | | |
| | | | | |

---

**Estado actual:** ⏳ **PENDIENTE INICIO** — Esperando teléfonos empresa para registro choferes  
**Próxima acción:** Configurar `telegram_chat_id` reales en `vehicles` table tras registro `/start`  
**Firma:** 💧 Prometeo  
**Fecha:** 1 Agosto 2026
