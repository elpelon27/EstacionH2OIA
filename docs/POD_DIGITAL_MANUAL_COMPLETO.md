# POD Digital — Manual Completo (Bloques 1-5)

Fecha cierre: 2026-09-27 · Prometeo 💧 · Proyecto: POD Digital + Odoo + Créditos
Estado: 100% COMPLETO (Bloques 1-5 terminados y verificados)

## 1. Arquitectura final

```
                          CELULAR/TABLET DEL CHOFER (equipo empresa)
                    ┌─────────────────────────────────────────────────┐
                    │  PWA web/pod_form.html (offline-first)         │
                    │  - PIN chofer (4 dígitos, 3 intentos, alerta)   │
                    │  - Nota: productos, precios, saldo (server-side)│
                    │  - Firma canvas + cédula + foto + vacíos/tapas │
                    │  - IndexedDB: cola offline → sync automático    │
                    └───────────────┬─────────────────────────────────┘
                                    │ ?token=veh (revocable)
                    ┌───────────────▼─────────────────────────────────┐
                    │  BRIDGE FastAPI (valentina-bridge :8000)         │
                    │  GET  /pod/{id}          → PWA HTML              │
                    │  GET  /api/pod/{id}      → datos nota            │
                    │  POST /api/pod/submit    → firma+foto+estado    │
                    │  GET  /api/pod/status/{id}                      │
                    │  POST /api/pod/pin/{id}  → PIN (423 bloqueo)    │
                    │  Kill-switch: data/pod_revoked.json             │
                    └───────┬──────────────────────┬───────────────────┘
                            │                      │
            botón ✅ Entregado             worker cron */5
            (Telegram chofer)              scripts/pod_odoo_sync.py
                    │                      │
        ┌───────────▼──────────┐   ┌───────▼──────────────────────┐
        │ @DespachoH2O_bot     │   │ ODOO 17 (estacion_h2o, EUR)   │
        │ crea pod_record      │   │ partner → picking → invoice  │
        │ pending + link firma │   │ → payment (si R4 confirmado)  │
        └──────────────────────┘   │ 4 productos: AGUA/HIELO/     │
                                 │  VACIO(swap)/TAPAS(consu)     │
                                 └───────┬────────────────────────┘
                                         │ cron */15
                                 ┌───────▼──────────────────────┐
                                 │ scripts/fs_odoo_sync.py       │
                                 │ fs_pedidos↔Odoo (bidireccional)│
                                 │ fs_pagos→payments             │
                                 │ Odoo= fiscal, fs_*= operativo │
                                 └──────────────────────────────┘

  CRÉDITO: fs_pedidos/fs_pagos (conversations.db) — PURGADO, arranque en 0
  RESUMEN: scripts/credit_summary.py — cron lunes 8AM + /resumen on-demand
  FISCAL: docs/HOOKS_FISCALES_FUTUROS.md (SENIAT pendiente inscripción)
```

## 2. Flujo completo de una entrega

1. **Planificación**: auto-router materializa orders_auto → deliveries
   (skills/dispatch/auto_materializer.py, 7:45 AM).
2. **Chofer**: bot @DespachoH2O_bot → /ruta → [📍 Llegué] → GPS →
   [✅ Entregado].
3. **Botón Entregado**: marca delivered + crea pod_record pending +
   responde con el link de firma: `http://valentina.estacionh2o.com:8000/pod/<id>?token=<token>`.
4. **PWA**: chofer abre link → PIN → nota con datos → cliente firma en
   canvas + cédula + foto (si no firma/rechaza) + vacíos/tapas → Confirmar.
5. **Offline**: sin señal → IndexedDB ("Guardado local") → al recuperar
   reenvía automático → "Sincronizado".
6. **Worker */5min**: POD signed/photo_only → Odoo: partner →
   delivery note (AGUA+HIELO+VACIO swap+TAPAS) → picking done →
   invoice posted → pago si fs_pagos verificado → synced_to_odoo=1.
7. **Crédito**: fs_pedidos acumula la deuda (ciclo semanal).
8. **Lunes 8 AM**: cron credit_summary --weekly envía WhatsApp (Meta
   Cloud API) a cada cliente con saldo. Comprobante → Valentina/R4.
9. **Líder**: /resumen <tel> para ver o enviar on-demand.

## 3. Comandos @Skynet_27_bot (todos, guard chat_id del Líder)

| Comando | Qué hace |
|---|---|
| /resumen <tel> | Preview estado de cuenta del cliente |
| /resumen <tel> send | Envía el resumen por WhatsApp al cliente |
| /revoke_vehicle <id> | Kill-switch: revoca token, PWA 403, PODs offline → comprometidos |
| /activate_vehicle <id> | Reactiva el vehículo revocado |
| /reset_pin <id> | Desbloquea PIN (limpia intentos fallidos) |
| /set_peso <tel> <tipo> | Clasificación de clientes (preexistente) |
| /unset_peso <tel> | Quita clasificación |
| /list_peso / /list_tipo | Listados de clientes |
| /client_info <tel> | Ficha completa del cliente |

Bot chofer @DespachoH2O_bot: /start /ruta /siguiente /status /plan /help
+ botones Llegué/Entregado/No responde.

## 4. Cómo abrir la PWA en el celular

1. El chofer recibe el link del bot al marcar Entregado (o el Líder lo
   arma: `http://<servidor>:8000/pod/<delivery_id>?token=<POD_VEHICLE_TOKEN>`).
2. Abrir en Chrome (Android). PIN del chofer: POD_CHOFER_PIN en config/.env.
3. Para instalar como app: menú Chrome → "Agregar a pantalla de inicio".
4. Requisito: haber cargado la nota una vez para cache offline
   (localStorage) — sin señal se puede firmar si ya se abrió antes.

## 5. QR WAHA (cuando llegue el chip)

El puente WhatsApp (Valentina) usa WAHA docker. Al llegar el chip:
1. `docker ps | grep waha` → verificar contenedor.
2. Abrir `http://<servidor>:3000` (puerto WAHA) → escanear QR con el
   app WhatsApp Business del número de Valentina.
3. Verificar sesión: `curl http://localhost:3000/sessions` → status
   SCAN_QR_CODE → WORKING.
4. Los resúmenes de crédito NO dependen de WAHA (usan Meta Cloud API),
   WAHA es para el canal conversacional de Valentina.

## 6. Troubleshooting

| Problema | Solución |
|---|---|
| PWA "Acceso denegado" | Token inválido o vehículo revocado (/activate_vehicle) |
| PIN bloqueado (3 fallos) | /reset_pin <vehicle_id> desde @Skynet_27_bot |
| "Guardado local" permanente | Verificar señal del celular; al reconectar reenvía solo. Si no: abrir la PWA de nuevo (reintento al cargar) |
| POD no llega a Odoo | Ver logs/pod_sync.log; worker reintenta cada 5 min; revisar `docker ps` de odoo-web/odoo-db |
| Invoice sin pago en Odoo | El pago llega si fs_pagos.verificado=1 (R4). Ver logs/fs_sync.log |
| Foto no se guardó | data/pod_photos/ — verificar espacio en disco |
| Resumen semanal no salió | logs/credit_summary.log; verificar META_ACCESS_TOKEN y que fs_pedidos tenga pendientes |
| POD 'compromised' | Vehículo fue revocado con PODs sin sync → validar manualmente y re-sincronizar |
| Odoo auth falla | Credenciales en infra/odoo/.env (ODOO_DB=estacion_h2o) |

## 7. Variables de entorno (config/.env)

```
POD_VEHICLE_TOKEN=h2o-pod-2026-veh1     # token único (todos los vehículos)
POD_VEHICLE_TOKENS=token1:1,token2:2    # o mapa token:vehicle (recomendado)
POD_CHOFER_PIN=1379                     # PIN PWA (CAMBIAR en producción)
POD_SIGN_URL=http://valentina.estacionh2o.com:8000/pod
POD_PHOTO_DIR=data/pod_photos
POD_HTML_PATH=web/pod_form.html
POD_PRECIO_AGUA=1.00
POD_PRECIO_HIELO=1.20
ODOO_URL / ODOO_DB / ODOO_USERNAME / ODOO_PASSWORD   # ver infra/odoo/.env
TELEGRAM_ALERT_CHAT / TELEGRAM_ALERT_TOKEN            # alertas PIN bloqueado
```

## 8. Crons activos del proyecto

| Cron | Script | Log |
|---|---|---|
| */5 * * * * | scripts/pod_odoo_sync.py | logs/pod_sync.log |
| */15 * * * * | scripts/fs_odoo_sync.py | logs/fs_sync.log |
| 0 8 * * 1 | scripts/credit_summary.py --weekly | logs/credit_summary.log |

## 9. Tests de regresión (todos ALL PASSED)

```bash
venv/bin/python tests/unit/test_pod_bloque2.py             # esquema + botón Entregado
venv/bin/python tests/unit/test_pod_endpoints_bloque2.py  # endpoints API
venv/bin/python tests/unit/test_pwa_bloque3.py            # PWA + PIN + E2E
venv/bin/python tests/unit/test_pod_odoo_sync_bloque4.py   # worker Odoo (usa Odoo real)
venv/bin/python tests/unit/test_fs_odoo_sync_bloque4.py    # fs_* ↔ Odoo
venv/bin/python tests/unit/test_credit_summary_bloque4.py  # resumen + /resumen
venv/bin/python tests/unit/test_killswitch_bloque5.py     # kill-switch
```

## 10. Pendientes del Líder (post-proyecto)

1. Cambiar POD_VEHICLE_TOKEN y POD_CHOFER_PIN de test por producción.
2. Cargar inventario inicial real en Odoo WH/Stock (hoy 0, orden abierta).
3. Cargar RIF de la empresa en Odoo + partners reales con cédula.
4. Probar PWA en celular real (canvas/firma con dedo + cámara).
5. Definir URL pública definitiva (dominio/puerto/HTTPS).
6. Inscripción SENIAT cuando se decida (ver docs/HOOKS_FISCALES_FUTUROS.md).
7. Tokens por vehículo reales en POD_VEHICLE_TOKENS para kill-switch granular.
