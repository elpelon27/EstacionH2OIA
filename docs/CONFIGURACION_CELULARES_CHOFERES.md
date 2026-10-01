# Configuración de Celulares de Choferes (ADB + mobile-mcp)

**Estado al 2026-10-01:** ⏸️ **PENDIENTE** — hay un celular conectado por USB
(Unisoc, serial `SP6300000000016611`) pero está en **modo PTP**, así que ADB
no lo ve. Falta activar Depuración USB y cambiar a MTP.
Detalle completo en `docs/ENDURECIMIENTO_CELULARES.md`.

mobile-mcp quedó **instalado y operativo** (33 herramientas, servicio systemd
activo en `127.0.0.1:3010`). Solo falta el ajuste del teléfono.

---

## Qué falta (acción del Líder)

1. Conectar el celular del chofer por cable USB al servidor.
2. En el celular: **Activar depuración USB**
   (Ajustes → Acerca del teléfono → tocar "Número de compilación" 7 veces
   → Ajustes → Opciones de desarrollador → Depuración USB).
3. En el celular, cuando aparezca el diálogo "¿Permitir depuración USB?",
   marcar **"Permitir siempre desde este equipo"** y aceptar.
4. Decir: **"Configurar equipo 1"** (Yordanis) o **"Configurar equipo 2"** (Evert).

Si el celular se conecta pero aparece como `unauthorized`, es el paso 3:
no se aceptó la huella RSA del servidor.

---

## Comandos de verificación

```bash
# ¿Hay equipos conectados?
adb devices -l
#   → vacío            : no hay nada conectado
#   → XXXXX unauthorized: falta aceptar el diálogo en el celular
#   → XXXXX device     : listo para configurar

# Ver modelo / Android de cada equipo
adb devices -l | awk 'NR>1 && $2=="device" {print $1}'
```

---

## Qué hace `scripts/setup_phone_auto.sh <serial> <vehicle_id>`

Cuando conectes un equipo, este script:

1. Verifica que ADB vea el dispositivo y esté autorizado.
2. Obtiene modelo, versión de Android y operador.
3. Instala/verifica apps necesarias (WhatsApp, navegador).
4. Desactiva el bloqueo de pantalla mientras está cargando
   (`stay_on_while_plugged_in`), para que la pantalla no se apague en ruta.
5. Ajusta el brillo y el tiempo de apagado de pantalla.
6. Registra el equipo en `data/dispatch.db` contra su `vehicle_id`.
7. Reporta por Telegram qué quedó configurado.

```bash
./scripts/setup_phone_auto.sh <serial> 1   # Yordanis  (Triciclo 1, +584222560722)
./scripts/setup_phone_auto.sh <serial> 2   # Evert     (Triciclo 2, +584222560723)
```

---

## Correspondencia equipo ↔ chofer

| vehicle_id | Chofer   | Vehículo   | WhatsApp         | Sesión WAHA |
|---|---|---|---|---|
| 1          | YORDANIS | Triciclo 1 | +584222560722    | `chofer_1`  |
| 2          | EVERT    | Triciclo 2 | +584222560723    | `chofer_2`  |

⚠️ **Regla crítica del Líder:** el número que avisa la llegada debe ser el
mismo que envía el PDF del recibo. Esa consistencia ya está garantizada en
`waha_client.py` por `vehicle_id` — el celular físico solo es el hardware
donde corre WhatsApp, no cambia qué número sale en cada entrega.

---

## Stack instalado (verificado 2026-10-01)

| Componente | Estado | Detalle |
|---|---|---|
| `adb` | ✅ v34.0.4 | ya estaba en `/usr/bin/adb` |
| mobile-mcp | ✅ clonado + build | `external_repos/mobile-mcp` |
| Servicio systemd | ✅ active | `mobile-mcp.service`, puerto **3010** |
| Herramientas MCP | ✅ 33 | `hermes mcp test mobile` |
| Config en Hermes | ✅ | `mcp_servers.mobile.url` |

### ⚠️ Dos desvíos del plan original

1. **Puerto 3010, no 3001.** El 3001 ya lo ocupa `hermes_grafana`
   (`127.0.0.1:3001->3000`). Verificado con `ss -ltnp`.
2. **Transporte HTTP requiere flag.** mobile-mcp por defecto arranca en
   **stdio**; el modo HTTP se activa con `--listen [host:]port`
   (verificado en `lib/index.js`). El servicio systemd ya lo incluye.

### Nota de seguridad

El log del servidor avisa: sin `MOBILEMCP_AUTH`, acepta conexiones sin
autenticar. Escucha solo en `127.0.0.1` (localhost), así que no es reachable
desde fuera. Si algún día se expone en otra interfaz, **hay que setear
`MOBILEMCP_AUTH`** con un token Bearer.
