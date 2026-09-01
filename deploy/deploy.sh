#!/usr/bin/env bash
#
# Actualiza producción a la última versión de la rama actual. Se corre EN
# el VPS, parado en /home/restomind/app (o con esa ruta pasada como $1).
#
# No hace falta un paso de migración aparte: backend/migrate.py corre solo
# al arrancar la app (backend/app.py lo invoca al importar).
#
set -euo pipefail

APP_DIR="${1:-/home/restomind/app}"
cd "${APP_DIR}"

echo "==> git pull"
git pull

echo "==> Instalando dependencias (por si requirements.txt cambió)"
venv/bin/pip install -r requirements.txt

echo "==> Reiniciando el servicio"
sudo systemctl restart restomind

echo "==> Esperando a que levante..."
sleep 2
if curl -sf http://127.0.0.1:8000/health > /dev/null; then
    echo "==> OK: /health responde"
else
    echo "==> ⚠️  /health no respondió — revisá: journalctl -u restomind -n 50 --no-pager"
    exit 1
fi
