# SWAP Migration Plan — 165 Botellones Loaner
**Estación H2O · Maracaibo, Venezuela**  
**Fecha:** 30 Julio 2026  
**Autor:** Prometeo  

---

## Resumen Ejecutivo

| Métrica | Valor |
|---------|-------|
| **Total botellones loaner** | 165 (H2O-001 a H2O-165) |
| **Vehículos** | 2 triciclos (30 llenos / 70 vacíos c/u) |
| **Operadores** | YORDANIS (Triciclo 1), EVERT (Triciclo 2) |
| **Clientes piloto** | 16 (6 B2B + 5 multifamiliares + 5 unifamiliares) |
| **Duración migración** | **3 semanas** |
| **Modelo intercambio** | 1:1 (entrega lleno → recoge vacío) |

---

## Semanas 1-2: FASE B2B + Multifamiliares (Clientes 1-11)

### Objetivo
- Activar 11 clientes de alto volumen (B2B daily + multifamiliares weekly)
- Validar flujo completo: asignación → entrega → recogida → lavado → reasignación
- Alcanzar ~80-100 botellones en rotación activa

### Clientes Semana 1-2

| # | Cliente | Tipo | Frecuencia | Botellas/visita | Horas retorno | Zona |
|---|---------|------|------------|-----------------|---------------|------|
| 1 | Hotel del Lago | B2B | Daily | 8-12 | 24 | Norte |
| 2 | Restaurante El Faro | B2B | Daily | 4-6 | 24 | Centro |
| 3 | Clínica San Rafael | B2B | Daily | 6-10 | 24 | Norte |
| 4 | Oficinas Corp. Polar | B2B | Weekly | 15-20 | 36 | Oeste |
| 5 | Universidad del Zulia | B2B | Weekly | 10-15 | 36 | Norte |
| 6 | Centro Comercial Sambil | B2B | Daily | 12-18 | 24 | Centro |
| 7 | Condominio Los Naranjos | Multifam. | Weekly | 20-30 | 36 | Norte |
| 8 | Residencias El Soler | Multifam. | Weekly | 15-25 | 36 | Sur-Este |
| 9 | Edificio Las Palmas | Multifam. | Weekly | 12-18 | 36 | Norte |
| 10 | Torres del Lago | Multifam. | Weekly | 15-20 | 36 | Norte |
| 11 | Conjunto Res. Veritas | Multifam. | Weekly | 18-25 | 36 | Norte |

### Capacidad semanal estimada

```
Triciclo 1 (YORDANIS): 30 llenos/día × 6 días = 180 llenos/semana
Triciclo 2 (EVERT):     30 llenos/día × 6 días = 180 llenos/semana
TOTAL:                  360 llenos/semana
```

**Demanda semanal estimada (Semanas 1-2):**
- B2B Daily (4 clientes): ~40-60 botellas/día × 6 = 240-360/semana
- B2B Weekly (2 clientes): ~25-35 botellas/semana
- Multifamiliares (5 clientes): ~80-110 botellas/semana
- **Total: ~345-505 botellas/semana** → Límite de capacidad, priorizar B2B daily

### Acciones Operativas Semana 1-2

| Día | Acción | Responsable |
|-----|--------|-------------|
| **Lunes S1** | Asignar H2O-001 a H2O-050 a Triciclo 1; H2O-051 a H2O-100 a Triciclo 2 | Planta |
| **Lunes S1** | Entrega inicial B2B daily (Hotel, Restaurante, Clínica, Sambil) | YORDANIS + EVERT |
| **Martes S1** | Recogida vacíos B2B daily → lavado | Planta |
| **Miércoles S1** | Entrega B2B weekly (Polar, UZ) + Multifamiliares | Ambos |
| **Jueves S1** | Recogida vacíos semanales → lavado | Planta |
| **Viernes S1** | **Corte inventario**: botellas en cliente vs. en planta vs. en tránsito | Prometeo/Planta |
| **Sábado S1** | Ajuste rutas, reasignar botellas disponibles | Dispatcher |
| **Domingo S1** | **Descanso operativo** - solo alertas críticas | — |
| **Lunes S2** | Repetir ciclo, incorporar lecciones S1 | Todos |
| **Viernes S2** | **Revisión KPIs**: % retorno, tiempo ciclo, botellas perdidas | Prometeo/Líder |

### KPIs Críticos Semanas 1-2

| KPI | Target | Alerta si |
|-----|--------|-----------|
| **Tasa retorno botellón** | ≥ 95% | < 90% |
| **Tiempo ciclo (lleno→vacío→lleno)** | ≤ 48h | > 72h |
| **Botellas perdidas/dañadas/semana** | ≤ 2 | > 5 |
| **Cobertura demanda B2B daily** | 100% | < 95% |
| **Stock disponible en planta (EOD)** | ≥ 20 | < 10 |

---

## Semana 3: FASE Unifamiliares (Clientes 12-16)

### Objetivo
- Incorporar 5 unifamiliares (biweekly, 48h retorno)
- Completar rotación de 165 botellones
- Establecer ritmo estable post-migración

### Clientes Semana 3

| # | Cliente | Tipo | Frecuencia | Botellas/visita | Horas retorno | Zona |
|---|---------|------|------------|-----------------|---------------|------|
| 12 | Familia Pérez | Unifam. | Biweekly | 2-3 | 48 | Norte |
| 13 | Familia González | Unifam. | Biweekly | 2-3 | 48 | Norte |
| 14 | Familia Rodríguez | Unifam. | Biweekly | 2-3 | 48 | Norte |
| 15 | Familia Hernández | Unifam. | Biweekly | 2-3 | 48 | Norte |
| 16 | Familia Martínez | Unifam. | Biweekly | 2-3 | 48 | Norte |

### Ajustes Operativos Semana 3

- **Ruta dedicada unifamiliares**: Agrupar en ruta Norte (misma zona) → 1 viaje/semana por triciclo
- **Stock buffer**: Mantener 15-20 botellas disponibles en planta para imprevistos
- **Comunicación proactiva**: Recordatorio 24h antes de recogida (bot Telegram choferes)

### KPIs Semana 3

| KPI | Target |
|-----|--------|
| **Total botellas en rotación** | 140-155/165 |
| **Tasa retorno global** | ≥ 96% |
| **Tiempo ciclo promedio** | ≤ 36h |
| **Alertas overdue resueltas < 24h** | 100% |

---

## Plan de Contingencia

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| **Rotura masiva botellas (>10/semana)** | Media | Alto | Stock seguridad 20 botellas; proveedor backup 48h |
| **Chofer enfermo / triciclo averiado** | Media | Alto | Cross-training choferes; triciclo reserva |
| **Cliente B2B no devuelve vacíos** | Alta | Medio | Alertas automáticas 6h/24h/48h; escalamiento a humano |
| **Demanda > capacidad (pico calor)** | Alta | Medio | Priorizar B2B daily; diferir unifamiliares 1 semana |
| **Error tracking botellas (duplicados/perdidos)** | Baja | Alto | Auditoría física semanal viernes; conciliación DB |

---

## Comunicación y Reportes

| Reporte | Frecuencia | Destinatario | Canal |
|---------|------------|--------------|-------|
| **Dashboard tiempo real** | Continuo | Líder + Planta | Grafana (Prometheus metrics) |
| **Resumen diario EOD** | Diario 18:30 | Líder | Telegram (bot `@DespachoH2O_bot`) |
| **KPIs semanales** | Viernes 17:00 | Líder + Prometeo | Telegram + Obsidian Vault |
| **Auditoría física** | Viernes 15:00 | Planta | Checklist papel + foto DB |
| **Alerta crítica** | Inmediata | Líder + Chofer afectado | Telegram (prioridad alta) |

---

## Checklist Go/No-Go Semana 3 → Producción Completa

- [ ] ≥ 150 botellas en rotación activa
- [ ] Tasa retorno ≥ 96% (promedio 3 semanas)
- [ ] 0 alertas críticas sin resolver > 24h
- [ ] Choferes operando autónomos (sin supervisión directa)
- [ ] Planta lavado procesando ≥ 50 botellas/día
- [ ] Dashboard Grafana verde (todos los paneles OK)
- [ ] Líder aprueba: **"SWAP OPERATIVO"**

---

## Archivos Relacionados

| Archivo | Descripción |
|---------|-------------|
| `skills/dispatch/seed_data.py` | Pobla BD con zonas, vehículos, 16 clientes, 165 botellas |
| `skills/dispatch/bottle_tracker.py` | Tracker estados: available → in_transit_full → with_client → in_transit_empty → maintenance → available |
| `skills/dispatch/telegram_bot.py` | Bot choferes: asignar, entregar, recoger, lavar, alertas |
| `skills/dispatch/route_engine.py` | VRP con OR-Tools (haversine) |
| `docs/03-sesiones/PLAN_MIGRACION_SWAP_2026-07-30.md` | Este documento |

---

**Firma:** 💧 Prometeo — 30 Julio 2026