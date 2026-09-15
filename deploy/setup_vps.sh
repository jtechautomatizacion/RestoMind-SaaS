#!/usr/bin/env bash
#
# Bootstrap de un VPS Ubuntu 24.04 nuevo para RestoMind. Se corre UNA sola
# vez, como root o con sudo, recién estrenado el servidor.
#
# 24.04 (Noble) trae Python 3.12 de fábrica — el mismo con el que se
# desarrolla — así que NO hace falta el PPA de deadsnakes que necesitaban
# las versiones anteriores (22.04 trae 3.10; 20.04, 3.8). Una dependencia
# externa menos en el arranque, y el servidor corre exactamente el mismo
# intérprete que la máquina de desarrollo.
#
# No genera ningún secreto por vos: SECRET_KEY, credenciales SMTP y de
# Firebase quedan como TODO en el .env final para que los completes a mano.
# Un script versionado en git nunca debe ser el que inventa contraseñas.
#
# Uso:
#   scp deploy/setup_vps.sh root@TU_IP:~/
#   ssh root@TU_IP
#   REPO_URL="https://github.com/tu-usuario/RestoMind-SaaS.git" bash setup_vps.sh
#
set -euo pipefail

REPO_URL="${REPO_URL:?Definí REPO_URL antes de correr este script, ej: REPO_URL=https://github.com/... bash setup_vps.sh}"
APP_USER="restomind"
APP_DIR="/home/${APP_USER}/app"

echo "==> Actualizando el sistema"
apt update && apt upgrade -y

echo "==> Instalando Python (el nativo del sistema: 3.12 en Ubuntu 24.04)"
# Ubuntu separa venv y los headers en paquetes aparte del intérprete.
apt install -y python3 python3-venv python3-dev

# Guarda por si el servidor se aprovisionó con una versión anterior de
# Ubuntu: CLAUDE.md exige 3.11+, y varias dependencias del proyecto no
# instalan en 3.10 o menos. Mejor frenar acá, con el número a la vista,
# que fallar a mitad del pip install con un error de compilación.
PY_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [ "$(printf '%s\n3.11\n' "${PY_VERSION}" | sort -V | head -1)" != "3.11" ]; then
    echo "ERROR: este servidor trae Python ${PY_VERSION} y RestoMind necesita 3.11 o superior."
    echo "       Reaprovisioná el VPS con Ubuntu 24.04 (trae 3.12) — ver deploy/RUNBOOK.md."
    exit 1
fi
echo "    Python ${PY_VERSION} OK"

echo "==> Instalando Nginx, certbot, git, build-essential, sqlite3, ufw"
# build-essential + sqlite3: por si algún paquete de requirements.txt no
# trae wheel prearmado para esta arquitectura, y para el backup con
# `sqlite3 ... .backup` (ver deploy/backup_db.sh).
apt install -y nginx certbot python3-certbot-nginx git build-essential sqlite3 ufw

echo "==> Instalando Docker (para el contenedor sunat-service)"
# Desde v4.0 la emisión SUNAT vive en un contenedor aparte, porque sunat-py
# fija cryptography<45 y el backend usa la 50 (ver docker-compose.yml). Sin
# Docker el backend arranca igual, pero el primer cobro con boleta muere con
# SunatCloudError — un fallo que aparece recién con un comensal esperando.
#
# Se usan los paquetes de Ubuntu y no el repositorio de docker.com por el
# mismo criterio que hizo elegir el Python del sistema en vez del PPA de
# deadsnakes: una dependencia externa menos en el arranque de cada servidor.
apt install -y docker.io docker-compose-v2
systemctl enable --now docker

# NOTA DELIBERADA: el usuario '${APP_USER}' NO se agrega al grupo 'docker'.
# Ese grupo equivale a root (quien puede crear un contenedor puede montar /
# y salir del aislamiento), así que sumarlo anularía el motivo por el que el
# script crea un usuario sin privilegios. `docker compose` se corre como
# root desde ${APP_DIR}; 'restart: unless-stopped' lo devuelve solo tras un
# reinicio, sin que nadie tenga que entrar al servidor.

echo "==> Configurando el firewall (ufw)"
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "==> Creando usuario de sistema sin privilegios '${APP_USER}'"
if ! id "${APP_USER}" &>/dev/null; then
    adduser --system --group --home "/home/${APP_USER}" --shell /bin/bash "${APP_USER}"
fi

echo "==> Clonando el repo en ${APP_DIR}"
if [ ! -d "${APP_DIR}" ]; then
    sudo -u "${APP_USER}" git clone "${REPO_URL}" "${APP_DIR}"
else
    echo "    ${APP_DIR} ya existe, se omite el clone (usá deploy/deploy.sh para actualizar)"
fi

echo "==> Creando entorno virtual e instalando dependencias"
sudo -u "${APP_USER}" python3 -m venv "${APP_DIR}/venv"
sudo -u "${APP_USER}" "${APP_DIR}/venv/bin/pip" install --upgrade pip
sudo -u "${APP_USER}" "${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

echo "==> Preparando .env de producción"
if [ ! -f "${APP_DIR}/.env" ]; then
    sudo -u "${APP_USER}" cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
    sudo -u "${APP_USER}" sed -i \
        -e 's/^ENVIRONMENT=.*/ENVIRONMENT=production/' \
        -e 's/^DEBUG=.*/DEBUG=false/' \
        -e 's|^SECRET_KEY=.*|SECRET_KEY=TODO_GENERAR_CON_python_-c_"import secrets; print(secrets.token_urlsafe(48))"|' \
        -e 's|^CORS_ORIGINS=.*|CORS_ORIGINS=["https://TODO_TU_DOMINIO"]|' \
        "${APP_DIR}/.env"
    chmod 600 "${APP_DIR}/.env"
    chown "${APP_USER}:${APP_USER}" "${APP_DIR}/.env"
    echo ""
    echo "    ⚠️  ${APP_DIR}/.env creado con placeholders TODO_*."
    echo "    ⚠️  Completalo a mano ANTES de arrancar el servicio (ver deploy/RUNBOOK.md)."
else
    echo "    ${APP_DIR}/.env ya existe, no se toca."
fi

echo "==> Instalando el servicio systemd"
cp "${APP_DIR}/deploy/restomind.service" /etc/systemd/system/restomind.service
systemctl daemon-reload
systemctl enable restomind

echo ""
echo "==> Bootstrap completo. Pasos que faltan (ver deploy/RUNBOOK.md):"
echo "    1. Completar los TODO_* en ${APP_DIR}/.env"
echo "    2. sudo systemctl start restomind"
echo "    3. Configurar Nginx con deploy/nginx.conf.template"
echo "    4. certbot --nginx -d TU_DOMINIO"
