# META WhatsApp — Producción Final

**Fecha de cierre:** 2026-09-11 ~21:10 (-04)
**Responsable técnico:** Prometeo (💧 directiva del Líder)
**Estado:** ✅ EN PRODUCCIÓN — validado end-to-end con datos reales

---

## Arquitectura (pipeline bidireccional)

```
                ┌─────────────────────────────────────────────┐
                │              CLIENTE (WhatsApp)              │
                └──────────────────────┬──────────────────────┘
                                       │ wa msg
                                       ▼
                ┌─────────────────────────────────────────────┐
                │        META CLOUD API (graph v25.0)          │
                │   WABA: Estacion H2O Maracaibo + EstacionH20 │
                │   Número: +58 422-7119156                    │
                └──────┬────────────────────────┬─────────────┘
           webhook POST│                         │ POST /messages
        (valentina.    ▼                         ▼
         estacionh2o.com via                     │
         Cloudflare tunnel)          ┌─────────────────────────┐
                ┌─────────────────┐   │   valentina-bridge      │
                │  api/bridge.py  │──▶│  (systemd service)     │──┘
                │  verify + dedup │   │  → Dify (LLM)         │
                └─────────────────┘   │  → /webhook/r4/*       │
                                     └─────────────────────────┘
```

Flujo completo verificado:

    Cliente → Meta → webhook (Cloudflare tunnel → api/bridge.py)
           → bridge (Dify) → respuesta → POST /messages (Meta)
           → Cliente (respuesta automática de Valentina)

## Credenciales (nombres, sin secrets — valores viven en .env, gitignored)

| Variable | Valor/Nota |
|---|---|
| META_ACCESS_TOKEN | System User permanente (valentina-bot) — **no expira** |
| META_PHONE_NUMBER_ID | `1300557096469075` (producción) |
| META_VERIFY_TOKEN | Sincronizado con Meta dashboard (ver .env) |
| META_API_VERSION | `v25.0` |
| WhatsApp Business | +58 422-7119156 |

**Corrección clave:** el phone_number_id anterior `1186108677920030`
era de sandbox. Corregido a `1300557096469075` (producción) y la WABA
quedó asignada a valentina-bot (Estacion H2O Maracaibo + EstacionH20).

## Test final (2026-09-11 ~21:10)

- POST /messages (Graph API v25.0) → **200 OK**, respuesta incluía el
  `wa_id` del Líder → entrega confirmada a Meta.
- Valentina respondió automáticamente con mensaje "fuera de horario"
  → pipeline de entrada (webhook → bridge → Dify → respuesta) operativo.
- Bidireccionalidad completa confirmada con datos reales.

**wamid del test:**
`wamid.HBgMNTg0MTIyNTYwNzIwFQIAERgSNjVERDQ4QTI1RTE4RDMwM0FDAA==`

## Cierre de deuda

DT-30 (DEUDAS_TECNICAS_Y_PROYECTOS.md) → ✅ CERRADA con este test.
