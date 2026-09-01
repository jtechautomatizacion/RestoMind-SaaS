#!/usr/bin/env bash
#
# Backup diario de la base SQLite de producción. Pensado para correr por
# cron como el usuario 'restomind' (ver instrucciones al final del archivo).
#
# Usa `sqlite3 ... .backup`, NO `cp`: un cp crudo puede copiar el archivo a
# mitad de una escritura y corromperlo. El comando .backup de SQLite es
# seguro de correr con la app escribiendo al mismo tiempo (usa la misma API
# que usaría cualquier herramienta de backup en caliente).
#
set -euo pipefail

APP_DIR="${APP_DIR:-/home/restomind/app}"
DB_PATH="${APP_DIR}/restomind.db"
BACKUP_DIR="${BACKUP_DIR:-/home/restomind/backups}"
DIAS_RETENCION=14

mkdir -p "${BACKUP_DIR}"

FECHA="$(date +%Y-%m-%d_%H%M%S)"
DESTINO="${BACKUP_DIR}/restomind_${FECHA}.db"

sqlite3 "${DB_PATH}" ".backup '${DESTINO}'"
gzip "${DESTINO}"

echo "Backup creado: ${DESTINO}.gz"

# Retención: borra backups locales de más de N días. Esto NO reemplaza una
# copia fuera del servidor — un backup que vive en el mismo disco que
# puede fallar (o en el mismo VPS que podés perder por completo) no es un
# backup real. Recomendado: sincronizar BACKUP_DIR periódicamente a otro
# lugar (tu propia PC vía rsync/scp, o almacenamiento barato tipo
# Backblaze B2/S3) — no automatizado acá a propósito, para no atarte a un
# proveedor sin que lo decidas vos.
find "${BACKUP_DIR}" -name "restomind_*.db.gz" -mtime "+${DIAS_RETENCION}" -delete

echo "Backups en ${BACKUP_DIR}:"
ls -lh "${BACKUP_DIR}"

# ---------------------------------------------------------------------
# Instalación en cron (correr una vez, como el usuario restomind):
#
#   crontab -e
#
# Y agregar (backup diario a las 3:00 am, hora del servidor):
#
#   0 3 * * * /home/restomind/app/deploy/backup_db.sh >> /home/restomind/backups/backup.log 2>&1
# ---------------------------------------------------------------------
