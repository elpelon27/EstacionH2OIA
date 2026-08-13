# README — Integraciones Estación H2O (Odoo + R4 Conecta)

**Estado**: Operacional · **Última actualización**: 2026-08-12

Estas son las dos integraciones externas del hogar-servidor. La fuente de verdad
de cada decisión de diseño está en los ADRs (008 y 009).

---

## 1. Odoo 17 (ERP contable + inventario)

| Aspecto | Valor |
|---|---|
| Stack | Docker Compose (`infra/odoo/docker-compose.yml`) |
| Servicios | `odoo-web` :8069 · `odoo-db` (Postgres 15) :5433 |
| BD Odoo | `postgres` (user `odoo`, pass en `infra/odoo/.env`) |
| Cliente | `src/integrations/odoo/odoo_sync.py` (XML-RPC con pooling/retry) |
| Config | `infra/odoo/.env` → `ODOO_URL/DB/USERNAME/PASSWORD` |
| Mock | No; requiere Odoo real corriendo |

### Modelos sincronizados
- `res.partner` (clientes, RIF en `vat`)
- `product.product` (botellón, hielo, insumos)
- `stock.picking` (notas de entrega) → `button_validate` → `done`
- `sale.order` + `account.move` (conversión nota → factura, sin doble descuento)
- `ir.cron` / `ir.actions.server` (reportes automáticos)

### Comandos útiles
```bash
# Cliente conecta
venv/bin/python -c "from src.integrations.odoo.odoo_sync import OdooClient; c=OdooClient(); print(c.connect())"

# Reporte diario (cron)
venv/bin/python scripts/odoo_reporte_ventas_diarias.py
```

### Nota Odoo 17 (stock_sms)
Al validar un `stock.picking` de salida, el módulo `stock_sms` puede abrir un
wizard SMS. Para validaciones programáticas pasar `{"context": {"skip_sms": True}}`
en `button_validate` (ver `tests/e2e/test_fase8_e2e.py`).

---

## 2. Banco R4 Conecta V3.0 (pago móvil)

| Aspecto | Valor |
|---|---|
| Módulos | `src/integrations/r4/` (codigos, hmac_auth, client, webhooks) |
| Procesador FASE 6 | `src/financial/banco_verificador.py` |
| Endpoints | `/webhook/r4/consulta`, `/webhook/r4/notifica`, `/webhook/r4/health` |
| Seguridad | IP whitelist + Bearer token + HMAC-SHA256 + rate-limit |
| Config | `R4_COMMERCE_TOKEN`, `R4_ID_COMERCIO`, `R4_BASE_URL` (config/.env) |

### Flujo pago móvil
1. Cliente inicia pago → R4 llama `/webhook/r4/consulta` (validamos cliente+pedido)
2. Pago aprobado → R4 llama `/webhook/r4/notifica` (CodigoRed=00)
3. `procesar_notifica_pago_movil` busca match teléfono+monto → llama
   `verificar_pago_manual` (Financial Shield) → `estado_pago='pagado'`
4. ACK al banco `{"abono": true}`

### Health R4
```bash
curl -s http://localhost:8000/webhook/r4/health
```

### ⚠️ Corregido 2026-08-12 (bug FASE 6)
La verificación real estaba indentada dentro del bloque "pedido ya pagado"
(código muerto). Corregido en `banco_verificador.py`; requiere restart del bridge.

---

## 3. Monitoreo (FASE 9)

- `/health` → checks: `odoo`, `dispatch_db`, `dispatch_queue_pending` (además de
  dify/meta/sqlite/telegram/kill_switch)
- `/metrics` → nuevas gauges: `valentina_odoo_up`, `valentina_dispatch_queue_pending`
- `/metrics` protegido por IP allowlist (localhost + 172.19/16)

```bash
curl -s http://localhost:8000/health | python3 -m json.tool
curl -s http://localhost:8000/metrics | grep -E "valentina_odoo_up|dispatch_queue_pending"
```
