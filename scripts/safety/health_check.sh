#!/bin/bash
# health_check.sh — Verificación de integridad post-corte eléctrico
# Se ejecuta al arranque del sistema (hermes-health-check.service)
REPORT=/home/skynet/health_report.txt
REPO=/mnt/ssd_trabajo/hermes-agent

{
echo "==============================================="
echo "HEALTH CHECK HERMES — $(date '+%Y-%m-%d %H:%M:%S')"
echo "==============================================="

# --- 1. Servicios críticos ---
echo ""
echo "--- SERVICIOS ---"
for svc in cron docker ollama prometeo-telegram open-notebook; do
  state=$(systemctl is-active "$svc" 2>/dev/null)
  if [ "$state" = "active" ]; then
    echo "✓ $svc: active"
  else
    echo "⚠ $svc: $state"
  fi
done

# --- 2. Qdrant ---
echo ""
echo "--- QDRANT ---"
code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:6333/ 2>/dev/null)
if [ "$code" = "200" ]; then
  echo "✓ Qdrant: HTTP $code"
else
  echo "⚠ Qdrant: HTTP $code (esperado 200)"
fi

# --- 3. Git limpio ---
echo ""
echo "--- GIT ---"
cd "$REPO" 2>/dev/null || { echo "⚠ Repo $REPO inaccesible"; exit 1; }
if git fsck --no-dangling > /dev/null 2>&1; then
  echo "✓ git fsck: OK (repo íntegro)"
else
  echo "⚠ git fsck: FALLÓ — repo corrupto"
fi
if git diff --quiet 2>/dev/null && git diff --cached --quiet 2>/dev/null; then
  echo "✓ Working tree limpio"
else
  echo "⚠ Working tree con cambios sin commit"
fi

# --- 4. Commits sin push ---
echo ""
echo "--- PUSH ---"
git fetch origin -q > /dev/null 2>&1
branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
unpushed=$(git rev-list --count origin/"$branch"..HEAD 2>/dev/null || echo "?")
if [ "$unpushed" = "0" ]; then
  echo "✓ Branch $branch: 0 commits sin push"
else
  echo "⚠ Branch $branch: $unpushed commits sin push"
fi

# --- 5. Tarea interrumpida ---
echo ""
echo "--- TAREA EN CURSO ---"
if [ -f "$REPO/.hermes/state/current_task.json" ]; then
  status=$(python3 -c "import json; print(json.load(open('$REPO/.hermes/state/current_task.json')).get('status','?'))" 2>/dev/null)
  step=$(python3 -c "import json; print(json.load(open('$REPO/.hermes/state/current_task.json')).get('current_step','?'))" 2>/dev/null)
  if [ "$status" = "in_progress" ]; then
    echo "⚠ TAREA INTERRUMPIDA: $step"
  else
    echo "✓ Tarea: $status"
  fi
else
  echo "✓ Sin current_task.json"
fi

# --- 6. Discos ---
echo ""
echo "--- DISCOS ---"
df -h | grep -vE "tmpfs|loop|udev"

echo ""
echo "==============================================="
echo "FIN HEALTH CHECK — $(date '+%Y-%m-%d %H:%M:%S')"
echo "==============================================="
} >> "$REPORT" 2>&1

echo "Reporte: $REPORT (último health check)"
