# Chequeo de Seguridad + Configuración Empresarial — Celulares de Choferes

**Estado al 2026-10-01:** ⚠️ **BLOQUEADO por configuración del celular** —
hay un equipo conectado por USB pero **ADB no lo ve**.

---

## Diagnóstico (verificado, no supuesto)

`lsusb` detecta el teléfono:

```
Bus 003 Device 003: ID 1782:4001 Spreadtrum Communications Inc. Unisoc Phone
  iManufacturer  1 Unisoc
  iProduct       2 Unisoc Phone
  iSerial        3 SP6300000000016611
```

Pero `adb devices -l` devuelve vacío. La causa está en el modo USB:

```
bNumInterfaces     1
bInterfaceNumber   0
bInterfaceClass    6 Imaging        ← PTP
bInterfaceSubClass 1 Still Image Capture
bInterfaceProtocol 1 Picture Transfer Protocol (PIMA 15470)
```

**El celular está en modo PTP (transferencia de fotos) y expone una sola
interfaz.** En PTP el canal ADB no existe, por eso `adb` no lo lista ni
siquiera como `unauthorized`. No es problema de cable, de permisos ni de
reglas udev — es que la depuración USB no está activa.

Esto **no se puede forzar desde el servidor**: depende de un ajuste en el
propio teléfono.

---

## Qué hay que hacer en el celular (Líder)

1. **Activar Opciones de desarrollador:**
   Ajustes → Acerca del teléfono → tocar 7 veces sobre
   "Número de compilación".

2. **Activar Depuración USB:**
   Ajustes → Sistema → Opciones de desarrollador → **Depuración USB** → ON.

3. **Cambiar el modo USB:** deslizar la barra de notificaciones, tocar
   "USB para transferencia de imágenes" / "Cargando" y elegir
   **"Transferencia de archivos" (MTP)** o **"Transferencia de archivos Android"**.

4. Aceptar el diálogo **"¿Permitir depuración USB?"**, marcando
   **"Permitir siempre desde este equipo"**.

5. Decir: **"Endurecer equipo 1"** (Yordanis) o **"Endurecer equipo 2"** (Evert).

Verificación de que quedó listo:
```bash
adb devices -l
#   → SP6300000000016611  device   ← correcto
#   → SP6300000000016611  unauthorized  ← falta el paso 4
#   → (vacío)                       ← sigue en PTP, revisá el paso 3
```

---

## Qué hace `scripts/harden_phone.sh <serial> <vehicle_id>`

Cuando el equipo aparezca como `device`:

```bash
./scripts/harden_phone.sh SP6300000000016611 1   # Yordanis
./scripts/harden_phone.sh <serial>           2   # Evert
```

### a) Bloqueo de apps innecesarias

Usa `pm disable-user --user 0` sobre:
- `com.facebook.katana` (Facebook)
- `com.instagram.android` (Instagram)
- `com.tiktok.android` (TikTok)

⚠️ **`disable-user` no desinstala**: la app queda deshabilitada para el
usuario pero se puede revertir con `pm enable`. Si no está instalada, el
script lo reporta y sigue (no falla). Verifica el resultado real con
`pm list packages -d` en vez de asumir que salió bien.

### b) GPS alta precisión

```
settings put secure location_mode 3
settings put location location_mode 3
```

Escribe en las dos tablas (`secure` y `location`) porque según la versión de
Android el ajuste vive en una u otra. Luego **lee el valor de vuelta** para
confirmar, no da por hecho que se aplicó.

### c) Pantalla

- `screen_brightness` → **255** (máximo, para visibilidad en exteriores)
- `screen_off_timeout` → **600000 ms (10 min)**

Ambos se releen y se reportan.

### d) Verificación de apps requeridas — **sin instalar**

Por directiva del Líder, WhatsApp, Telegram y Chrome ya están instalados y
operativos. El script **solo verifica** que sigan activos:
- `com.whatsapp`
- `org.telegram.messenger`
- `com.android.chrome`

**Nunca ejecuta `install`.** Si alguna falta o está bloqueada, lo reporta
como problema en vez de instalarla.

También valida que la sesión WAHA del chofer esté `WORKING` con el número
correcto, para que el endurecimiento no quede separado de la regla de
consistencia por entrega.

---

## Restricciones respetadas

| Restricción | Cómo se cumple |
|---|---|
| **NO instalar apps** | El script no contiene ningún `adb install`. Solo `pm list packages` y `pm disable-user`. |
| Reversible | `disable-user` se deshace con `pm enable <pkg>`. |
| Verificación real | Cada ajuste se relee desde el dispositivo y se reporta el valor efectivo. |

## Script relacionado

`scripts/setup_phone_auto.sh` — configuración inicial (pantalla encendida
mientras carga, registro en `dispatch.db`). Este `harden_phone.sh` es la capa
de seguridad; se pueden correr los dos, primero setup y después harden.
