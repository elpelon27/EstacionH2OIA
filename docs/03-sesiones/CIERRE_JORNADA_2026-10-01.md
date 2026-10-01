---
tags: [cierre-jornada, sesion, logistica, waha, dispatcher, mobile-mcp, auditoria]
fecha: 2026-09-30 → 2026-10-01
turno: nocturno
estado: cerrado
---

# Cierre de Jornada — 2026-09-30 → 2026-10-01

Jornada larga. Se cerraron los frentes de logística (WAHA), dispatcher,
mobile-mcp, endurecimiento de celulares y una auditoría completa de deudas.

---

## 1. Vinculación WAHA — 2 números operativos

**Regla crítica del Líder respetada:** una entrega = un solo número de punta a
punta. El cliente ve siempre el mismo chip en cercanía, llegada, espera y PDF.

```
chofer_1  WORKING  584222560722@c.us   (YORDANIS)
chofer_2  WORKING  584222560723@c.us   (EVERT)
```

### El QR estaba roto — se resolvió con pairing code

El QR fallaba con `window.require(...).Cmd.refreshQR is not a function`:
WhatsApp Web `2.3000.1048901417` ya no expone esa función, el código expira en
~40 s y el celular responde **"NO SE PUDO VINCULAR DISPOSITIVO"**.

Se descartó desfase de reloj (host y contenedor sincronizados en UTC).

Solución: **código de emparejamiento**, ligado al número de teléfono.
Ventaja decisiva para la regla crítica: si el código se genera para
`584222560722`, **solo ese número** puede completar la vinculación. El QR no
daba esa garantía — cualquiera podía escanearlo.

---

## 2. WAHA blindado (docker-compose + auto-reconnect)

**Riesgo evitado:** el volumen montado `/mnt/ssd_trabajo/waha` estaba **vacío**.
Las credenciales vivían en `/app/.sessions/webjs/` dentro del contenedor.
`docker rm` tal como estaba planteado habría destruido ambos vínculos y habría
que volver a llamar a los choferes.

Secuencia aplicada: backup 104 MB → montar la ruta correcta → migrar.

Pruebas destructivas verificadas:
- `docker rm` + `compose up -d` → ambos siguen WORKING.
- `docker restart` → reconectan solas.
- Sesión detenida a propósito → el health check la recuperó.

Cron instalado cada 15 min. Fix posterior: el healthcheck marcaba `unhealthy`
porque `/api/version` exige `X-Api-Key` y el `wget` no la mandaba (401).

---

## 3. Dispatcher bot + DT-01 cerrada

- Nombre, descripción y comandos actualizados en `@DespachoH2O_bot`.
- **`/plan` no existía** en el código; se registraron los comandos reales más
  `/health`. Anunciar `/plan` habría dejado un comando muerto en el menú.
- **DT-01 desbloqueada:** `vehicles.telegram_chat_id` tenía `111111`/`222222`
  (basura de fixtures de test) y el query de registro exige `IS NULL`, así que
  ningún chofer podía registrarse. Limpiado con backup de DB.

Estado final:
```
YORDANIS  8806724603
EVERT     8987840684
```

---

## 4. mobile-mcp + endurecimiento de celulares

mobile-mcp operativo con 33 herramientas. Dos desvíos corregidos con evidencia:
- Puerto **3010**, no 3001 (ese lo ocupa `hermes_grafana`).
- El transporte por defecto es **stdio**; el HTTP requiere `--listen`.
- Faltaba el paquete `mcp` en Python — sin él Hermes ignora la config MCP
  en silencio.

Ambos celulares (SP_6300, Android 15) endurecidos, con verificación releyendo
del equipo: GPS alta precisión, brillo 255, apagado 10 min, y WhatsApp /
Telegram / Chrome activas. **Sin instalar ni desinstalar nada**, según la
restricción. Facebook/Instagram/TikTok no estaban instalados (equipos limpios).

Detalle útil: el equipo 2 apareció `unauthorized`; se resolvió esperando a que
el Líder aceptara el diálogo en pantalla, no reiniciando servicios.

---

## 5. Auditoría completa de deudas (solo lectura)

Barrido en vivo sin tocar código ni DB. Resultado en
`docs/ROADMAP_VIVO_ACTUALIZADO.md`.

### Cerradas con evidencia
DT-01 (chat_ids reales), D10 SOUL FASE 3 (`auto_activation_ready() = True`),
DT-13 OpenNotebook, DT-15 token Meta.

### Nuevas — lo que hay que atacar primero

| ID | Hallazgo | Prioridad |
|---|---|---|
| **DT-32** | cloudflared en crash-loop: **95 caídas/hora**, 502 intermitente en el health público mientras el bridge local responde 200 | 🔴 P0 |
| **DT-33** | 5 tests rompen la **colección** de pytest → sin `--ignore` la suite ejecuta **0**. Con `--ignore`: 1005 passed, 60% cobertura | 🔴 P0 |
| **DT-34** | Redis `DBSIZE = 0` (D6 reabierta): servicio activo pero capa Buffer vacía | 🟠 P1 |
| **DT-35** | Solo **4 de 363** clientes con `client_type`; el auto-routing Nivel 1 está implementado pero inoperante | 🟡 P2 |

### Correcciones al documento anterior
- Los 11 comandos de seguridad **existen** pero no están en `setMyCommands` →
  no aparecen en el menú (DT-31 parcial). El bot tiene 15 comandos, no 17.
- Métricas reales: 1005 passed / 60% cobertura (el doc decía 580/580 y 36%).

---

## Estado al cierre (verificado)

| Servicio | Estado |
|---|---|
| WAHA (compose) | Up, healthy, 2/2 WORKING |
| Auto-reconnect | cron 15 min activo |
| Dispatcher bot | active, choferes registrados |
| mobile-mcp | active, 33 herramientas |
| Whatsscanbot | active |
| OSRM | HTTP 200 |
| Celulares | 2/2 endurecidos |

## Pendiente para la próxima jornada

1. **DT-32** — estabilizar cloudflared (P0).
2. **DT-33** — reparar los 5 tests que abortan la colección (P0).
3. **DT-34** — diagnosticar Redis vacío (P1).
4. **DT-31** — registrar los 11 comandos de seguridad en el menú (30 min).
5. **DT-35** — clasificar los 363 clientes (**requiere criterio del Líder**).

## Lección de la jornada

Dos veces el plan del Líder difería de la realidad y verificarlo evitó un
daño serio:

1. El volumen de persistencia de WAHA no era el correcto → sin el backup, se
   perdían ambos números vinculados.
2. El QR de WAHA está roto en este build → insistir habría quemado el tiempo
   de los choferes sin resultado.

En ambos casos la evidencia en vivo valió más que el informe previo.

---

*Buenas noches, Líder. Todo quedó operativo y documentado. 💧*
