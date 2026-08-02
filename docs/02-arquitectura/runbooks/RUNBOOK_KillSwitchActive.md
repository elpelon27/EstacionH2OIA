# 🛑 RUNBOOK: KillSwitchActive
**Alert:** `KillSwitchActive` | **Severity:** CRITICAL | **Response Time:** < 5 min

---

## 📋 DESCRIPCIÓN
El kill switch de Valentina Bridge ha sido activado. Valentina NO responderá a mensajes de WhatsApp.

**Métrica:** `valentina_active_conversations < 0 or absent(valentina_active_conversations) == 1`

---

## 🔍 DIAGNÓSTICO INICIAL (1-2 min)

```bash
# 1. Verificar estado del health endpoint
curl -s http://localhost:8000/health | jq .

# 2. Verificar si existe archivo kill switch
ls -la /mnt/ssd_trabajo/hermes-agent/data/valentina.kill

# 3. Verificar logs recientes
journalctl -u valentina-bridge -n 50 --no-pager
```

**Resultado esperado si kill switch activo:**
```json
{
  "status": "kill_switch_active",
  "checks": { "kill_switch": true }
}
```

---

## 🎯 ACCIONES SEGÚN CAUSA

### Causa A: Activación intencional por Líder (vía `/stop` en Telegram Bot)
```bash
# Verificar quién lo activó
cat /mnt/ssd_trabajo/hermes-agent/data/valentina.kill
# Output: "killed by <username> at <timestamp>"
```
**Acción:** Confirmar con Líder si debe reactivarse. Si sí → Paso 2.

### Causa B: Activación accidental / prueba
**Acción:** Desactivar inmediatamente → Paso 2.

### Causa C: Archivo残留 de reinicio previo
```bash
# Si el archivo existe pero no debería (ej. tras reinicio forzado)
rm /mnt/ssd_trabajo/hermes-agent/data/valentina.kill
```
**Acción:** El bridge lo limpia automáticamente al arrancar (lifespan), pero si persiste → borrar manual.

---

## ✅ PASO 2: REACTIVAR VALENTINA

### Opción 1: Vía Telegram (recomendado)
```
Enviar al bot @ValentinaBridgeBot: /start
```
Respuesta esperada: `✅ Kill switch DESACTIVADO — Valentina está respondiendo de nuevo. 💧`

### Opción 2: Vía CLI (si Telegram no disponible)
```bash
rm -f /mnt/ssd_trabajo/hermes-agent/data/valentina.kill
# Verificar
curl -s http://localhost:8000/health | jq -e '.checks.kill_switch == false'
```

---

## 🔍 VERIFICACIÓN POST-REACTIVACIÓN (1 min)

```bash
# 1. Health check
curl -s http://localhost:8000/health | jq .

# 2. Enviar mensaje de prueba a WhatsApp (número de prueba)
# Verificar en logs: journalctl -u valentina-bridge -f

# 3. Confirmar métricas
curl -s http://localhost:8000/metrics | grep valentina_messages_total
```

---

## 📞 ESCALAMIENTO

| Nivel | Tiempo | Acción |
|-------|--------|--------|
| **Nivel 1** | 0-5 min | Ejecutar runbook, reactivar |
| **Nivel 2** | 5-15 min | Si no reactiva → Reiniciar servicio: `sudo systemctl restart valentina-bridge` |
| **Nivel 3** | 15+ min | Contactar a Prometeo / Líder → Revisar logs completos, posible bug |

---

## 📝 REGISTRO DE INCIDENTE

| Campo | Valor |
|-------|-------|
| Fecha/Hora | |
| Causa raíz | |
| Acción tomada | |
| Tiempo de inactividad | |
| Impacto en clientes | |
| Prevención futura | |

**Firmado por:** ___________ | **Fecha:** ___________

---

## 🔗 ENLACES RELACIONADOS
- Dashboard: [Valentina Bridge Overview](http://localhost:3001/d/bftxd5ovnp3b4b)
- Logs: `journalctl -u valentina-bridge -f`
- Código kill switch: `api/bridge.py` (línea ~172, ~190, ~2330)
