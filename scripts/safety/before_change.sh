#!/bin/bash
TAREA=$1
TS=$(date '+%Y%m%d_%H%M%S')
BRANCH="safety/${TAREA}-${TS}"
cd /mnt/ssd_trabajo/hermes-agent
git checkout -b "$BRANCH"
mkdir -p .hermes/state
echo "$BRANCH" > .hermes/state/current_branch.txt
echo "✓ Branch de seguridad: $BRANCH"
echo "✓ Trabajá en esta branch. Si rompe algo, descartala."
echo "✓ Si todo OK: git checkout feat/odoo-r4-integration && git merge $BRANCH"
