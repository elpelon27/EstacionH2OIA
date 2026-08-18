#!/bin/bash
# verify_backup.sh — Verificacion mensual de integridad de backups
# Cron: 0 6 1 * * /mnt/ssd_trabajo/hermes-agent/scripts/verify_backup.sh
# Se ejecuta el 1ero de cada mes a las 6am
#
# Que hace:
# 1. Encuentra el backup mas reciente de SQLite (conversations.db, dispatch.db)
# 2. Lo restaura en un tmp
# 3. Verifica integridad con PRAGMA integrity_check
# 4. Cuenta registros en tablas criticas
# 5. Verifica Odoo PostgreSQL si esta corriendo
# 6. Alerta a Telegram si algo falla

set -euo pipefail

REPO="/mnt/ssd_trabajo/hermes-agent"
BACKUP_DIR="${REPO}/backups"
DAILY_BACKUP_DIR="/mnt/ssd_trabajo/backups/daily"
TMP_DIR=$(mktemp -d)
ALERT_FILE="${REPO}/data/.backup_verify_result"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ERRORS=0
WARNINGS=0
RESULTS=""

log() {
    echo "[$(date)] $1"
    RESULTS="${RESULTS}[$(date)] $1\n"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"
    RESULTS="${RESULTS}[ERROR] $(date '+%Y-%m-%d %H:%M:%S') $1\n"
    ERRORS=$((ERRORS + 1))
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"
    RESULTS="${RESULTS}[WARN] $(date '+%Y-%m-%d %H:%M:%S') $1\n"
    WARNINGS=$((WARNINGS + 1))
}

log_ok() {
    echo -e "${GREEN}[OK]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"
    RESULTS="${RESULTS}[OK] $(date '+%Y-%m-%d %H:%M:%S') $1\n"
}

log "=== INICIO VERIFICACION DE BACKUP ==="

# ===== 1. VERIFICAR BACKUP MAS RECIENTE =====
log "Buscando backup mas reciente..."

# Buscar en backups/ (formato: conversations-YYYYMMDD.db, dispatch-YYYYMMDD.db)
LATEST_CONV=$(find "${BACKUP_DIR}" -name "conversations-*.db" -type f 2>/dev/null | sort | tail -1)
LATEST_DISP=$(find "${BACKUP_DIR}" -name "dispatch-*.db" -type f 2>/dev/null | sort | tail -1)

# Buscar en daily/ (formato: YYYYMMDD_HHMMSS.tar.gz)
LATEST_DAILY=$(find "${DAILY_BACKUP_DIR}" -name "*.tar.gz" -type f 2>/dev/null | sort | tail -1)

if [ -z "${LATEST_CONV}" ] && [ -z "${LATEST_DAILY}" ]; then
    log_error "No se encontro ningun backup de SQLite"
    log "Buscado en: ${BACKUP_DIR}/conversations-*.db"
    log "Buscado en: ${DAILY_BACKUP_DIR}/*.tar.gz"
else
    if [ -n "${LATEST_CONV}" ]; then
        log_ok "Backup conversations encontrado: $(basename "${LATEST_CONV}")"
    fi
    if [ -n "${LATEST_DISP}" ]; then
        log_ok "Backup dispatch encontrado: $(basename "${LATEST_DISP}")"
    fi
    if [ -n "${LATEST_DAILY}" ]; then
        log_ok "Backup diario encontrado: $(basename "${LATEST_DAILY}")"
    fi
fi

# ===== 2. RESTAURAR Y VERIFICAR SQLITE =====
log "Verificando integridad de SQLite..."

verify_sqlite() {
    local backup_file="$1"
    local db_name="$2"
    local tmp_db="${TMP_DIR}/${db_name}"

    if [ -z "${backup_file}" ] || [ ! -f "${backup_file}" ]; then
        log_warn "Backup de ${db_name} no encontrado, saltando"
        return 0
    fi

    # Copiar a tmp
    cp "${backup_file}" "${tmp_db}"

    # Verificar integridad
    local integrity
    integrity=$(sqlite3 "${tmp_db}" "PRAGMA integrity_check;" 2>&1)

    if [ "${integrity}" = "ok" ]; then
        log_ok "Integridad ${db_name}: OK"
    else
        log_error "Integridad ${db_name}: FALLIDA (${integrity})"
        return 1
    fi

    # Contar registros en tablas criticas
    local table_counts
    table_counts=$(sqlite3 "${tmp_db}" "
        SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;
    " 2>/dev/null)

    for table in ${table_counts}; do
        local count
        count=$(sqlite3 "${tmp_db}" "SELECT COUNT(*) FROM ${table};" 2>/dev/null || echo "ERROR")
        log "  ${db_name}.${table}: ${count} registros"
    done

    return 0
}

verify_sqlite "${LATEST_CONV}" "conversations.db"
verify_sqlite "${LATEST_DISP}" "dispatch.db"

# ===== 3. VERIFICAR BACKUP DIARIO (tar.gz) =====
if [ -n "${LATEST_DAILY}" ]; then
    log "Verificando integridad del backup diario..."

    # Verificar que el tar.gz no esta corrupto
    if tar -tzf "${LATEST_DAILY}" > /dev/null 2>&1; then
        log_ok "Integridad tar.gz: OK"
    else
        log_error "Integridad tar.gz: FALLIDA (archivo corrupto)"
    fi

    # Extraer y verificar contenido
    cd "${TMP_DIR}"
    if tar -xzf "${LATEST_DAILY}" 2>/dev/null; then
        local_files=$(find . -name "*.db" -type f)
        for db_file in ${local_files}; do
            integrity=$(sqlite3 "${db_file}" "PRAGMA integrity_check;" 2>&1)
            if [ "${integrity}" = "ok" ]; then
                log_ok "Integridad $(basename "${db_file}"): OK"
            else
                log_error "Integridad $(basename "${db_file}"): FALLIDA"
            fi
        done
    else
        log_warn "No se pudo extraer tar.gz para verificacion profunda"
    fi
fi

# ===== 4. VERIFICAR ODOO POSTGRESQL =====
log "Verificando Odoo PostgreSQL..."

if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "odoo"; then
    log "Odoo container detectado, verificando..."

    # Verificar que PostgreSQL responde
    if docker exec odoo-db pg_isready -U odoo > /dev/null 2>&1; then
        log_ok "PostgreSQL (Odoo): responde OK"
    else
        log_warn "PostgreSQL (Odoo): no responde (puede estar iniciando)"
    fi

    # Contar tablas
    local_tables=$(docker exec odoo-db psql -U odoo -d postgres -t -c \
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null || echo "ERROR")
    log "  Odoo tablas en public schema: ${local_tables}"
else
    log_warn "Odoo container no encontrado, saltando verificacion PostgreSQL"
fi

# ===== 5. LIMPIAR TMP =====
rm -rf "${TMP_DIR}"
log_ok "Limpieza temporal completada"

# ===== 6. RESUMEN FINAL =====
log "=== RESUMEN ==="
log "Errores: ${ERRORS}"
log "Warnings: ${WARNINGS}"

# Guardar resultado para futuras referencias
echo -e "${RESULTS}" > "${ALERT_FILE}"

# ===== 7. ALERTA TELEGRAM SI HAY ERRORES =====
if [ ${ERRORS} -gt 0 ]; then
    log_error "VERIFICACION DE BACKUP FALLIDA — ${ERRORS} errores"

    # Intentar enviar alerta por Telegram si el bot esta configurado
    if [ -f "${REPO}/config/.env" ]; then
        TG_TOKEN=$(grep TELEGRAM_BOT_TOKEN "${REPO}/config/.env" 2>/dev/null | cut -d'=' -f2 || echo "")
        TG_CHAT=$(grep TELEGRAM_CHAT_ID_LIDER "${REPO}/config/.env" 2>/dev/null | cut -d'=' -f2 || echo "")

        if [ -n "${TG_TOKEN}" ] && [ -n "${TG_CHAT}" ]; then
            MSG="🚨 BACKUP VERIFICATION FAILED

Fecha: ${DATE}
Errores: ${ERRORS}
Warnings: ${WARNINGS}

Ver log: ${ALERT_FILE}

Detalles:
$(echo -e "${RESULTS}" | head -20)"

            curl -s -X POST "https://api.telegram.org/bot${TG_TOKEN}/sendMessage" \
                -d "chat_id=${TG_CHAT}" \
                -d "text=${MSG}" > /dev/null 2>&1 || true
            log "Alerta Telegram enviada"
        fi
    fi

    exit 1
else
    log_ok "VERIFICACION DE BACKUP EXITOSA"
    exit 0
fi
