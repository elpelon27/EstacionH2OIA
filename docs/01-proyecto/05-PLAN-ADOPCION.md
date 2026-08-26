# Plan de Adopción — Estación H2O / Prometeo

**Fecha**: 2026-08-26 (Día 34)
**Autor**: Prometeo (GLM 5.2 vía OpenRouter)
**Aprobador**: Luis Martinez (@elpelon27) — Líder de Estación H2O
**Objetivo**: Adopción completa del sistema en 2 semanas

---

## Contexto Actual (verificado 2026-08-26)

| Métrica | Actual | Target post-adopción |
|---------|--------|---------------------|
| Clientes en dispatch.db | 3 | 16 (todos los activos) |
| Deliveries en dispatch.db | 4 | 50+ (primera semana) |
| Choferes en Telegram bot | 0 confirmados | 2/2 (YORDANIS + EVERT) |
| Pedidos por Valentina | ~2-3/día | 10-15/día |
| Reportes Telegram al Líder | Activos (cron) | Revisados diariamente |

---

## Semana 1: Onboarding Interno + Infraestructura

### Día 1 (Lunes): Onboarding Choferes (DT-01)

**Objetivo**: YORDANIS y EVERT operando @DespachoH2O_bot de Telegram

**Pasos**:
1. **Líder reúne choferes** (10 min): explica que las rutas del día llegarán por Telegram
2. **Cada chofer abre Telegram** y busca @DespachoH2O_bot
3. **Envía /start** al bot
4. **Bot responde**: "Bienvenido YORDANIS. Tu zona asignada es [zona]. Recibirás tus rutas del día aquí a las 7:45am."
5. **Chofer confirma** recibiendo un mensaje de prueba con botones ✅/❌
6. **Líder verifica** en dispatch.db que el chofer aparece con session activa

**Verificación**:
```bash
sqlite3 data/dispatch.db "SELECT * FROM dispatch_sessions ORDER BY started_at DESC LIMIT 5"
```

**Criterio de éxito**: 2/2 choferes han enviado /start y recibido respuesta con botones funcionales

### Día 2-3 (Martes-Miércoles): Capacitación Líder

**Objetivo**: Luis opera el dashboard Odoo + reportes Telegram

**Sesión 1 (2h)**: Dashboard Odoo
1. **Acceder**: https://estacion-h2o.odoo.com/web/login (Odoo Docker Up)
2. **Revisar módulos**: Sales, Stock, Account, HR, Payroll
3. **Cargar productos**: Botellón 20L, Hielo 5kg, Insumos (tapas, etiquetas)
4. **Configurar precios**: Precio EUR + tasa BCV actualizada
5. **Crear 3 clientes piloto**: los que ya están en dispatch.db (migrar a Odoo partners)
6. **Revisar inventario**: Botellones disponibles, en tránsito, con cliente (SWAP)

**Sesión 2 (1h)**: Reportes Telegram (Prometeo)
1. **Verificar bot @Skynet_27_bot** responde
2. **Revisar reporte 7am**: ventas del día anterior
3. **Revisar recordatorios 30min**: pagos pendientes
4. **Revisar reporte 18:30**: cierre financiero del día
5. **Configurar alertas**: qué quiere recibir y cuándo

**Verificación**:
```bash
# Reporte 7am llegó
ls -la logs/cron_analytics_7am.log

# Bot responde
curl -s https://valentina.estacionh2o.com/health | jq .status
```

**Criterio de éxito**: Luis accede a Odoo, ve 3 productos cargados, recibe y entiende los 3 reportes Telegram

### Día 4-5 (Jueves-Viernes): Migración Clientes Piloto

**Objetivo**: Los 3 clientes actuales en dispatch.db migrados a flujo Valentina completo

**Pasos**:
1. **Líder contacta a los 3 clientes** por WhatsApp personal
2. **Mensaje**: "A partir de hoy, puedes pedir tus botellones directamente a nuestro nuevo número de WhatsApp [Valentina]. Solo escribe 'necesito botellones' y ella te guía."
3. **Cliente escribe a Valentina**
4. **Valentina procesa**: FSM awaiting_qty → awaiting_address → awaiting_payment
5. **Pedido completo**: inserta en orders + dispatch_queue + sync client
6. **Route planner 7:45am** asigna ruta
7. **Chofer entrega** y marca ✅ en Telegram

**Verificación**:
```bash
# Pedidos nuevos por Valentina
sqlite3 data/conversations.db "SELECT COUNT(*) FROM orders WHERE date >= date('now', '-2 days')"

# Clients sincronizados
sqlite3 data/dispatch.db "SELECT COUNT(*) FROM clients"
```

**Criterio de éxito**: 3/3 clientes piloto han hecho al menos 1 pedido por Valentina

---

## Semana 2: Adopción Completa

### Día 6-7 (Lunes-Martes): Migración Clientes Restantes (16 total)

**Objetivo**: Migrar los 13 clientes restantes de WhatsApp manual a Valentina

**Estrategia**: Migración gradual por lotes

**Lote 1 (Lunes mañana)**: 5 clientes
- Líder envía mensaje personal a 5 clientes: "Prueba nuestro nuevo sistema de pedidos automáticos"
- Monitorear respuesta: ¿cuántos escriben a Valentina?
- Ajustar mensaje si hay confusión

**Lote 2 (Lunes tarde)**: 5 clientes
- Mismo proceso, ahora con feedback del Lote 1

**Lote 3 (Martes)**: 3 clientes restantes
- Clientes más reacios o menos frecuentes
- Ofrecer incentivo: "Primer pedido por Valentina = 1 botellón gratis" (opcional, decisión del Líder)

**Verificación**:
```bash
# Total clientes en dispatch.db
sqlite3 data/dispatch.db "SELECT COUNT(*) FROM clients"
# Target: 16

# Pedidos por día
sqlite3 data/conversations.db "SELECT date(created_at), COUNT(*) FROM orders GROUP BY date(created_at) ORDER BY date(created_at) DESC LIMIT 7"
```

**Criterio de éxito**: 16 clientes registrados en dispatch.db, al menos 10 han hecho 1+ pedido por Valentina

### Día 8-9 (Miércoles-Jueves): Cambio de Modelo (Recarga → Intercambio 70/30)

**Objetivo**: Clientes entienden y operan bajo modelo SWAP 70/30

**Contexto**: En lugar de "recarga en sitio" (cliente paga por llenar su botellón), el modelo es "intercambio" (cliente recibe botellón lleno y devuelve vacío, paga solo el intercambio)

**Comunicación a clientes**:
- Valentina explica automáticamente en cada pedido: "El precio es por intercambio. Necesitas devolver [N] botellones vacíos cuando te entregamos los llenos."
- Si cliente no tiene vacíos para devolver, precio ajustado (depósito)
- SWAP_EXECUTION_TRACKER.md existe en docs/02-arquitectura/swap/

**Capacitación choferes**:
- Chofer debe contar vacíos recibidos al entregar
- Registrar en Telegram bot: "Entregados: 3, Recibidos: 3" (o discrepancia)
- Si hay discrepancia, reportar a Líder

**Verificación**:
```bash
# Bottle movements registrados
sqlite3 data/dispatch.db "SELECT COUNT(*) FROM bottle_movements"
# Target: coincidir con deliveries

# Alertas de botellones
sqlite3 data/dispatch.db "SELECT COUNT(*) FROM bottle_alerts"
# Target: mínimas (solo discrepancias reales)
```

**Criterio de éxito**: 80%+ de entregas con SWAP registrado (vacíos recibidos = entregados)

### Día 10 (Viernes): Revisión + Ajustes

**Objetivo**: Evaluación de adopción, ajustes necesarios

**Checklist de revisión**:

| # | Item | Target | Verificación |
|---|------|--------|--------------|
| 1 | Choferes activos en Telegram | 2/2 | dispatch_sessions |
| 2 | Clientes registrados | 16 | dispatch.db clients |
| 3 | Pedidos por Valentina (semana) | 30+ | orders WHERE date >= 7 días atrás |
| 4 | Deliveries completadas | 20+ | deliveries WHERE status = 'delivered' |
| 5 | SWAP registrado | 80%+ | bottle_movements vs deliveries |
| 6 | Reportes Telegram revisados | 5/5 días | logs/cron_*.log + feedback Líder |
| 7 | Odoo dashboard accesible | Sí | curl https://estacion-h2o.odoo.com/web/login |
| 8 | Productos cargados Odoo | 3+ | Odoo Inventory > Products |
| 9 | Clientes en Odoo | 3+ (piloto) | Odoo Contacts |
| 10 | Valentina uptime | > 95% | systemctl + logs |

**Acciones correctivas si hay gaps**:
- Si clientes no adoptan Valentina: llamar personalmente, ofrecer incentivo
- Si choferes no marcan entregas: sesión de 15 min de refuerzo
- Si SWAP no se registra: simplificar botones en Telegram
- Si Odoo no accesible: verificar Docker, reiniciar contenedores

---

## Timeline Resumen

```
SEMANA 1
├── Día 1 (Lun):  DT-01 Onboarding choferes (/start al bot)
├── Día 2 (Mar):  Capacitación Líder (Odoo dashboard)
├── Día 3 (Mié):  Capacitación Líder (reportes Telegram)
├── Día 4 (Jue):  Migración 3 clientes piloto
├── Día 5 (Vie):  Migración piloto — verificación

SEMANA 2
├── Día 6 (Lun):  Migración Lotes 1+2 (10 clientes)
├── Día 7 (Mar):  Migración Lote 3 (6 clientes restantes)
├── Día 8 (Mié):  Cambio modelo SWAP 70/30 (comunicación)
├── Día 9 (Jue):  SWAP — verificación choferes
├── Día 10(Vie):  Revisión + ajustes
```

---

## Riesgos de Adopción y Mitigación

| Riesgo | Probabilidad | Mitigación |
|--------|-------------|------------|
| Cliente no quiere usar WhatsApp automatizado | MEDIA | Valentina es transparente, experiencia igual o mejor que manual |
| Chofer prefiere papel vs Telegram | MEDIA | Onboarding simple, bot intuitivo con botones (no comandos) |
| Modelo 70/30 confunde al cliente | MEDIA | Valentina explica automáticamente, Líder refuerza |
| Cliente no tiene vacíos para SWAP | BAJA | Depósito temporal, ajustar precio |
| Odoo muy complejo para Líder | BAJA | Solo dashboard inicial, no requiere configuración técnica |
| Cortes eléctricos interrumpen adopción | ALTA | Bridge reinicia automático (Restart=always), FSM persistente sobrevive |

---

## Dependencias

- **Odoo Docker**: Debe estar accesible (odoo-web + odoo-db Up — verificado 2026-08-26)
- **Valentina bridge**: Activo y healthy (systemctl active — verificado)
- **Dispatcher bot**: Activo (systemctl active — verificado)
- **Cron jobs**: 6 activos (verificado crontab)
- **Cloudflare Tunnel**: valentina.estacionh2o.com operativo (verificado)
- **Telegram bots**: @Skynet_27_bot (Líder) + @DespachoH2O_bot (choferes) activos

---

**Firma**: 💧