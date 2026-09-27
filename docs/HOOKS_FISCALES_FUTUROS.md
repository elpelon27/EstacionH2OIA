# Hooks Fiscales Futuros — Facturación Electrónica SENIAT

Fecha: 2026-09-27 · Bloque 5 Fase 5.2 · Prometeo 💧
Estado: SOLO DOCUMENTACIÓN. NO hay código fiscal implementado (por decisión del
Líder: las facturas formales siguen manuscritas en libretas físicas; NO inscrito
en SENIAT electrónico).

## Situación actual

- Los PODs generan `account.move` (out_invoice) en Odoo 17 con ref `ND-POD-<id>`,
  posted, sin impuestos (IVA removido de los 4 productos), moneda EUR.
- Los pedidos fs_* generan invoices con ref `FS-<pedido_id>`.
- NINGUNA de estas invoices es un documento fiscal legal en Venezuela: son
  respaldo interno de deuda/venta. El documento tributario vigente es la
  libreta física manuscrita.

## Endpoints preparados (a implementar cuando el Líder se inscriba)

### POST /api/fiscal/invoice
Recibe datos de la invoice Odoo, genera el XML fiscal y lo envía al SENIAT.

```
POST /api/fiscal/invoice
{
  "odoo_invoice_id": 123,
  "rif_emisor": "J-XXXXXXXX",
  "cliente_rif": "V-12345678",
  "cliente_nombre": "...",
  "base_imponible": 4.20,
  "iva": 0.71,           // 16% VE si aplica al producto
  "total": 4.91,
  "moneda": "VES",
  "tasa_bcv": 40.00
}
→ {"status": "enviada", "xml_ref": "...", "seniat_control": "..." (futuro)}
```

### GET /api/fiscal/status
```
GET /api/fiscal/status
→ {"inscrito": false, "certificado": false, "invoices_pendientes_fiscal": 0}
```

## Flujo futuro completo (cuando se active)

```
1. POD firmado (PWA)
2. Worker pod_odoo_sync crea Odoo invoice (ref ND-POD-<id>)        [YA EXISTE]
3. Worker fiscal NUEVO: lee invoices posted SIN campo
   x_fiscal_ok (nueva columna a añadir en account_move o campo
   related en el modelo)
4. Genera XML fiscal con: RIF emisor, RIF cliente (cédula ya se
   captura en el POD), base, IVA, total en VES a tasa BCV
   (fs_tasas_cambio ya la alimenta el cron R4).
5. Envía al SENIAT (API/portal cuando esté disponible el servicio
   de facturación electrónica asignado).
6. Recibe número de control fiscal → lo guarda en la invoice
   (ref o campo nuevo) y marca fiscal_ok=1.
7. La libreta física deja de ser el documento fiscal → se retira
   del flujo.
```

## Requisitos para activación (checklist del Líder)

1. **Inscripción SENIAT** en el régimen de facturación electrónica
   (portal del SENIAT, RIF de la empresa al día).
2. **Certificado digital** de la empresa (firma electrónica).
3. **RIF de la empresa** configurado en Odoo (res.company.vat) —
   hoy My Company no tiene RIF cargado.
4. **Impuestos**: si el agua/hielo llevan IVA VE, restaurar el
   impuesto en los productos (fue removido en Bloque 1 para
   invoices internas) o configurar impuesto solo en el flujo fiscal.
5. **Config de endpoints SENIAT** (URLs del proveedor autorizado,
   credenciales) → variables FISCAL_SENIAT_URL etc. en config/.env.
6. Decidir moneda fiscal: hoy Odoo opera en EUR con conversión
   VES a tasa BCV; el documento fiscal VE probablemente exigirá VES.

## Qué NO hay que tocar cuando llegue el momento

- El flujo POD → Odoo ya produce invoices con toda la información
  necesaria (cliente, cédula, productos, montos). El worker fiscal
  solo leerá de Odoo; no duplica lógica.
- La cédula capturada en la PWA (pod_records.client_cedula) es el
  futuro RIF del cliente en facturas fiscales — ya se guarda.
- Las tasas BCV ya se sincronizan (cron R4 → fs_tasas_cambio).

## Estimación cuando se active

| Tarea | Estimación |
|---|---|
| Modelo fiscal (campos en account.move + config) | 1 d |
| Generador XML (formato SENIAT VE) | 2-3 d |
| Cliente envío + recepción control fiscal | 2 d |
| Endpoints /api/fiscal/* + tests | 1-2 d |
| Migración de libretas físicas pendientes | 0.5 d |
| **Total** | **6-9 d hábiles** |
