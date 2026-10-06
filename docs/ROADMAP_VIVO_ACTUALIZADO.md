# ROADMAP VIVO ACTUALIZADO — Estación H2O

**Revalidación en vivo:** 2026-09-30 → 2026-10-01 (barrido completo, solo lectura)
**Actualización:** 2026-10-05 (jornada DT-36→DT-52: 6 fixes de prueba de campo, pilotos DT-31/DT-33, bug QR producción). Ver §0.
**Auditor:** Prometeo 💧 · **Regla aplicada:** verificación con datos de primera mano, no informes previos.

> ⚠️ Este documento reemplaza el estado de `docs/DEUDAS_TECNICAS_Y_PROYECTOS.md`
> (cuya última actualización era 2026-09-27, desactualizado en varios puntos).
> Las tablas de abajo se armaron con `curl`, `sqlite3`, `docker ps`, `systemctl`
> y `pytest` ejecutados durante esta auditoría, no copiando el doc anterior.

---

## 0. ACTUALIZACIÓN 2026-10-05 — DT-31/32/33/34 CERRADAS + jornada DT-46

> Piloto con verificación en vivo. Todas las líneas de abajo llevan comando real ejecutado.

| Ítem | Estado | Evidencia (2026-10-05) |
|---|---|---|
| **DT-31 comandos de seguridad** | ✅ **CERRADA** | getMyCommands @Skynet_27_bot = **30** (11 seguridad + 4 clientes: resumen/revoke_vehicle/activate_vehicle/reset_pin + 15 originales). Log `set_my_commands OK: 30`. Nota: el menú ya tenía los 11 de seguridad el 01-oct (doc desactualizado); faltaban los operacionales. Commit `4b0e3a87`. |
| **DT-32 cloudflared** | ✅ **ESTABILIZADA** | 0 caídas en la última hora (antes: 95/h), servicio active, edge HTTP 200 ×3 consecutivos. **Vigilar 48h más** antes de cerrar definitivamente. |
| **DT-33 tests / colección** | ✅ **CERRADA** | 1070 tests recogidos sin errores de colección; corrida completa **1055 passed / 15 skipped / 0 failed**, cobertura **67%** (era 60%). QR asset fix commit `7af36a5d`. |
| **DT-34 Redis** | ✅ **RECUPERADA** | `DBSIZE=10` (era 0), PING OK, warming escribiendo. Pendiente TAREA-3 de esta jornada: verificar cron warming activo para prevenir recaída. |
| **BUG QR PRODUCCIÓN (nuevo hallazgo)** | ✅ **FIXEADO** | bridge.py:1759 `QR_R4_OFICIAL_PATH` apunta a `qr_r4_oficial.png`; el QR bancario fue subido como `.jpg` el 03-oct → **el QR del Pago Móvil jamás habría llegado a un cliente** (falla silenciosa). Fix: PNG generado desde el JPG (Pillow; .jpg original conservado). Commit `7af36a5d`. Enlaza con DT-46/Issue-2. |
| **DT-46 (prueba de campo del Líder)** | ✅ **FIXES APLICADOS** | FIX 1A doble-log handler (consumer.py, verificado 1 línea no 2); FIX 3 GPS-validado → skip re-pedir dirección (13/13 + 12/12 tests, commits snapshot 7c19bdce/6be3c6a3 + marker 0c8ae4cf); FIX 4 Fase 1: 3 deliveries stale de Yordanis → cancelled (pending v1 = 0); FIX 5 Parte 1: POD_SIGN_URL → `https://valentina.estacionh2o.com/pod` (antes `:8000` muerto desde internet); FIX 6 aviso cercanía = NO IMPLEMENTADO (deuda, ver DEUDA_TECNICA_DT46.md). |
| **Fase A containerd (DT-39)** | ✅ **MIGRADA + renombrada** | `/var/lib/containerd.purge-20261004_210605` espera borrado definitivo **2026-10-11**. |
| **Fase B Chrome→SSD** | ❌ **CANCELADA** | Chrome no soporta symlinks para `~/.cache`/`~/.config/google-chrome`. Copias huérfanas del SSD (4.6GB) eliminadas 2026-10-05: SSD 170G→165G usado. |

Deuda técnica derivada de DT-46 (detalle en `docs/02-arquitectura/DEUDA_TECNICA_DT46.md`):
- **DT-46-A** asignación por GPS choferes (política carga se mantiene) · **DT-46-B** link POD
  automático al cliente · **DT-46-C** aviso de cercanía (bloqueada por DT-46-A).
- **DT-35** sigue ABIERTA: 4/363 clientes clasificados (requiere criterio del Líder).

---

## 1. ESTADO ACTUAL DEL SISTEMA (resumen ejecutivo)

### 🟢 EN PRODUCCIÓN (verificado)

| Servicio | Evidencia en vivo |
|---|---|
| **WAHA logística** | `waha` Up 2h **(healthy)**, compose con `restart: always` + healthcheck |
| **2 números vinculados** | `chofer_1` WORKING `584222560722@c.us` · `chofer_2` WORKING `584222560723@c.us` |
| **Auto-reconnect WAHA** | cron cada 15 min; probado en real (sesión detenida → RECUPERADA) |
| **OSRM local** | HTTP 200 en ruta de prueba; contenedor `osrm` Up |
| **Dispatcher bot** | `active`; 22 tests pasan; `/start` ofrece YORDANIS / EVERT |
| **DT-01 choferes registrados** | chat_ids reales: `8806724603` (YORDANIS), `8987840684` (EVERT) |
| **mobile-mcp** | servicio `active` en 127.0.0.1:3010; 33 herramientas descubiertas |
| **Celulares endurecidos (2)** | GPS alta precisión, brillo 255, apagado 10 min, apps verificadas |
| **Valentina bridge (local)** | `localhost:8000/health` → 200 |
| **Meta token producción** | `meta_access_token: True`, `meta_phone_number_id: True` |
| **Odoo sync** | `odoo: True` en health público |
| **OpenNotebook** | contenedores Up; HTTP 200 en 8502 (`/notebooks`) y API 5055 |
| **Ollama + nomic-embed-text** | HTTP 200; modelo de embeddings presente |
| **Whatsscanbot** | `active`; DeepSeek V4 Flash primario en `llm_client.py` |
| **363 clientes cargados** | `SELECT COUNT(*) FROM clients` → 363 |
| **Clasificación 11 tipos** | `TIPOS_VALIDOS` en `skills/client_commands.py` (3 N1 + 7 N2 + residencial) |
| **Rate limiting** | slowapi en `api/bridge.py` con clave dual (IP + teléfono) |
| **Geocerca con polígono** | `scripts/security/geofence.py` + `load_polygon_kml.py` |
| **POD Digital** | `web/pod_form.html` + `pod_odoo_sync.py` + `fs_odoo_sync.py` |
| **Kill-switch revocable** | `/revoke_vehicle` en `skills/client_commands.py` |

### 🟡 STANDBY / PARCIAL

| Ítem | Estado real |
|---|---|
| **Túnel Cloudflare** | ⚠️ **INESTABLE** — 95 caídas en la última hora; 502 intermitente (detalle abajo) |
| **Cobertura tests** | 1005 passed / 1 failed / 14 skipped / 3 errors — **60%** |
| **Clasificación de clientes** | Código listo (11 tipos) pero solo **4 de 363** tienen `client_type` |
| **R4 Conecta** | Código completo; `fs_pagos` en 0 (sin pagos desde la purga de arranque limpio) |
| **D10 warming SOUL** | Parches listos; `auto_activation_ready()` → **True** (cumplió 21 días) |
| **Sprint 3 Swap E2E** | Desbloqueado por DT-01; check-in y flujo con código listo |
| **Bot @Skynet_27_bot** | 15 comandos registrados (doc decía 17); los 11 de seguridad **no están en el menú** |

### 🔴 BLOQUEADO

| Ítem | Bloqueo |
|---|---|
| **5 archivos de test rompen la colección** | Errores en *import time* abortan **toda** la suite (1023 tests recogidos → 0 ejecutados si no se ignoran) |
| **Cloudflared en crash-loop** | Requiere investigación de causa raíz (ver §5) |
| **Inventario inicial Odoo** | Acción del Líder (documentado en POD_DIGITAL_MANUAL_COMPLETO) |
| **Inscripción SENIAT / RIF** | Acción del Líder (hooks fiscales documentados) |

---

## 2. DEUDAS TÉCNICAS — tabla con estado real

| ID | Deuda | Estado | Acción necesaria | Quién |
|---|---|---|---|---|
| **DT-01** | `vehicles.telegram_chat_id` NULL | ✅ **CERRADA 2026-10-01** | Ninguna. chat_ids reales verificados: `8806724603`, `8987840684` | Choferes (hecho) |
| **DT-12** | Cobertura de tests | 🟡 **PARCIAL** | 1005 passed, **60%** cobertura. Bloqueante real: 5 archivos rompen la colección | Prometeo |
| **DT-13** (doc: DT-28) | OpenNotebook embedding bug | ✅ **CERRADA** | HTTP 200 en 8502 y 5055; Ollama + `nomic-embed-text` operativos | — |
| **DT-14** (doc: DT-29) | Webhook Meta sin HTTPS | ✅ **CERRADA** (con asterisco) | Cloudflare tunnel configurado. ⚠️ pero el túnel está inestable → ver DT-32 | Prometeo |
| **DT-15** (doc: DT-30) | Token Meta debug-only | ✅ **CERRADA** | `meta_access_token: True` en health público | — |
| **D3** | R4 Conecta E2E | 🟡 **CERRADA→verificar** | Pipeline documentado como verificado con pago real. `fs_pagos` en 0 → sin pagos nuevos desde purga. Webhook responde 403 a IP no autorizada (correcto, HMAC/IP) | — |
| **D6** | Redis | ⚠️ **REABIERTA** | `DBSIZE` = **0**. Redis activo y persistente, pero **vacío** — el warming no está escribiendo. Revisar por qué | Prometeo |
| **D10** | SOUL FASE 3 parches | ✅ **CERRADA 2026-10-01** | Parches implementados; `auto_activation_ready()` → `True` (21+ días desde 2026-09-10) | — |
| **D14** | Factura Meta | ✅ **CERRADA** | Confirmada por el Líder 2026-09-09 | — |
| **DT-31** | Comandos de seguridad del bot | ✅ **CERRADA 2026-10-05** | getMyCommands = 30 (11 seguridad + 4 clientes + 15 originales). Commit `4b0e3a87`. Nota: el menú ya tenía los 11 de seguridad el 01-oct; doc previo desactualizado | Prometeo |
| 🆕 **DT-32** | **Cloudflared en crash-loop** | ✅ **ESTABILIZADA 2026-10-05** | 0 caídas/hora, edge 200×3. Vigilar 48h. (Antes: 95 caídas/hora, `status=2/INVALIDARGUMENT`, 502 intermitente) | Prometeo |
| 🆕 **DT-33** | **5 tests rompen la colección** | ✅ **CERRADA 2026-10-05** | Colección sana (1070 recogidos, 0 errores); corrida completa 1055 passed / 0 failed, 67% cobertura. Fix del asset QR: commit `7af36a5d` | Prometeo |
| 🆕 **DT-34** | **Redis vacío** (derivada de D6) | ✅ **RECUPERADA 2026-10-05** | `DBSIZE=10` (era 0), warming escribiendo. Verificar cron para prevenir recaída | Prometeo |
| 🆕 **DT-35** | **Clasificación de clientes sin datos** | 🟡 **NUEVA** | 11 tipos en código, solo **4/363** clientes con `client_type='retail'` | Líder/Prometeo |

### Nota sobre DT-01 — verificación con datos

```
sqlite3 data/dispatch.db "SELECT id, name, operator_name, telegram_chat_id FROM vehicles;"
1 | Triciclo 1 | YORDANIS | 8806724603   ✅ (antes: 111111 falso de tests)
2 | Triciclo 2 | EVERT    | 8987840684   ✅ (antes: 222222 falso de tests)
```

Los valores `111111`/`222222` venían de fixtures de test y bloqueaban el
registro porque el query exige `telegram_chat_id IS NULL`. Limpiados el
2026-09-30; los choferes completaron `/start` y el sistema los registró.

---

## 3. PROYECTOS COMPLETADOS

| Proyecto | Fecha | Commits / evidencia |
|---|---|---|
| POD Digital Bloques 1-5 | 2026-09-27 | `web/pod_form.html`, 7 suites de tests |
| Vinculación WAHA 2 números | 2026-09-30 → 10-01 | `2a9c2f03`, `76bdf49a`, pairing code (QR roto en WAHA 2026.9.1) |
| WAHA docker-compose + auto-reconnect | 2026-10-01 | `ffae88b6`, `67dd5209` (fix healthcheck 401) |
| Dispatcher bot refrescado | 2026-09-30 | `50ee6537` · DT-01 desbloqueada |
| mobile-mcp integrado | 2026-10-01 | `3d122037` · 33 herramientas |
| Celulares endurecidos (2) | 2026-10-01 | `2a9c2f03` (Yordanis), `76bdf49a` (Evert) |
| Endurecimiento + script | 2026-10-01 | `3d4281b9` |
| SOUL FASE 3 (D10) | 2026-10-01 | `auto_activation_ready() = True` |
| Meta producción (DT-15) | 2026-09-11 | System User permanente, WABA asignada |
| Webhook HTTPS (DT-14) | 2026-09 | Cloudflare tunnel `valentina.estacionh2o.com` |
| R4 Conecta (D3) | 2026-09-12 | Pago real verificado Bs. 2.933,63 |
| Campaña mypy | 2026-08-17 | 0 errores en 89 archivos |
| Observabilidad Prometheus/Grafana | 2026-08-16 | 4 dashboards, 23 reglas de alerta |

---

## 4. PROYECTOS PENDIENTES (con prioridad)

| Proyecto | Prioridad | Estimación | Bloqueo |
|---|---|---|---|
| **DT-32** Estabilizar cloudflared | 🔴 **P0** | 2-4h | Causa raíz desconocida (panic en `quic_datagram_v2`) |
| **DT-33** Reparar 5 tests que rompen colección | 🔴 **P0** | 4-8h | Fixtures apuntan a DB incorrecta / bugs de nombre |
| **DT-34** Redis vacío — diagnosticar | 🟠 **P1** | 2-3h | Warming no escribe en la capa Buffer |
| **DT-31** Registrar 11 comandos de seguridad | 🟡 **P2** | 30 min | Solo falta `setMyCommands` |
| **DT-35** Clasificar 363 clientes | 🟡 **P2** | 4-8h | Requiere criterio del Líder por cliente |
| Sprint 3 Swap E2E (check-in, flujo) | 🟡 **P2** | 1-2 semanas | Desbloqueado por DT-01; falta prueba en campo |
| Registrar comandos de seguridad | 🟡 P2 | — | — |
| Loki/Promtail (log aggregation) | 🔵 **P3** | 1-2 días | No bloqueante |
| Tempo/Jaeger (tracing) | 🔵 **P3** | 2-3 días | No bloqueante |
| Backup restore test automatizado | 🔵 **P3** | 4h | No bloqueante |
| Mapa de calor GPS histórico | 🔵 **P3** | 1 día | Requiere datos de ruta acumulados |
| Runbooks CI/CD y Swap bottles | 🔵 **P3** | 4h | Documentación |

---

## 5. HALLAZGOS NUEVOS (no documentados antes)

### 🔴 DT-32 — Cloudflared en crash-loop (P0)

```
journalctl -u cloudflared --since "1 hour ago" | grep -c "Main process exited"
→ 95
```

El servicio se reinicia ~95 veces por hora con `status=2/INVALIDARGUMENT`
y un panic en `connection.(*datagramV2Connection).Serve` / `quic_datagram_v2.go:107`.

**Impacto real:** el health público devuelve **502 intermitente**
(medido: intento1=502, intento2=200, intento3=200). El bridge local está
perfecto (`localhost:8000/health` → 200). O sea: **Valentina funciona, pero el
acceso público se cae intermitentemente.**

Cuando responde, todos los checks están OK:
```
status: ok
  dify_api_key: True      meta_access_token: True
  meta_phone_number_id: True   sqlite: True
  telegram: True          kill_switch: False
  odoo: True              dispatch_db: True
```

⚠️ Esto contradice parcialmente el cierre de DT-14: el túnel existe y está
configurado, pero no es confiable hoy.

### 🔴 DT-33 — 5 archivos de test abortan toda la suite

```
pytest --co -q
→ ERROR tests/unit/test_killswitch_bloque5.py   - sqlite3.OperationalError
→ ERROR tests/unit/test_pod_endpoints_bloque2.py - NameError: name 'did2'
→ ERROR tests/unit/test_pod_odoo_sync_bloque4.py - AssertionError: None
→ ERROR tests/unit/test_pod_waha_fase2.py       - sqlite3.OperationalError
→ ERROR tests/unit/test_pwa_bloque3.py          - sqlite3.OperationalError
→ Interrupted: 5 errors during collection
→ 1023 tests collected, 5 errors
```

Todos fallan en **tiempo de import/colección**, no en ejecución. Eso aborta
la corrida completa: sin `--ignore`, el número de tests que pasan es **0**.
Ignorándolos: **1005 passed, 1 failed, 14 skipped, 3 errors — 60% cobertura**.

Es la deuda que más distorsiona la métrica de salud del proyecto.

### 🟠 DT-34 — Redis vacío (D6 reabierta)

```
redis-cli DBSIZE → 0
redis-cli PING   → PONG   (servicio sano)
```

El doc marcaba D6 como cerrada porque "warming_diario llena la capa Buffer a
diario". Hoy Redis está **vacío**. El cron de warming está instalado y
`auto_activation_ready()` devuelve True, pero no hay llaves. Hay que verificar
si el warming está corriendo y escribiendo realmente.

### 🟡 DT-31 — Comandos de seguridad no visibles en Telegram

El doc dice "Bot @Skynet_27_bot operativo con 11 comandos de seguridad".
Realidad:
- Los 11 handlers **sí existen** en `skills/security_commands.py` como `async def`
  (`blacklist_add`, `blacklist_remove`, `block`, `unblock`, `observe`,
  `credit_client`, `cliente_info`, `ataque_detectado`, `lockdown_status`,
  `lockdown_release`, `stats`, `set_gps`).
- Pero `setMyCommands` devuelve **15** comandos, ninguno de seguridad:
  `/start /stop /status /orders /logs /metrics /tasa /health /help /set_gps
   /set_peso /unset_peso /list_peso /list_tipo /client_info`

Están implementados pero **no registrados en el menú** → el Líder no los ve.
Además son 15, no los 17 que decía el doc.

### 🟡 DT-35 — Clasificación de clientes sin datos

```
SELECT client_type, COUNT(*) FROM clients GROUP BY client_type;
→ retail | 4        (de 363 clientes)
```

Los 11 tipos están en el código (`NIVEL_1` + `NIVEL_2` + residencial) y el
auto-routing Nivel 1 está implementado en `skills/client_commands.py`, pero
**359 de 363 clientes no tienen tipo asignado**. El auto-routing no puede
funcionar sin ese dato.

---

## 6. PRÓXIMOS PASOS RECOMENDADOS (top 5)

1. **🔴 Estabilizar cloudflared (DT-32)** — Es lo único que hoy hace que el
   sistema público falle intermitentemente. Valentina está sana por dentro;
   el túnel es el cuello de botella. Requiere investigación (posible bug de
   QUIC datagram en esta versión). **Sin hardware ni dinero.**

2. **🔴 Reparar los 5 tests que rompen la colección (DT-33)** — Hasta que no se
   arreglen, cualquier medición de "tests passing" es falsa (0 sin `--ignore`).
   Son fixtures apuntando a la DB incorrecta y un `NameError`. **Sin hardware.**

3. **🟠 Diagnosticar Redis vacío (DT-34)** — D6 se dio por cerrada pero la capa
   Buffer está en 0. Si el warming no está escribiendo, la memoria semántica
   no se está consolidando. **Sin hardware.**

4. **🟡 Registrar los 11 comandos de seguridad en el menú (DT-31)** — Es un
   `setMyCommands` de 30 minutos; el código ya está. **Sin hardware.**

5. **🟡 Clasificar los 363 clientes (DT-35)** — Requiere **criterio del Líder**
   (qué tipo es cada cliente). Sin ese dato el auto-routing Nivel 1 está
   implementado pero inoperante. **Requiere decisión humana, no código.**

### Lo que puede esperar
Loki/Promtail, Tempo, backup restore test, mapa de calor GPS, runbooks
faltantes. Nada de eso bloquea operación.

### Lo que requiere hardware / dinero / gestión externa
- Inventario inicial Odoo (**Líder**)
- Inscripción SENIAT / RIF empresa (**Líder**)
- URL pública de la PWA (**Líder**)
- Prueba en celular real en ruta (**choferes**)
- Migración swap bottles 165 unidades (**plan 3 semanas**)

---

## 7. MÉTRICAS DE SALUD — medidas en vivo

| Métrica | Valor real (2026-10-01) | Objetivo | ¿Cumple? |
|---|---|---|---|
| Tests passing | **1005** (con 5 archivos ignorados) | 100% | 🟡 (1 failed, 3 errors) |
| Tests recogidos | 1023 | — | 🔴 5 abortan colección |
| Cobertura total | **60%** (3453 stmts, 1390 miss) | >45% | ✅ |
| Mypy errores | 0 (según doc, no re-medido) | 0 | ✅ |
| WAHA sesiones | 2/2 WORKING | 2 | ✅ |
| Choferes registrados | 2/2 con chat_id real | 2 | ✅ |
| Celulares endurecidos | 2/2 | 2 | ✅ |
| Clientes cargados | 363 | 363 | ✅ |
| Clientes clasificados | **4** / 363 | 363 | 🔴 |
| Redis DBSIZE | **0** | >0 | 🔴 |
| Cloudflared uptime | **~95 caídas/hora** | 0 | 🔴 |
| OSRM | 200 OK | — | ✅ |
| Health público | 502 intermitente | 200 | 🔴 |

---

*Revalidación en vivo · Prometeo · 2026-10-01 · 💧*
*Regla aplicada: solo lectura (SELECT, curl, docker ps, systemctl, pytest). No se modificó código ni DB.*
