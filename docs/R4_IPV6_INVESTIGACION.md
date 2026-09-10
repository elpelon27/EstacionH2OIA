---
title: Investigación — Exigencia IPv6 en R4 Conecta
---

# Investigación: ¿De dónde viene la "exigencia de IPv6" en R4?

**Última actualización:** 2026-09-09
**Autor:** Prometeo (orquestado por Líder, modo R4)
**Fuente:** Verificación en vivo sobre `feat/odoo-r4-integration` @ b6633a1 (2026-09-09)
**Repo:** github.com/elpelon27/EstacionH2OIA

## Contexto

El banco R4 Conecta confirmó al Líder (2026-09-09):
- ✅ Puede operar con SOLO IPv4 (sin IPv6)
- ✅ La IPv4 fija del comercio `156.255.155.24` ya está en su whitelist
- ❌ La exigencia de IPv6 no era del banco
- Hipótesis del Líder: viene de algún componente Python/sudo nuestro

## Archivos analizados

| Archivo | Resultado |
|---|---|
| `src/integrations/r4/client.py` (880 líneas) | Única referencia a "IPv6" en todo el código R4 |
| `src/integrations/r4/webhooks.py` (1033 líneas) | Validación de IP entrante por string-match, sin familia IP |
| `src/integrations/r4/hmac_auth.py`, `codigos.py`, `__init__.py` | Sin referencias IPv6 |
| `api/bridge.py` | Solo `get_remote_address` (slowapi, rate-limit) y check `127.0.0.1`/`::1`/`172.19.` — sin exigencia IPv6 |
| `src/security/`, `core/` | Cero referencias a IPv6/AF_INET6/inet6 |
| `config/.env` / `config/.env.example` | `R4_WEBHOOK_ALLOWED_IPS` contiene SOLO IPv4 del banco; sin entradas IPv6 |
| `api/start_bridge.sh` | uvicorn `--host 0.0.0.0` (IPv4-only bind, correcto) |
| `valentina-bridge.service` | Sin directivas IPv6; `ss -tlnp` confirma bind `0.0.0.0:8000` (IPv4 only) |
| `cloudflared` (tunnel) | Sin config IPv6; no se tocó (regla del Líder) |
| `sudo` | Cero referencias a sudo/ipv6 en el código R4 |

## Hallazgos exactos

1. **client.py:188-224** — `_IPv4Transport(httpx.AsyncHTTPTransport)`: transporte que
   FUERZA resolución IPv4 (solo registros A) para hosts `*.mibanco.com.ve` en el
   EGRESS (nuestro cliente → banco). Es exactamente lo CONTRARIO a una exigencia
   de IPv6: garantiza que salimos SIEMPRE por la IPv4 whitelisted. Introducido en
   commit `ff17418` como hardening.
   - Docstring (líneas 191-192) dice: "si la peticion sale por IPv6 dinamico el
     banco responde 401 code 108". **Esta afirmación fue REFUTADA por verificación
     en vivo el 2026-09-01** (references/ipv4-egress-diagnosis.md): el egress
     por defecto YA salía por `156.255.155.24`, y el 401/108 persistía sobre IPv4
     pura — el 108 era un problema de credencial/endpoint banco-side.
2. **webhooks.py:226-238 (`verify_ip_whitelist`)** — la IP entrante del banco se
   valida con **comparación de strings** contra `allowed_ips` (set de strings del
   `.env`), tomando primero `X-Forwarded-For` si existe. No usa `ipaddress`, no
   parsea familias, no exige IPv6. IPv4 y IPv6 entrantes se tratan igual.
3. **webhooks.py:43-51** — `R4_WEBHOOK_ALLOWED_IPS` en `.env` contiene las 3 IPv4
   del banco (`45.175.213.98`, `200.199.249.3`, `204.199.249.3`). Sin IPv6. La IPv4
   `156.255.155.24` del Líder NO está ni necesita estar: esa es la IP de EGRESS
   (nosotros → banco), no de origen de los webhooks entrantes.
4. ** Ningún middleware bloquea IPv4.** uvicorn escucha en `0.0.0.0:8000`
   (IPv4-only). Todo el path Cloudflare → uvicorn funciona sobre IPv4.

## Causa raíz probable

**No existe ninguna exigencia de IPv6 en nuestra arquitectura.** La confusión
proviene del docstring de `_IPv4Transport` (client.py:191-192), que afirma que "el
banco rechaza IPv6 con 108" — un comentario HIPOTÉTICO de la investigación del
2026-09-01 que la verificación en vivo refutó. Ese comentario, leído al revés
("IPv6 matters"), pudo interpretarse como que IPv6 era necesaria o problemática.
El servidor además tiene IPv6 global dinámica (`2803:d700:...` en enp0s31f6),
pero el egress real hacia el banco ya era IPv4.

Caso aplicable: **CASO D parcial** — la exigencia no es del estándar R4 ni nuestra;
simplemente NO EXISTE. No hay nada funcional que remover.

## Solución propuesta (mínima, sin cambio funcional)

1. Corregir el docstring/comentarios de `_IPv4Transport` (client.py:188-224):
   reexplicarlo como hardening determinista de egress ("garantiza salir por la
   IPv4 whitelisted; banco confirmó 2026-09-09 que IPv4 sola es suficiente"),
   en vez de la afirmación refutada "banco rechaza IPv6 con 108". Cero cambio
   de comportamiento — el transporte se mantiene.
2. No tocar `verify_ip_whitelist`, `.env`, bridge, tunnel ni Meta (reglas).
3. Verificación en vivo del webhook con IPv4 del banco (Fase 3).

## Conclusión

La arquitectura YA opera con IPv4 sola (bind 0.0.0.0, whitelist IPv4-only, egress
forzado IPv4). Confirmación del banco es consistente con lo que ya existe. Solo
queda corregir la documentación engañosa del docstring.

💧
## FASE 3 — Test end-to-end (2026-09-09, en vivo)

- POST /webhook/r4/consulta con X-Forwarded-For=45.175.213.98 + Authorization UUID:
  → **200 {"status": false}** (validación IP + auth OK, negocio procesa)
- POST con IP no-whitelist (8.8.8.8): → **403 "IP no autorizada"** ✅
- POST sin Authorization con IP del banco: → 401 "Authorization header requerido" ✅
- Logs `journalctl -u valentina-bridge` confirman cada evento (IP autorizada/rechazada).
- Nota: `/webhook/r4` raíz no existe (404); las rutas son `/consulta` y `/notifica`.
- Interferente durante el test: cloudflared se reinició (22:17) causando 502
  transitorios; tras re-registrar conexiones, el flujo tunnel→bridge dio 200.
- Conclusión: la cadena webhook R4 opera 100% sobre IPv4. IPv6 no es necesaria.
