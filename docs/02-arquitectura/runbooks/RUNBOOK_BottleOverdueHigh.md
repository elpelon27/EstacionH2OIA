# RUNBOOK: BottleOverdueHigh
**Alert:** `BottleOverdueHigh` | **Severity:** WARNING | **Response Time:** < 15 min

---

## DESCRIPCIÓN
Más de 5 botellones loaner vencidos (no devueltos en tiempo esperado).

**Métrica:** `bottle_tracker_overdue > 5`

---

## DIAGNÓSTICO (2-3 min)

```bash
# 1. Ver botellas overdue
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/dispatch.db "
SELECT b.bottle_code, b.status, b.client_id, c.name as cliente,
       datetime(b.expected_return_at) as esperado,
       (strftime('%s','now') - b.expected_return_at)/3600 as horas_vencido
FROM bottles b
LEFT JOIN clients c ON b.client_id = c.id
WHERE b.status = 'with_client'
  AND b.expected_return_at IS NOT NULL
  AND b.expected_return_at < strftime('%s','now')
ORDER BY horas_vencido DESC;
"

# 2. Ver alertas activas
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/dispatch.db "
SELECT * FROM bottle_alerts WHERE alert_type = 'overdue' AND resolved_at IS NULL;
"
```

---

## ACCIONES

### 1. Notificar a choferes (recogida urgente)
```bash
# Enviar alerta Telegram a choferes afectados
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/dispatch.db "
SELECT v.telegram_chat_id, v.operator_name, b.bottle_code, c.name
FROM bottles b
JOIN clients c ON b.client_id = c.id
JOIN vehicles v ON c.zone_id = (SELECT zone_id FROM clients WHERE id = b.client_id)
WHERE b.status = 'with_client'
  AND b.expected_return_at < strftime('%s','now')
GROUP BY v.id;
"
# Usar chat_ids para enviar mensaje vía bot
```

### 2. Escalamiento automático 6h/24h/48h
- Verificar que `bottle_tracker.py` genera alertas automáticas
- Verificar `bottle_alerts` table tiene entries para overdue

### 3. Si cliente no responde 48h: escalar a humano
```bash
# Marcar alerta como escalada
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/dispatch.db "
UPDATE bottle_alerts SET severity = 'critical', acknowledged = 1
WHERE alert_type = 'overdue' AND resolved_at IS NULL;
"
```

---

## VERIFICACIÓN

```bash
# Overdue count < 3
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/dispatch.db "
SELECT COUNT(*) FROM bottles
WHERE status = 'with_client'
  AND expected_return_at IS NOT NULL
  AND expected_return_at < strftime('%s','now');
"
```

---

## ESCALAMIENTO

| Nivel | Overdue | Acción |
|-------|---------|--------|
| Nivel 1 | 3-5 | Notificar choferes + alerta automática |
| Nivel 2 | 6-10 | Escalamiento 6h/24h/48h + llamar cliente |
| Nivel 3 | > 10 | Escalar a Líder + posible cobro / bloqueo cliente |

---

## REGISTRO

| Campo | Valor |
|-------|-------|
| Fecha/Hora | |
| Overdue count | |
| Botellas afectadas | |
| Acción | |

**Firmado por:** ___________ | **Fecha:** ___________