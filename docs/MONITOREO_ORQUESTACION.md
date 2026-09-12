# MONITOREO ORQUESTACION — Prueba real end-to-end

Fecha: 2026-09-12 · Autor: Prometeo 💧 (orquestador) · Branch: `feat/odoo-r4-integration`

Flujo monitoreado: Cliente WhatsApp → Meta webhook → Valentina (Dify) → pago Banco R4
→ webhook `/webhook/r4` → `buscar_pedidos_por_telefono_monto()` → INSERT `fs_pagos`
→ UPDATE `fs_pedidos` → WhatsApp "✅ Pago confirmado" → Odoo best-effort → Dispatcher.

## 1. Lanzar

```bash
bash /home/skynet/monitor_orquestacion.sh
tmux attach -t monitor      # Ctrl-b d para despegar
# Al terminar:
tmux kill-session -t monitor
```

⚠️ tmux NO está instalado en el servidor (sudo requiere contraseña del Líder).
Si el Líder instala tmux (`sudo apt-get install -y tmux`) el script funciona tal cual.
Sin tmux, el script imprime el fallback: 5 backgrounds con logs en /tmp/mon_t*.log,
seguibles con `tail -f /tmp/mon_t*.log`, y se matan con `pkill -f journalctl.*grep`.

5 terminales (panes tmux, numerados):

| Pane | Terminal | Monitorea |
|------|----------|-----------|
| 0 | T5 Servicios | `watch` estado systemd + COUNT fs_pagos en vivo |
| 1 | T1 Meta | `journalctl -u valentina-bridge` filtrado `meta\|whatsapp\|dify\|webhook/meta` |
| 2 | T4 Errores | mismo journal filtrado `error\|fail\|exception\|traceback` |
| 3 | T2 R4 | filtrado `r4\|banco\|pago\|consulta\|notifica\|fs_pago\|fs_pedido` |
| 4 | T3 Dispatch | `journalctl -u prometeo-telegram` filtrado `dispatch\|chofer\|entrega\|botellon` |

## 2. Qué buscar en cada terminal

**T1 Meta** (pasos 1-4 del flujo): al enviar el WhatsApp del cliente deben aparecer
en secuencia la recepción del webhook `/webhook/meta`, la firma verificada
(X-Hub-Signature), el mensaje entrante y el envío de respuesta vía Graph API.
Si no aparece NADA aquí, Meta no está entregando → chequear
`curl https://valentina.estacionh2o.com/health` y el edge (skill valentina-bridge-infra).

**T2 R4** (pasos 5-9): la línea clave del pipeline financiero:
```
R4notifica: pago VERIFICADO pedido_fs=<id> ref=<ref> estado=<estado>
```
Ese `pedido_fs=<id>` es el pedido casado por
`buscar_pedidos_por_telefono_monto(emisor, monto VES, ref)`.
Después: INSERT en fs_pagos (ver en T5 el contador de pagos +1) y WhatsApp
"✅ Pago confirmado. Gracias. 💧" (paso 10). Odoo `register_payment` es best-effort:
un fallo de Odoo NO rompe el flujo.

**T3 Dispatch**: solo si el pedido tiene entrega pendiente; si no, puede quedarse
en silencio — eso es normal.

**T4 Errores**: debe quedarse en silencio. Cualquier línea que aparezca durante
la prueba es sospechosa; capturarla completa con timestamp.

**T5 Servicios**: todos los servicios en `active`. El contador PAGOS_FS debe
incrementarse en 1 justo después del "pago VERIFICADO" en T2.

## 3. Patrones de éxito

- T1: webhook/meta recibido + firma OK + respuesta enviada (sin 401/403/429).
- T2: `pago VERIFICADO pedido_fs=N ref=...` seguido de la confirmación WhatsApp.
- T5: `PAGOS_FS` +1 respecto al valor previo a la prueba.
- Verificación SQL del Líder (post-pago):
```bash
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/conversations.db \
  "SELECT id, fs_pedido_id, cliente_telefono, monto_eur, monto_ves, tasa_eur_ves_pago, verificado, creado_at FROM fs_pagos ORDER BY id DESC LIMIT 3"
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/conversations.db \
  "SELECT id, estado_pago, monto_pagado_eur FROM fs_pedidos WHERE id=<pedido_fs>"
```
- Nota: `fs_pagos` tiene trigger de auditoría `trg_audit_fs_pagos_insert`; el INSERT
  también queda reflejado en `fs_audit_log`.

## 4. Patrones de fallo

- `R4notifica: no hay pedido pendiente para emisor=... monto=... VES ref=...`
  → la casación por teléfono+monto no encontró pedido: monto transferido ≠
  monto_total_ves esperado, o teléfono emisor no coincide, o pedido ya casado.
- `META_APP_SECRET no configurado -- rechazando webhook` (T1) → .env incompleto.
- 403 del banco (T2, HTTP del endpoint R4) → problema de whitelist/IP,
  ver skill r4-conecta-integration.
- `No se pudo obtener tasa EUR/VES` (T4/T2) → tasas caídas, usaría fallback.
- `R4consulta` sin respuesta del banco → banco no alcanzó el webhook.
- 429 en Graph API (T1) → rate limit Meta, la respuesta al cliente falla aunque
  el pago ya esté procesado.

## 5. Cuándo intervenir vs dejar solo

- **Dejar solo**: todo lo que el Líder hace por WhatsApp y el banco (crear pedido,
  pagar). El monitoreo es pasivo: no enviar mensajes de prueba ni tocar la BD.
- **Intervenir solo si**: algún servicio en T5 pasa a `failed` DURANTE la prueba,
  o T4 muestra traceback repetido. En ese caso: capturar logs con timestamps,
  NO reiniciar servicios a mitad de la transacción salvo orden explícita del Líder.
- **Nunca**: ejecutar el pago, crear pedidos, ni corregir datos a mano mientras
  el Líder valida. El Líder aprende leyendo los logs.

## 6. Tasa BCV/EUR (verificada 2026-09-12, ver punto 7 del informe)

- `get_eur_ves_rate()` (src/financial/currency.py): consulta online, NO está
  hardcodeada en .env. Prioridad 1: `open.er-api.com` (EUR/VES directo),
  prioridad 2: frankfurter (solo EUR/USD referencia), prioridad 3: última tasa
  guardada en `fs_tasas_cambio`.
- Última tasa registrada en BD: **EUR/VES = 977.88** (open_er_api,
  2026-09-12T09:21 -04:00). USD/VES = 842.21.
- ⚠️ Los 82 pedidos pendientes actuales tienen `tasa_eur_ves = 823.94` (tasa vieja).
  El pedido que cree el Líder debe usar tasa coherente con la del momento del pago,
  porque la casación R4 es por MONTO VES transferido vs monto esperado.

## 7. Pedidos pendientes (pre-prueba, 09:4x -04:00)

82 pedidos con `estado_pago='pendiente'`, todos `cliente_telefono=c2ebf4c2d575b0db`
(telefone hash), tasa 823.94, montos EUR 1.0–5.4. Esquema real: la columna de
estado es `estado_pago` (valores 'pendiente'/'pagado'), no `status`.
