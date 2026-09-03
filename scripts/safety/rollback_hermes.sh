#!/bin/bash
# Uso:
#   rollback_hermes.sh             → rollback a último tag safety-*
#   rollback_hermes.sh 3           → rollback a 3 commits atrás
#   rollback_hermes.sh safety-20260903_172801 → rollback a tag específico

set -e
cd /mnt/ssd_trabajo/hermes-agent

TARGET=""
if [ -z "$1" ]; then
  # Último tag safety
  TARGET=$(git tag | grep "^safety-" | sort -r | head -1)
  if [ -z "$TARGET" ]; then
    echo "❌ No hay tags safety-* para hacer rollback"
    exit 1
  fi
elif [[ "$1" =~ ^[0-9]+$ ]]; then
  # N commits atrás
  TARGET="HEAD~$1"
else
  # Tag específico
  TARGET="$1"
  if ! git tag | grep -q "^$TARGET$"; then
    echo "❌ Tag $TARGET no existe"
    echo "Tags disponibles: git tag | grep safety"
    exit 1
  fi
fi

echo "=== ROLLBACK A: $TARGET ==="

# Crear branch de recovery con cambios actuales (no perderlos)
RECOVERY="recovery/$(date '+%Y%m%d_%H%M%S')"
git checkout -b "$RECOVERY"
git add -A
git commit -m "recovery: estado antes de rollback a $TARGET" 2>/dev/null || true

# Volver a la rama principal
git checkout feat/odoo-r4-integration

# Reset suave (no destructivo, mantiene cambios en working tree)
git reset --mixed "$TARGET"

echo ""
echo "✓ Rollback completado a $TARGET"
echo "✓ Cambios descartados conservados en branch: $RECOVERY"
echo ""
echo "Para ver qué se descartó:"
echo "  git diff feat/odoo-r4-integration $RECOVERY"
echo ""
echo "Para restaurar un commit específico:"
echo "  git cherry-pick <commit>"
echo ""
echo "Para borrar la branch de recovery (si ya no la necesitás):"
echo "  git branch -D $RECOVERY"
