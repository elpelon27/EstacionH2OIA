# Runbook: Disaster Recovery

**Ultima actualizacion**: 2026-08-17
**Owner**: Líder + Prometeo
**Critico**: Si — plan de contingencia total

---

## Escenarios de desastre

### Nivel 1: Servicio caido (mas comun)
- valentina-bridge, dispatcher-bot, o telegram-bot cae
- **Sintomas**: alerta Prometheus, HTTP 503 en /health, bot no responde
- **Solucion**: Ver `RUNBOOK_ServiceDown.md`

### Nivel 2: Datos corruptos (medio)
- SQLite corrupto, tablas con NULLs, datos inconsistentes
- **Sintomas**: errores en logs, queries fallan, pedidos no procesan
- **Solucion**: Restaurar desde backup (ver abajo)

### Nivel 3: Server fisico falla (grave)
- Disco muere, servidor no arranca, perdida total
- **Sintomas**: sin acceso SSH, servicios todos abajo
- **Solucion**: Restauracion completa en nuevo hardware (ver Plan Total)

### Nivel 4: Seguridad comprometida (critico)
- API keys filtradas, acceso no autorizado, inyeccion detectada
- **Sintomas**: trafico anomalo, logs de auditoria, reportes externos
- **Solucion**: Rotacion de credenciales + auditoria forense

---

## Backup y restauracion

### Backups automaticos

| Tipo | Frecuencia | Ubicacion | Script |
|---|---|---|---|
| SQLite (valentina.db) | Diario 3am | `data/backups/` + Google Drive | `scripts/backup_db.sh` |
| dispatch.db | Diario 3am | `data/backups/` + Google Drive | `scripts/backup_db.sh` |
| Odoo PostgreSQL | Diario 4am | Docker volume + Google Drive | `scripts/backup_db.sh` |
| Config .env | Manual | Google Drive (off-site) | Manual |

### Restaurar SQLite (valentina.db)

```bash
cd /mnt/ssd_trabajo/hermes-agent

# 1. Detener bridge
sudo systemctl stop valentina-bridge.service

# 2. Backup del estado actual (por si acaso)
cp data/valentina.db data/valentina.db.broken_$(date +%Y%m%d)

# 3. Restaurar desde backup
cp data/backups/valentina_YYYYMMDD_HHMMSS.db data/valentina.db

# 4. Verificar integridad
sqlite3 data/valentina.db "PRAGMA integrity_check;"
sqlite3 data/valentina.db "SELECT COUNT(*) FROM orders;"
sqlite3 data/valentina.db "SELECT COUNT(*) FROM conversations;"

# 5. Reiniciar bridge
sudo systemctl start valentina-bridge.service

# 6. Verificar
curl -s http://localhost:8000/health | python3 -m json.tool
```

### Restaurar dispatch.db

```bash
cd /mnt/ssd_trabajo/hermes-agent

# 1. Detener dispatcher
sudo systemctl stop dispatcher-bot.service 2>/dev/null

# 2. Backup del estado actual
cp data/dispatch.db data/dispatch.db.broken_$(date +%Y%m%d)

# 3. Restaurar
cp data/backups/dispatch_YYYYMMDD_HHMMSS.db data/dispatch.db

# 4. Verificar
sqlite3 data/dispatch.db "PRAGMA integrity_check;"
sqlite3 data/dispatch.db "SELECT COUNT(*) FROM bottles;"
sqlite3 data/dispatch.db "SELECT COUNT(*) FROM vehicles;"

# 5. Reiniciar
sudo systemctl start dispatcher-bot.service 2>/dev/null
```

### Restaurar Odoo PostgreSQL

```bash
# 1. Verificar contenedor Odoo
docker ps | grep odoo

# 2. Restaurar desde backup
docker exec odoo-db pg_restore -U odoo -d postgres \
  /backups/odoo_YYYYMMDD.dump

# 3. Reiniciar Odoo
docker restart odoo

# 4. Verificar
curl -s http://localhost:8069/web/login | grep "Odoo"
```

---

## Plan de restauracion total (Server fisico)

### Prerequisitos
- Nuevo servidor con Ubuntu 22.04+
- Acceso a Google Drive con backups
- Acceso a GitHub repo: https://github.com/elpelon27/EstacionH2OIA

### Paso 1: Infraestructura base
```bash
# Instalar Python 3.12, Docker, dependencias
sudo apt update && sudo apt install -y python3.12 python3.12-venv docker.io docker-compose
sudo systemctl enable --now docker

# Crear usuario
sudo useradd -m -s /bin/bash skynet
```

### Paso 2: Restaurar codigo
```bash
cd /mnt/ssd_trabajo
git clone https://github.com/elpelon27/EstacionH2OIA.git hermes-agent
cd hermes-agent
git checkout feat/odoo-r4-integration

# Crear venv
python3.12 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

### Paso 3: Restaurar configuracion
```bash
# Restaurar .env desde Google Drive
mkdir -p config
# Copiar .env desde backup manual
nano config/.env  # Verificar todos los valores

# Verificar LOG_SALT (debe ser 32+ chars aleatorios)
grep LOG_SALT config/.env

# Instalar servicios systemd
sudo cp systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
```

### Paso 4: Restaurar datos
```bash
# Restaurar SQLite desde backup
cp data/backups/valentina_latest.db data/valentina.db
cp data/backups/dispatch_latest.db data/dispatch.db

# Restaurar Odoo PostgreSQL
docker compose up -d odoo-db
docker exec -i odoo-db pg_restore -U odoo -d postgres < /backups/odoo_latest.dump
docker compose up -d odoo
```

### Paso 5: Iniciar servicios
```bash
# Cloudflare tunnel
sudo systemctl start cloudflared.service

# Bridge (Valentina)
sudo systemctl start valentina-bridge.service

# Telegram bot (Prometeo)
sudo systemctl start prometeo-telegram.service

# Dispatcher bot
sudo systemctl start dispatcher-bot.service

# Verificar todos
sudo systemctl status valentina-bridge prometeo-telegram dispatcher-bot cloudflared
```

### Paso 6: Verificar
```bash
# Health check
curl -s http://localhost:8000/health | python3 -m json.tool

# Bot responde
# Enviar mensaje a @Skynet_27_bot con /status

# Prometheus
curl -s http://localhost:9090/-/healthy

# Grafana
curl -s http://localhost:3000/api/health
```

### Paso 7: Reconfigurar webhook Meta
1. Ir a https://developers.facebook.com/apps
2. WhatsApp API settings
3. Callback URL: `https://<nuevo-dominio-cloudflare>/webhook/meta`
4. Verify token: mismo que en `.env`
5. Suscribir a: `messages`

---

## Verificacion de backup (automatizada)

Hay un script de verificacion mensual: `scripts/verify_backup.sh`
- Se ejecuta el 1ero de cada mes via cron
- Hace restore test de SQLite en tmp
- Verifica integridad
- Alerta a Telegram si falla

Ver runbook de Backup Verification para mas detalles.

---

## Contactos de emergencia

| Rol | Contacto |
|---|---|
| Líder | @Skynet_27_bot (Telegram) |
| Cloudflare | Dashboard: https://dash.cloudflare.com |
| Meta WhatsApp API | https://developers.facebook.com/apps |
| GitHub Repo | https://github.com/elpelon27/EstacionH2OIA |
| Odoo | http://localhost:8069 (admin/admin) |
