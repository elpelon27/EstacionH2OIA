# ADR-008: Integración Odoo 17 (XML-RPC)

**Estado**: Aceptado
**Fecha**: 2026-08-12
**Relaciona**: ADR-009 (R4), FASE 4 del plan de integración

## Contexto
Estación H2O necesita contabilidad e inventario confiables. Los pedidos que
atiende Valentina (WhatsApp) y el despacho por triciclos debían sincronizarse con
un ERP para: facturación electrónica (RIF), control de inventario de botellones y
hielo, y reportes de ventas/nómina. El negocio operaba con la verdad solo en
SQLite; Odoo era el destino natural por ser autohostable y sin costo de licencia.

## Decisión
Integrar **Odoo Community 17** vía **XML-RPC** como sistema de registro
contable/inventario, levantado en Docker junto al resto del hogar.

Razones:
- Odoo 17 Community: gratuito, maduro, módulos de ventas/inventario/contabilidad
- XML-RPC es el protocolo oficial y estable de Odoo para integración externa
- Docker local (`odoo-web:8069` + `odoo-db:5433`) aislado de la red externa
- La nota de entrega → factura se decide por algoritmo (ADR/documento de arquitectura §5.1)
- Auto-hosting: sin dependencia de SaaS de terceros, datos en casa

## Consecuencias
**Positivas**:
- Facturas `account.move` posteadas verificables (ej. INV/2026/00004)
- Inventario sincronizado sin doble descuento (nota → factura no re-descuenta)
- Reportes diarios/semanales de ventas, hielo, insumos y nómina vía crons

**Negativas/consideraciones**:
- XML-RPC no tiene streaming; sync por lotes con retry/backoff
- Odoo requiere mantenimiento de su Postgres (backup incluido en `backup_daily.sh`)
- El módulo `stock_sms` puede interceptar validaciones de entrega (wizard SMS); en
  tests se desactiva con `{"context": {"skip_sms": True}}`
- `process_r4notifica` del webhook R4 seguía placeholder; la FASE 6 real vive en
  `src/financial/banco_verificador.py`

## Implementación
- `src/integrations/odoo/odoo_sync.py`: cliente XML-RPC con pooling/retry
- `infra/odoo/`: docker-compose (odoo-web:8069, odoo-db:5433) + config
- Cron jobs: `r4_tasa_bcv`, `odoo_ventas_diarias`, `odoo_cierre_semanal`,
  `odoo_inventario_hielo`, `odoo_inventario_insumos`, `odoo_nomina_viernes`
- Tests E2E: `tests/e2e/test_fase8_e2e.py` (nota → factura, inventario)
