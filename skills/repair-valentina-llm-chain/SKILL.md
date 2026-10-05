---
name: repair-valentina-llm-chain
description: Cuando Valentina responde con "dificultades técnicas" (fallback), Dify no responde, o contenedores docker no pueden alcanzar servicios del host (Ollama, etc.) después de un restart de docker o migración de runtime. Diagnóstico y fix completo de la cadena LLM: Ollama → plugin_daemon → Dify API → valentina-bridge → WAHA → WhatsApp.
---

# Repair Valentina LLM Chain

## Incidente origen (2026-10-05, DT-42/DT-43)
Tras migración de containerd root (DT-39) + restart de docker, los bridges
docker se recrearon con subnets nuevas. UFW tenía INPUT policy DROP y ninguna
regla cubría las subnets de las redes docker nuevas → todo paquete de un
contenedor hacia el host era bloqueado. El plugin_daemon de Dify no alcanzaba
Ollama (11434) → la app "Valentina" en Dify fallaba → el bridge caía al
mensaje "disculpe tengo dificultades técnicas".

## Cuándo aplicar este skill

Aplicar cuando se presente CUALQUIERA de estos síntomas:

1. **Valentina manda "disculpe tengo dificultades técnicas"** por WhatsApp
   (fallback del bridge cuando la cadena LLM falla)
2. **skynet_27_bot reporta "Dify no responde"**
3. **Contenedores docker no pueden alcanzar servicios del host** (Ollama en
   11434, etc.) después de:
   - `systemctl restart docker`
   - Migración de containerd root
   - Reinicio del servidor
   - Cualquier operación que recrea bridges docker
4. **Errores en logs Dify** del tipo:
   - `connect ECONNREFUSED 172.17.0.1:11434` (plugin_daemon → Ollama)
   - `fetch failed` / `EAI_AGAIN` en llamadas salientes
   - Timeouts hacia `http://172.17.0.1:11434` o `http://host.docker.internal:11434`

## Diagnóstico paso a paso (ejecutar EN ORDEN, sin saltos)

### Paso 1 — Confirmar que Ollama vive en el host

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:11434/api/tags
# Esperado: 200. Si falla: systemctl status ollama (OLLAMA_HOST=0.0.0.0:11434)
```

### Paso 2 — Identificar las subnets REALES de las redes docker

```bash
docker ps -q | xargs docker inspect --format \
  '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}={{$v.IPAddress}} {{end}}'
docker network ls | tail -n +2
# Para cada red usada: docker network inspect <red> --format \
#   '{{range .IPAM.Config}}subnet={{.Subnet}} gateway={{.Gateway}}{{end}}'
```

### Paso 3 — Verificar alcance desde DENTRO del contenedor (prueba real)

```bash
docker exec docker-plugin_daemon-1 curl -s -o /dev/null \
  -w "%{http_code}\n" --max-time 5 http://172.17.0.1:11434/api/tags
# Esperado: 200. Si es timeout/connection refused → UFW está bloqueando.
# NOTA: el sh interno de plugin_daemon NO soporta /dev/tcp — usar curl SIEMPRE.
# Si el contenedor no tiene curl ni wget: docker cp un curl estático o
# probar desde otro contenedor de la MISMA red.
```

### Paso 4 — Verificar reglas UFW actuales

```bash
sudo -S -p '' ufw status | grep 11434
# Estado saludable (6 reglas, una por subnet docker):
#   11434/tcp ALLOW 172.17.0.0/16   # Ollama from bridge
#   11434/tcp ALLOW 172.18.0.0/16   # Ollama from odoo_default
#   11434/tcp ALLOW 172.19.0.0/16   # Ollama from infra_hermes_net
#   11434/tcp ALLOW 172.20.0.0/16   # Ollama from docker_default (Dify)
#   11434/tcp ALLOW 172.21.0.0/16   # Ollama from docker_ssrf_proxy_network
#   11434/tcp ALLOW 172.22.0.0/16   # Ollama from waha_default
```

## Fix (solo si el Paso 3 dio timeout/blocked)

### Paso 5 — Agregar regla UFW por CADA subnet de red docker

```bash
sudo -S -p '' ufw allow from 172.17.0.0/16 to any port 11434 proto tcp \
  comment "Ollama from bridge"
# Repetir por cada subnet del Paso 2 (172.18, 172.19, 172.20, 172.21, 172.22...)
# Las subnets de docker suben secuenciales: si hay 7 redes, llegarán a 172.23
```

### Paso 6 — Reiniciar SOLO valentina-bridge (NOPASSWD, no requiere password)

```bash
sudo -S -p '' -n /bin/systemctl restart valentina-bridge
# Si pide contraseña: usar systemctl restart valentina-bridge con sudo normal
```

### Paso 7 — Verificar la cadena COMPLETA de punta a punta

```bash
# Eslabón 1: ollama
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:11434/api/tags          # 200
# Eslabón 2: plugin_daemon → ollama (el que se rompía)
docker exec docker-plugin_daemon-1 curl -s -o /dev/null -w "%{http_code}\n" \
  --max-time 5 http://172.17.0.1:11434/api/tags                                   # 200
# Eslabón 3: dify endpoint (401 = vivo, pide credencial)
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost/v1/chat-messages \
  -H "Content-Type: application/json" -d '{}'                                     # 401
# Eslabón 4: valentina-bridge
systemctl is-active valentina-bridge                                              # active
# Eslabón 5: waha (sesiones de choferes)
docker inspect -f "{{.State.Health.Status}}" waha                                 # healthy
# Eslabón 6 (prueba humana): mandar msg a Valentina por WhatsApp → debe responder
```

## Criterio de éxito
Los 6 eslabones del Paso 7 en verde + respuesta real de Valentina por WhatsApp.
Si el eslabón 2 sigue en rojo tras las reglas UFW: verificar que la subnet del
Paso 2 coincide con la regla agregada (subnet nueva = regla nueva).

## Prevención (para el futuro)

1. **Después de CUALQUIER operación que toque redes docker** (restart de docker,
   migración de containerd, docker network create/prune), correr el Paso 2 y
   comparar subnets contra `sudo ufw status | grep 11434`.
2. **Alternativa estructural (pendiente de decisión del Líder):** en vez de
   reglas por subnet, `sudo ufw allow from 172.16.0.0/12 to any port 11434`
   cubre TODO el rango docker privado (172.16–172.31) con una sola regla.
   Más robusto a redes nuevas; menos granular. NO aplicar sin autorización.
3. **Ollama ya escucha en 0.0.0.0:11434** (verificado): el problema siempre
   fue el firewall, no el bind.

## Errores comunes (leer antes de diagnosticar)

- **NO usar /dev/tcp dentro de plugin_daemon**: su sh no lo soporta y da
  "BLOCKED" falso. Probar SIEMPRE con curl real (paso 3).
- **401 en Dify es SALUD**: significa endpoint vivo exigiendo credencial.
  No es error.
- **404 en WAHA /healthz**: esta versión no expone ese endpoint. Usar
  `docker inspect waha` (health) y `GET /api/sessions` (401 sin key).
- **El mensaje "disculpe tengo dificultades técnicas" es del BRIDGE**, no de
  Dify ni de Ollama: es el fallback cuando _call_dify() falla. La causa raíz
  puede estar en cualquier eslabón — por eso se diagnostica en orden.

## Evidencia del incidente original (2026-10-05)

- UFW INPUT policy DROP + 0 reglas para subnets docker → todo bloqueado
- Fix: 6 reglas `ufw allow from 172.1{7..22}.0.0/16 to any port 11434`
- Post-fix verificado: plugin_daemon→Ollama HTTP 200, bridge active,
  Dify 401, WAHA healthy, 2/2 sesiones choferes WORKING
- Registrado como DT-42 (incidente) y DT-43 (fix) en worklog

## Historial
- 2026-10-05: creado tras incidente post-migración containerd (DT-39).
  Evidencia verificada en vivo, todos los eslabones probados con comandos.
