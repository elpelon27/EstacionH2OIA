#!/bin/bash
# B2 — Reconciliar systemd unit + configurar NOPASSWD sudoers
# Ejecutar: sudo bash /mnt/ssd_trabajo/hermes-agent/scripts/b2_fix_systemd.sh
set -e

echo "=== B2: Reconciliar systemd unit ==="

# 1. Remover sudoers roto si existe
rm -f /etc/sudoers.d/h2o-deploy

# 2. Crear sudoers correcto (una linea, sin saltos)
echo 'skynet ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart valentina-bridge.service, /usr/bin/systemctl daemon-reload, /bin/cp /mnt/ssd_trabajo/hermes-agent/systemd/*.service /etc/systemd/system/' > /etc/sudoers.d/h2o-deploy
chmod 0440 /etc/sudoers.d/h2o-deploy

# 3. Copiar el unit del repo a /etc
cp /mnt/ssd_trabajo/hermes-agent/systemd/valentina-bridge.service /etc/systemd/system/valentina-bridge.service

# 4. Daemon reload
systemctl daemon-reload

# 5. Verificar
echo "=== Verificacion ==="
echo "sudoers:"
cat /etc/sudoers.d/h2o-deploy
echo ""
echo "unit tamano:"
wc -c /etc/systemd/system/valentina-bridge.service
echo ""
echo "B2_OK"
