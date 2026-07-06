#!/usr/bin/env bash
# ============================================================================
# Valentina Bridge — Script de despliegue
# Estación H2O · Maracaibo, Venezuela
# ============================================================================
# Uso: bash deploy.sh
# Debe ejecutarse en el servidor Maracaibo como usuario skynet.
# ============================================================================

set -euo pipefail

# --- Configuración ---
REPO_DIR="/mnt/ssd_trabajo/hermes-agent"
API_DIR="${REPO_DIR}/api"
DATA_DIR="${REPO_DIR}/data"
CONFIG_DIR="${REPO_DIR}/config"
ENV_FILE="${CONFIG_DIR}/.env"
VENV_DIR="${REPO_DIR}/venv"
SERVICE_NAME="hermes-agent.service"

echo "🚀 Despliegue Valentina Bridge — Estación H2O"
echo "=============================================="

# --- 0. Verificar que estamos en el servidor correcto ---
if [[ "$(hostname)" != "skynet-System-product-name" ]]; then
    echo "⚠️  ADVERTENCIA: hostname no es el esperado. ¿Seguro que estás en Maracaibo?"
    read -p "Continuar? (y/N): " -r
    [[ ! $REPLY =~ ^[Yy]$ ]] && exit 1
fi

# --- 1. Verificar .env ---
if [[ ! -f "$ENV_FILE" ]]; then
    echo "❌ No existe $ENV_FILE"
    echo "   Copia .env.example y rellena tus credenciales:"
    echo "   cp .env.example $ENV_FILE"
    echo "   nano $ENV_FILE"
    exit 1
fi
echo "✅ .env encontrado"

# Verificar que las 3 críticas estén rellenas (no vacías)
source "$ENV_FILE"
if [[ -z "$META_ACCESS_TOKEN" || -z "$DIFY_API_KEY" || -z "$META_APP_SECRET" ]]; then
    echo "❌ Faltan credenciales críticas en .env:"
    echo "   META_ACCESS_TOKEN, META_APP_SECRET o DIFY_API_KEY vacías"
    exit 1
fi
echo "✅ Credenciales verificadas"

# --- 2. Copiar bridge.py ---
mkdir -p "$API_DIR"
if [[ -f "./bridge.py" ]]; then
    cp -v ./bridge.py "$API_DIR/bridge.py"
elif [[ -f "$API_DIR/bridge.py" ]]; then
    echo "ℹ️  bridge.py ya en $API_DIR (no se sobrescribe)"
else
    echo "❌ No encuentro bridge.py en el directorio actual ni en $API_DIR"
    exit 1
fi

# --- 3. Crear directorio de datos ---
mkdir -p "$DATA_DIR"
echo "✅ Directorio data: $DATA_DIR"

# --- 4. Venv + dependencias ---
if [[ ! -d "$VENV_DIR" ]]; then
    echo "📦 Creando venv Python 3.12..."
    python3.12 -m venv "$VENV_DIR"
fi

echo "📦 Instalando dependencias..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet \
    fastapi==0.115.0 \
    uvicorn[standard]==0.30.6 \
    httpx==0.27.2 \
    slowapi==0.1.9
echo "✅ Dependencias instaladas"

# --- 5. Cargar .env en systemd ---
# Crear/actualizar el override de systemd para cargar el .env
OVERRIDE_DIR="/etc/systemd/system/${SERVICE_NAME}.d"
sudo mkdir -p "$OVERRIDE_DIR"
sudo tee "$OVERRIDE_DIR/env.conf" > /dev/null <<EOF
[Service]
EnvironmentFile=${ENV_FILE}
WorkingDirectory=${API_DIR}
ExecStart=${VENV_DIR}/bin/uvicorn bridge:app --host 0.0.0.0 --port 8000 --workers 1
Restart=always
RestartSec=5
StartLimitBurst=5
StartLimitIntervalSec=60
EOF
echo "✅ Override systemd configurado"

# --- 6. Reload + restart ---
echo "🔄 Reiniciando servicio systemd..."
sudo systemctl daemon-reload
sudo systemctl restart "$SERVICE_NAME"
sleep 2

# --- 7. Health check ---
echo "🩺 Health check..."
for i in 1 2 3 4 5; do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo "✅ Bridge saludable (intento $i)"
        curl -s http://localhost:8000/health | python3 -m json.tool
        break
    fi
    echo "   intento $i... esperando"
    sleep 2
    if [[ $i -eq 5 ]]; then
        echo "❌ Bridge no responde tras 10s"
        echo "   Logs: journalctl -u $SERVICE_NAME -n 50 --no-pager"
        exit 1
    fi
done

# --- 8. Estado final ---
echo ""
echo "=============================================="
echo "✅ Despliegue completado"
echo "=============================================="
echo ""
echo "📋 Próximos pasos:"
echo "   1. Verifica que systemd está activo:"
echo "      systemctl status $SERVICE_NAME"
echo ""
echo "   2. Obtén tu URL pública de Cloudflare Tunnel:"
echo "      systemctl status cloudflared-tunnel.service | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com'"
echo ""
echo "   3. Configura el webhook en Meta Dashboard:"
echo "      https://developers.facebook.com/apps/975863248739508/whatsapp_business/wa_settings/"
echo "      Callback URL: https://<tu-url-cloudflare>/webhook/meta"
echo "      Verify Token: $META_VERIFY_TOKEN"
echo ""
echo "   4. Suscríbete al campo 'messages' del webhook"
echo ""
echo "   5. PRUEBA DE FUEGO: envía 'hola' desde tu WhatsApp (+58 412-256-0720)"
echo "      a Valentina (+58 422-711-9156)"
echo ""
echo "📊 Logs en vivo:"
echo "   journalctl -u $SERVICE_NAME -f"
echo ""
echo "💧 Valentina está lista para producción."
