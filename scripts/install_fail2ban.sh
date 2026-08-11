#!/bin/bash
# Install and configure fail2ban for SSH protection
# Run with: sudo bash install_fail2ban.sh

set -euo pipefail

echo "=== Installing fail2ban ==="
apt-get update -qq
apt-get install -y fail2ban

echo "=== Configuring fail2ban for SSH ==="
cat > /etc/fail2ban/jail.d/sshd.conf <<'JAIL_EOF'
[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
findtime = 600
bantime = 3600
banaction = iptables-multiport
backend = systemd

# More aggressive for repeated offenders
[sshd-ddos]
enabled = true
port = ssh
filter = sshd-ddos
logpath = /var/log/auth.log
maxretry = 2
findtime = 600
bantime = 86400
banaction = iptables-multiport
backend = systemd
JAIL_EOF

echo "=== Creating custom filter for SSH DDoS ==="
cat > /etc/fail2ban/filter.d/sshd-ddos.conf <<'FILTER_EOF'
[Definition]
failregex = ^%(__prefix_line)s(?:error: maximum authentication attempts exceeded for|Failed (?:password|publickey) for .* from <HOST>.*ssh2).*$
ignoreregex =
FILTER_EOF

echo "=== Enabling and starting fail2ban ==="
systemctl enable fail2ban
systemctl restart fail2ban

echo "=== Verifying status ==="
sleep 2
fail2ban-client status
fail2ban-client status sshd

echo "=== Done ==="