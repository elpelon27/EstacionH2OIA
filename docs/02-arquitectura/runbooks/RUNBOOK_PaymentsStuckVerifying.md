# RUNBOOK: PaymentsStuckVerifying
**Alert:** `PaymentsStuckVerifying` | **Severity:** WARNING | **Response Time:** < 20 min

---

## DESCRIPCIÓN
Más de 10 pagos atascados en estado "verifying" en la última hora.

**Métrica:** `increase(financial_payments_verifying[1h]) > 10`

---

## DIAGNÓSTICO (3-5 min)

```bash
# 1. Ver pagos en verifying
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/conversations.db "
SELECT id, fs_pedido_id, cliente_nombre, monto_eur, verificacion_metodo, creado_at
FROM fs_pagos
WHERE verificacion_metodo = 'verificando'
ORDER BY creado_at DESC;
"

# 2. Verificar recovery scan
journalctl -u valentina-bridge -n 50 --no-pager | grep -i recovery

# 3. Verificar recordatorios
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/conversations.db "
SELECT * FROM fs_pedidos
WHERE estado_pago IN ('verificando', 'parcial')
AND escalo_humano = 0
ORDER BY creado_at DESC;
"
```

---

## ACCIONES

### 1. Ejecutar recovery scan manual
```bash
cd /mnt/ssd_trabajo/hermes-agent
source venv/bin/activate
python3 -c "
from src.financial.verificacion import recovery_scan_stuck_payments
import asyncio
recovered = asyncio.run(recovery_scan_stuck_payments())
print(f'Recuperados: {recovered}')
"
```

### 2. Verificar métodos de verificación configurados
```bash
grep -E "FS_OCR_ENABLED|FS_BANK_VERIFICATION_METHOD" /mnt/ssd_trabajo/hermes-agent/config/.env
```

### 3. Si OCR falla: verificar Ollama + Qwen2.5-VL
```bash
curl -s http://localhost:11434/api/tags | jq '.models[] | select(.name | contains("qwen2.5-vl"))'
```

### 4. Escalamiento manual a Líder
```bash
# Enviar alerta Telegram
curl -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
  -d chat_id=1663148211 \
  -d text="🚨 ESCALAMIENTO: $(sqlite3 /mnt/ssd_trabajo/hermes-agent/data/conversations.db \"SELECT COUNT(*) FROM fs_pagos WHERE verificacion_metodo='verificando'\" ) pagos atascados en verificando"
```

---

## VERIFICACIÓN

```bash
# Pagos en verifying < 5
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/conversations.db "
SELECT COUNT(*) FROM fs_pagos WHERE verificacion_metodo = 'verificando';
"
```

---

## ESCALAMIENTO

| Nivel | Tiempo | Acción |
|-------|--------|--------|
| Nivel 1 | 0-20 min | Recovery scan + verificación OCR |
| Nivel 2 | 20-40 min | Escalamiento manual a Líder |
| Nivel 3 | 40+ min | Contactar Prometeo, revisar arquitectura verificación |

---

## REGISTRO

| Campo | Valor |
|-------|-------|
| Fecha/Hora | |
| Pagos en verifying | |
| Causa | |
| Acción | |

**Firmado por:** ___________ | **Fecha:** ___________