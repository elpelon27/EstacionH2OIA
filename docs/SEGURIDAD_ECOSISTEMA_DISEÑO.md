# Diseño de Seguridad Estructural del Ecosistema — FASE 0

**Fecha:** 2026-09-23 · **Autor:** Prometeo (por directiva 💧) · **Estado:** Diseño (sin tocar producción)

## Resumen del plan

Endurecimiento estructural del ecosistema Estación H2O en 9 fases (0-8), sumando capas de
seguridad sin reemplazar la malla existente ("menos es más"). Regla de oro de acceso: solo
números +58; internacionales → rebote + lista negra única. Bloqueos: 1ra ofensa 1h silencio,
2da ofensa <24h → permanente, sin apelación. Operador humano: Líder (Luis Martinez) vía
Telegram @Skynet_27_bot. Ataques coordinados: límites globales 29/min, 100/h, 700/día,
50+números nuevos/10min → observación; 700/día → lockdown (solo responden conocidos).

## Puntos de entrada y estado

| Punto | Estado | Protección actual |
|---|---|---|
| Valentina (WhatsApp) | Público | Menú + malla básica (sin rate limiting numérico) |
| Webhook Meta | Público | HMAC + fix _validate_meta_payload (NO TOCAR) |
| Webhook R4 | Público | IP whitelist 4 IPs banco (NO TOCAR) |
| @Skynet_27_bot | Privado | chat_id 1663148211 (operador) |
| @DespachoH2O_bot | Público | Solo choferes |
| OpenNotebook/Grafana/Odoo/Dify | Local | No expuestos |
| Puerto 8000 | ufw DENY | Protegido |
| IPv4 156.255.155.24 | Expuesta | ufw activo |

## Arquitectura de seguridad por capas (diagrama)

```
                        INTERNET (156.255.155.24, ufw activo)
                                     │
              ┌──────────────────────┼───────────────────────┐
              ▼                      ▼                       ▼
      [L1 Perímetro ufw]      [Webhook Meta]            [Webhook R4]
      solo puertos del        HMAC + _validate_meta     IP whitelist (4 IPs)
      bridge/servicios        (SELLADO - no tocar)      (SELLADO - no tocar)
              │                      │                       │
              └──────────┬───────────┘                       │
                         ▼                                   │
              ┌───────────────────────┐                      │
              │  VALENTINA BRIDGE      │◄─────────────────────┘
              │  (FastAPI, prod)       │
              └──────────┬────────────┘
                         ▼  cada mensaje entrante pasa por:
         ┌───────────────────────────────────────────────┐
         │ [L2 RATE LIMITER] scripts/security/rate_limiter.py
         │   • es_numero_venezolano (+58 o rebote+blacklist)
         │   • contar_mensajes_recientes (3 en 60s → aviso+1h)
         │   • blacklist ÚNICA (tabla blacklist_phone)
         │   • offenses_log (2 en <24h → permanente)     │
         ├───────────────────────────────────────────────┤
         │ [L3 ATTACK DETECTOR] scripts/security/attack_detector.py
         │   • 29/min 100/h 700/día (globales)
         │   • 50+ números nuevos/10min → observación
         │   • spam idéntico/timing exacto → bloqueo auto
         │   • 700/día → LOCKDOWN (solo conocidos)      │
         ├───────────────────────────────────────────────┤
         │ [L4 GEOCERCA] scripts/security/geofence.py
         │   • polígono GeoJSON (ray casting, sin deps)
         │   • fuera → "no atendemos su zona" + tabla
         │     future_zone_customers (NO va al audit log) │
         ├───────────────────────────────────────────────┤
         │ [L5 AUDIT] scripts/security/audit_logger.py
         │   • security_audit_log (retención 3 años)
         │   • eventos: entrante/bloqueo/observación/ataque/
         │     decisión operador/pago/intento fallido     │
         └───────────────┬───────────────────────────────┘
                         ▼
         ┌───────────────────────────────────────────────┐
         │ [L6 OPERADOR] @Skynet_27_bot (Telegram)       │
         │   /blacklist_add /blacklist_remove /block     │
         │   /unblock /observe /credit_client            │
         │   /cliente_info /ataque_detectado              │
         │   /lockdown_status /lockdown_release /stats   │
         │   + notificaciones automáticas                │
         └───────────────────────────────────────────────┘
                         ▼
         [L7 DATOS] dispatch.db (clients.phone_hash ya existe)
           + FASE 6: hash en fs_pedidos/fs_pagos/whatsapp_contacts
           + conversations.db cifrada (age/gpg, clave en .env chmod 600)
                     ▼
         [L8 TEST OFFENSIVO] Strix — SEMANAL, AMBIENTE AISLADO
           (nunca producción; si no hay ambiente → PENDIENTE LÍDER)
                     ▼
         [L9 GOBERNANZA] ECC rules — skills de Hermes
           (reglas globales: rate limit/blacklist/geocerca/HMAC/
            IP whitelist/Ollama-no-técnico/snapshot+push+rollback)
```

## Integración ECC (FASE 7)

ECC (affaan-m/ecc, clonado en `external_repos/ecc`) es un framework de rules (markdown
scoped por paths) + hooks (event-driven, PreToolUse/PostToolUse) + security scanning
(bandit/greptile). Para nuestro ecosistema:
- **No instalar ECC como harness completo** (es un OS de agente para Claude Code; instalarlo
  reemplazaría flujos → viola "no reemplazar la malla"). DECISIÓN: integrar como SKILL de
  Hermes que curador carga — las reglas críticas se copian a un skill propio con paths
  adaptados a este repo.
- Rules aplicables (de rules/common + rules/python): security.md (gestión de secretos, bandit),
  hooks.md (patrones), code-review.md. Las específicas de Angular/Rust/etc se descartan
  ("menos es más").
- Security scanning: bandit sobre scripts/ + revisión de secretos en .env (ya cubierto por
  scanner del repo, se suma bandit como capa).
- Los hooks de ECC (memoria persistente, quality gates) NO se instalan — el repo ya tiene
  git-hooks y auto-snapshot propios. SUMAR, no reemplazar.

## Integración Strix (FASE 8)

Strix (usestrix/strix, clonado en `external_repos/strix`) es un agente de pentesting con AI
(uv/pip `strix-agent`) que corre exploits con PoCs. DECISIONES:
- Requiere API key de LLM para operar (STRIX_API_KEY o similar) y un TARGET. PENDIENTE LÍDER:
  confirmar qué LLM/key usar para Strix y crear el ambiente de pruebas aislado.
- Sin ambiente aislado NO se corre (decisión segura del Líder). Documentado como PENDIENTE
  en SEGURIDAD_ECOSISTEMA_PROGRESO.md.
- Cron semanal (domingo 03:00) con guard: solo ejecuta si existe el archivo
  `config/strix_targets.env` con STRIX_ENABLED=1 y targets del ambiente de pruebas.

## Fases de implementación

- FASE 0 (esta): investigación + este documento.
- FASE 1: rate_limiter.py + blacklist_phone + offenses_log + tests. DB: security.db (NUEVA,
  aislada — no tocar dispatch.db/conversations.db en producción; integración por el bridge
  la hace el Líder o yo con checkpoint verificado).
- FASE 2: geofence.py + geofence_polygon + future_zone_customers (en security.db).
- FASE 3: attack_detector.py + métricas + lockdown (tabla security_state en security.db).
- FASE 4: comandos del bot operador — MÓDULO NUEVO scripts/prometeo/security_commands.py
  con guard chat_id 1663148211, importado desde prometeo.py SIN modificar su lógica existente
  (sumar handlers). El bot telegram-bot.service ya existe (kill switch + alerts).
- FASE 5: audit_logger.py + security_audit_log (en security.db). Retención 3 años.
- FASE 6: hash de teléfonos en fs_pedidos/fs_pagos (conversations.db) y whatsapp_contacts
  (whatsapp_bot.db) + cifrado conversations.db. ⚠ PENDIENTE LÍDER: el cifrado de
  conversations.db en caliente afecta el bridge activo (el servicio la tiene abierta).
  Se planifica con checkpoint/backup por tabla, en ventana de mantenimiento. El hash de
  columnas teléfono en claro REQUIERE decidir qué hace el runtime con teléfono en claro
  (runtime puede hashear para comparar; pero pedidos nuevos... el bridge escribe teléfono
  en claro hoy). MARCAR: preguntas al final.
- FASE 7: skill Hermes "ecc-rules" con reglas globales del ecosistema.
- FASE 8: Strix — documentado PENDIENTE si no hay ambiente aislado.

## Decisiones de ingeniería (con razones)

1. **security.db SQLite nueva y aislada** para blacklist/ofensas/geocerca/audit — evita
   contaminar DBs de producción y permite testear con backups. Integración = solo lectura
   por el bridge.
2. **Ray casting puro (sin shapely)** — cero dependencias nuevas, algoritmo probado.
3. **Reglas como skill de Hermes, no instalación completa de ECC** — "sumar, no reemplazar".
4. **Strix con guard de habilitación** — imposible correr contra producción por accidente.
5. **Comandos de operador como módulo aparte** — prometeo.py queda intacto, handlers nuevos
   se registran al importar (monkey-patch seguro con guard de idempotencia).
6. **No se guardan históricos de mensajes** (regla del Líder) — el audit log solo registra
   eventos con metadatos (phone/ip/tipo/acción), nunca contenido del mensaje.
7. **sudo no disponible sin password** — todo corre como usuario skynet; la clave de
   cifrado vive en .env chmod 600 (PENDIENTE LÍDER si quiere protección sudo-only).

## DUDAS / DECISIONES PENDIENTES DEL LÍDER (marcadas)

1. **FASE 6 hashing en caliente:** fs_pedidos/fs_pagos reciben escrituras del bridge EN
   PRODUCCIÓN ahora mismo. ¿Hashear columnas existentes (migración) y adaptar el bridge
   para escribir hashes, o esperar ventana de mantenimiento? El bridge es zona SELLADA.
   → PROPUESTA: migrar datos históricos + agregar columnas *_hash nuevas, dejar las
   columnas en claro SIN borrar hasta que Líder ordene purga. Esperar confirmación.
2. **FASE 4 registro de handlers en prometeo.py:** requiere 1 línea de import/modificación
   en el archivo vivo del bot operador (telegram-bot.service). Zona sensible pero el
   Líder pidió explícitamente extender @Skynet_27_bot. → PROPUESTA: módulo nuevo importado;
   si prometeo.py no tiene punto de extensión, agrego un import condicional mínimo con
   checkpoint y rollback verificado.
3. **Strix:** ¿crear ambiente de pruebas aislado (docker-compose espejo) ahora o dejar
   PENDIENTE hasta que el Líder lo decida? → Por defecto: PENDIENTE documentado.
4. **Geocerca inicial:** el polígono real de zona de atención lo pasa el Líder (referencias).
   Se crea con polígono placeholder desactivado (is_active=0) para no rechazar clientes reales
   hasta que lleguen las referencias.
