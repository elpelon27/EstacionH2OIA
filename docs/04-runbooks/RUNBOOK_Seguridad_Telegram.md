# RUNBOOK: Seguridad Telegram — Bot Operador @Skynet_27_bot

**Fecha:** 2026-09-23 · **Validado en producción por el Líder** 💧
**Servicio:** telegram-bot.service · **Acceso:** SOLO chat_id del Líder (TELEGRAM_CHAT_ID=1663148211)
**Módulos backend:** scripts/security/{rate_limiter, attack_detector, geofence, audit_logger}.py
**DB:** data/security.db (SQLite)

El bot operador es el punto de control humano del sistema de seguridad del ecosistema.
Todo comando de un chat_id no autorizado es ignorado y queda registrado como
`intento_fallo_acceso` en el audit log.

## Los 11 comandos

### /lockdown_status
Muestra si el modo lockdown está activo, el motivo, y los volúmenes actuales
(mensajes por minuto/hora/día contra los límites 29/100/700).
```
/lockdown_status
→ 🔒 Lockdown: inactivo
  📊 Volúmenes: 2/min · 15/hora · 88/día (límites 29/100/700)
```
**Cuándo usar:** chequeo rápido del estado del sistema, o tras una alerta de ataque.

### /lockdown_release
Saca el sistema del modo lockdown (solo si el operador lo decide).
```
/lockdown_release
→ 🔓 Lockdown liberado por el operador. Nota: si el volumen
  diario sigue ≥700, se re-activará automáticamente.
```
**Cuándo usar:** tras un lockdown por límite diario, cuando ya se revisaron las
conversaciones y se decide seguir atendiendo. OJO: se re-activa solo si el volumen
sigue alto — es protección automática, no un bug.

### /blacklist_add <phone> <reason> [permanent]
Agrega un número a la blacklist única. Con la palabra `permanent` es bloqueo
permanente; sin ella, temporal de 1 hora.
```
/blacklist_add +584141234567 cliente abusivo permanent
→ 🔒 +584141234567 agregado a blacklist (permanente).
  Razón: cliente abusivo
/blacklist_add +584241234567 molestando
→ 🔒 +584241234567 agregado a blacklist (temporal 1h).
```

### /blacklist_remove <phone>
Saca un número de la blacklist (desbloqueo total, incluidos permanentes).
```
/blacklist_remove +584141234567
→ ✅ blacklist limpiada para 584141234567
```

### /block <phone>
Silencio manual de 1 hora (equivale a 1ra ofensa). No es permanente.
```
/block +584161234567
→ 🔇 +584161234567 silenciado 1h (bloqueo manual).
```

### /unblock <phone>
Elimina el bloqueo temporal o permanente (alias de blacklist_remove en efecto).
```
/unblock +584161234567
→ 🔓 desbloqueado.
```

### /observe <phone>
Marca un número como "bajo observación" — queda en el audit log para seguimiento
sin bloquear.
```
/observe +584121234567
→ 👁 +584121234567 bajo observación.
```
**Cuándo usar:** comportamiento sospechoso que no llega a ofensa (loops de menú,
varias conversaciones al día).

### /credit_client <phone>
Marca al número como cliente con crédito/conocido. Efectos: (1) el pedido sin
pagar NO cuenta como ofensa (regla del Líder: cliente que pagó aunque ignoró el
menú no se castiga); (2) en lockdown, los números conocidos SIGUEN siendo atendidos.
```
/credit_client +584121234567
→ 💳 +584121234567 marcado como cliente con crédito (conocido).
```

### /cliente_info <phone>
Historial completo del número: estado en blacklist, ofensas en 24h, si es
conocido/registrado, y los últimos 10 eventos de auditoría.
```
/cliente_info +584121234567
→ 📱 Cliente +584121234567
  ✅ No está en blacklist
  ⚖️ Ofensas (24h): 0
  📌 Conocido/registrado: no
  🗂 Últimos 0 eventos de auditoría:
```
**Cuándo usar:** antes de decidir un bloqueo, o cuando un cliente reclama.

### /ataque_detectado
Lista los últimos 15 eventos de ataque registrados (límites golpeados, oleadas
de números nuevos, spam multi-número, activaciones de lockdown).
```
/ataque_detectado
→ 🚨 Ataques recientes (3):
  • 2026-09-23 09:14:02 limite_minuto → 29
  • 2026-09-23 09:15:10 numeros_nuevos_oleada → 52
  • 2026-09-23 09:31:44 spam_programado → 8 números
```

### /stats
Estadísticas de las últimas 24h: volúmenes por ventana, números nuevos,
bloqueos, observaciones, ataques, pagos confirmados, decisiones del operador,
intentos fallidos de acceso, y clientes fuera de zona (guardados aparte).
```
/stats
→ 📊 ESTADÍSTICAS (24h)
  • Mensajes: 3/min · 22/h · 210/día
  • Números nuevos (10min): 2
  • Bloqueos: 1
  • ...
```
**Cuándo usar:** revisión diaria del estado de la seguridad.

## Flujo recomendado ante un incidente

1. **Alerta llega** (ataque detectado / límites) → `/lockdown_status` para ver el panorama.
2. Si hay ataque masivo → el sistema entra en lockdown solo (700/día) o puedes
   bloquear números sueltos con `/blacklist_add ... permanent`.
3. Revisa `/ataque_detectado` y `/stats` para dimensionar.
4. Caso gris (gente mayor, cliente confundido): `/observe` y responderle vía el
   canal correspondiente — NO bloquear si pagó (`/credit_client` primero si aplica).
5. Todo queda auditado (retención 3 años) para revisión posterior.

## Notas técnicas

- Los comandos corren en el servicio telegram-bot.service (root). Reinicio tras
  cambios de código: `sudo systemctl restart telegram-bot`.
- DB aislada: data/security.db (no toca dispatch.db/conversations.db).
- Guard: chat_id autorizado vía TELEGRAM_CHAT_ID en config/.env.
- Todo comando (autorizado o no) genera eventos en security_audit_log.
