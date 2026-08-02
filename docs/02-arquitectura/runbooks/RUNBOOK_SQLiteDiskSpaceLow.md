# RUNBOOK: SQLiteDiskSpaceLow
**Alert:** `SQLiteDiskSpaceLow` | **Severity:** CRITICAL | **Response Time:** < 10 min

---

## DESCRIPCIÓN
Disco SSD donde residen las BDs SQLite tiene < 10% espacio libre.

**Métrica:** `(node_filesystem_avail_bytes{mountpoint="/mnt/ssd_trabajo"} / node_filesystem_size_bytes{mountpoint="/mnt/ssd_trabajo"}) < 0.1`

---

## DIAGNÓSTICO (2-3 min)

```bash
# 1. Ver espacio en disco
df -h /mnt/ssd_trabajo

# 2. Ver qué ocupa espacio
du -h /mnt/ssd_trabajo/hermes-agent --max-depth=1 | sort -hr | head -20

# 3. Ver tamaño BDs
ls -lh /mnt/ssd_trabajo/hermes-agent/data/*.db
ls -lh /mnt/ssd_trabajo/backups/
```

---

## ACCIONES

### A. Limpiar backups antiguos (> 14 días)
```bash
# Ver backups
ls -lh /mnt/ssd_trabajo/backups/

# Borrar > 14 días
find /mnt/ssd_trabajo/backups -name "*.db" -mtime +14 -delete
find /mnt/ssd_trabajo/backups -name "*.tar.gz" -mtime +14 -delete

# Verificar
df -h /mnt/ssd_trabajo
```

### B. Limpiar logs systemd antiguos
```bash
# Ver tamaño logs
journalctl --disk-usage

# Limpiar > 7 días
sudo journalctl --vacuum-time=7d

# Verificar
journalctl --disk-usage
```

### C. Limpiar Docker (imágenes/volúmenes no usados)
```bash
docker system prune -a -f --volumes
# O más conservador:
docker image prune -a -f
docker volume prune -f
```

### D. VACUUM en BDs SQLite (recuperar espacio interno)
```bash
# Solo si BDs tienen espacio libre interno significativo
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/conversations.db "VACUUM;"
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/dispatch.db "VACUUM;"
```

---

## VERIFICACIÓN

```bash
# Espacio libre > 15%
df -h /mnt/ssd_trabajo | awk 'NR==2 {print $5}' | sed 's/%//'
# Debe ser < 85%
```

---

## ESCALAMIENTO

| Nivel | Espacio libre | Acción |
|-------|---------------|--------|
| Nivel 1 | 10-15% | Limpieza A-C |
| Nivel 2 | 5-10% | A-D urgente + Líder informado |
| Nivel 3 | < 5% | Expandir disco / migración urgente |

---

## REGISTRO

| Campo | Valor |
|-------|-------|
| Fecha/Hora | |
| Espacio libre antes | |
| Espacio libre después | |
| Acciones tomadas | |

**Firmado por:** ___________ | **Fecha:** ___________