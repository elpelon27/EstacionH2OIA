# R4 — Plan: Prueba con Pedido Real (mañana, horario laboral)

**Fecha:** 2026-09-11 (preparado after-hours, SIN EJECUTAR)
**Directiva:** 💧 Líder — primera tarea de mañana en horario de atención al público.
**Objetivo:** validar el único tramo del pipeline R4 no ejercitado: **INSERT en fs_pagos**
(casación teléfono+monto → verificación → WhatsApp "✅ Pago confirmado" → Odoo best-effort).

---

## 0. Contexto técnico verificado HOY (primera mano, live)

- Tabla de pedidos pendientes: **`fs_pedidos`** en `data/conversations.db`
  (SQLite). Columnas relevantes: `pedido_id`, `cliente_telefono`,
  `monto_total_eur`, `monto_total_ves`, `tasa_eur_ves`, `estado_pago`
  ('pendiente'|'verificando'|'parcial'|'vencido' son casables).
- Casación: `buscar_pedidos_por_telefono_monto()` (`src/financial/database.py:567`)
  compara **monto en EUR** con tolerancia **±1%** (mín 0.01), y teléfono
  normalizado a 10 dígitos (formatos +58/0X aceptados, LIKE).
- El banco R4 envía Monto en **VES**; el webhook convierte VES→EUR con
  `get_eur_ves_rate()` para casar contra `monto_total_eur`. El pedido de
  prueba debe llevar `monto_total_eur` y `tasa_eur_ves` coherentes con el
  monto VES que el Líder va a pagar.
- Scoring de desempate: `seleccionar_mejor_match()` (teléfono exacto >
  monto exacto > más reciente). Un solo pedido pendiente para ese
  teléfono elimina ambigüedad.
- INSERT: `verificar_pago_manual(fs_pedido_id, monto_eur, metodo_pago='pagomovil', referencia, verificado_por='banco_r4')`
  (`src/financial/verificacion.py`) → INSERT `fs_pagos` + UPDATE `fs_pedidos.estado_pago`.
- Schema de `fs_pagos` verificado HOY en la DB real — correcto (ver §4).

## 1. Crear pedido pendiente (SQL, mañana)

⚠️ NO EJECUTAR HOY. Ajustar `<MONTO_EUR>`, `<TASA>` y confirmar con el
Líder el teléfono que usará para pagar (el de la prueba del 11/09 fue
04122560720):

```sql
INSERT INTO fs_pedidos (
  pedido_id, cliente_telefono, cliente_nombre,
  monto_total_eur, monto_total_ves, tasa_eur_ves,
  botellones_cantidad, estado_pago, estado_entrega,
  creado_at, actualizado_at
) VALUES (
  900001,                    -- pedido_id único de prueba
  '04122560720',             -- teléfono que pagará el Líder
  'LIDER PRUEBA R4',
  <MONTO_EUR>,               -- p.ej. 1.00 EUR si pagará ~60 VES
  <MONTO_VES>,               -- monto EXACTO que el Líder va a pagar
  <TASA>,                    -- tasa eur/ves del día (BCV)
  0, 'pendiente', 'sin_entregar',
  datetime('now'), datetime('now')
);
```

Nota: `monto_total_eur` debe caer dentro de ±1% del equivalente EUR del
pago VES según la tasa que use el webhook (`get_eur_ves_rate()`).
Monto EUR redondo pequeño (1.00 EUR) minimiza el riesgo de descuadre
por variación de tasa.

## 2. Hacer el pago que case

El Líder paga por **pagomovil desde su teléfono del banco R4** el
`monto_total_ves` exacto del pedido. Flujo que se disparará solo:

1. `R4consulta` (banco → bridge): busca pedidos para IdCliente →
   status=True (pedido pendiente encontrado).
2. `R4notifica` (banco → bridge, CodigoRed=00): busca
   `telefono_emisor + monto` → match único → `verificar_pago_manual()`.

## 3. Logs a monitorear (en vivo, durante el pago)

```bash
# journalctl del bridge, seguir en vivo:
journalctl -u valentina-bridge -f --since "5 min ago"

# Patrones clave a esperar:
#   R4consulta: cliente <Id> ACEPTADO, 1 pedido(s) pendiente(s)
#   R4notifica recibido: Referencia=..., Monto=..., TelefonoEmisor=...
#   R4notifica: match pedido_id=... monto_ves=... monto_eur=... (tasa=...)
#   R4notifica: pago VERIFICADO pedido_fs=... ref=... estado=pagado
# Si algo falla:
#   R4notifica: no hay pedido pendiente para emisor=... → casación falló
#   AMBIGUOUS_MATCH → hay >1 pedido con mismo tel/monto
```

## 4. Validar INSERT en fs_pagos (después del pago)

```sql
-- El INSERT esperado (debe existir una fila nueva):
SELECT id, fs_pedido_id, cliente_telefono, monto_eur, monto_ves,
       metodo_pago, referencia, verificacion_metodo,
       verificado, verificado_por, creado_at
FROM fs_pagos ORDER BY id DESC LIMIT 5;

-- El pedido debe quedar pagado:
SELECT id, pedido_id, estado_pago, monto_pagado_eur
FROM fs_pedidos WHERE pedido_id = 900001;

-- Trazabilidad del Financial Shield:
SELECT * FROM fs_audit_log ORDER BY id DESC LIMIT 10;
```

Criterios de ÉXITO (checklist de mañana):
- [ ] fila nueva en `fs_pagos` con `fs_pedido_id` = id del pedido 900001,
      `verificado=1`, `verificado_por='banco_r4'`, `metodo_pago='pagomovil'`
- [ ] `fs_pedidos.estado_pago = 'pagado'` (o el estado que fije la verificación)
- [ ] banco recibió `abono=True` (200 OK en journalctl)
- [ ] WhatsApp "✅ Pago confirmado" al teléfono del Líder
- [ ] registro en `fs_audit_log` (INSERT fs_pagos)
- [ ] Odoo best-effort: loguear resultado (éxito o fallo no bloqueante)

## 5. Limpieza post-prueba

```sql
-- Solo si el Líder lo ordena (dejar rastro auditado):
-- DELETE FROM fs_pedidos WHERE pedido_id = 900001;
-- (recomendado: NO borrar, marcar como prueba en fs_audit_log)
```

## Reglas

- NO ejecutar nada de esto hoy (after-hours). Mañana, horario laboral,
  con el Líder presente.
- Verificar SIEMPRE con datos en vivo (journalctl + SQLite directo),
  no con informes pasados.
- wamid de referencia del pipeline Meta: ver docs/META_PRODUCCION_FINAL.md
