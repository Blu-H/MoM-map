#!/usr/bin/env bash
# Sets up the MoM map viewer on a fresh Linux server.
# Installs: miniconda + mom-map env, nginx (static files only).
# Usage: ./setup.sh [--url http://YOUR_IP_OR_DOMAIN]

set -e
set -o pipefail

############################
# CONFIG
############################

REPO_URL="https://github.com/KatKatKateryna/MoMProduction.git"
REPO_BRANCH="interactive-map_pmtiles"
REPO_DIR="$HOME/MoMProduction"
MODULE_DIR="$REPO_DIR/map_viewer"
DATA_DIR="$REPO_DIR/data"

if command -v conda >/dev/null 2>&1; then
    CONDA_DIR="$(conda info --base)"
else
    CONDA_DIR="$HOME/miniconda3"
fi
CONDA_ENV_NAME="mom-map"
MINICONDA_INSTALLER="Miniconda3-latest-Linux-x86_64.sh"
MINICONDA_URL="https://repo.anaconda.com/miniconda/$MINICONDA_INSTALLER"

SERVICE_NAME="mom-map"
NGINX_SITE="mom-map"
LOG_DIR="/var/log/mom-map"

############################
# ARGUMENTS
############################

PUBLIC_URL=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --url) PUBLIC_URL="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

if [[ -z "$PUBLIC_URL" ]]; then
    # Auto-detect public IP
    PUBLIC_IP=$(curl -sf https://api.ipify.org || curl -sf https://ifconfig.me || echo "")
    if [[ -n "$PUBLIC_IP" ]]; then
        PUBLIC_URL="http://${PUBLIC_IP}"
        echo "Auto-detected public URL: $PUBLIC_URL"
    else
        echo "ERROR: Could not detect public IP. Pass --url http://YOUR_IP_OR_DOMAIN"
        exit 1
    fi
fi

echo "Public URL: $PUBLIC_URL"

############################
# SYSTEM PACKAGES
############################

echo "Installing system packages..."
sudo apt update -y
sudo DEBIAN_FRONTEND=noninteractive apt install -y \
    curl \
    git \
    wget \
    nginx

############################
# REPOSITORY
############################

if [ ! -d "$REPO_DIR/.git" ]; then
    echo "Cloning repository..."
    git clone --branch "$REPO_BRANCH" --single-branch --depth 1 "$REPO_URL" "$REPO_DIR"
else
    echo "Repository exists. Updating..."
    cd "$REPO_DIR"
    git fetch origin
    git reset --hard "origin/$REPO_BRANCH"
fi

############################
# MINICONDA
############################

if [ ! -d "$CONDA_DIR" ]; then
    echo "Installing Miniconda..."
    cd "$HOME"
    [ ! -f "$MINICONDA_INSTALLER" ] && wget "$MINICONDA_URL"
    bash "$MINICONDA_INSTALLER" -b -p "$CONDA_DIR"
fi

"$CONDA_DIR/bin/conda" init bash || true
source "$CONDA_DIR/etc/profile.d/conda.sh"
"$CONDA_DIR/bin/conda" tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main || true
"$CONDA_DIR/bin/conda" tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r   || true

conda config --add channels conda-forge || true
conda config --set channel_priority strict

############################
# CONDA ENV
############################

cd "$MODULE_DIR"

if conda env list | grep -q "^$CONDA_ENV_NAME "; then
    echo "Updating conda env $CONDA_ENV_NAME..."
    conda env update -n "$CONDA_ENV_NAME" -f environment.yml --prune
else
    echo "Creating conda env $CONDA_ENV_NAME..."
    conda env create -n "$CONDA_ENV_NAME" -f environment.yml
fi

conda activate "$CONDA_ENV_NAME"

############################
# INITIAL TILE GENERATION
############################

echo "Generating initial PMTiles..."
mkdir -p "$LOG_DIR"
"$CONDA_DIR/envs/$CONDA_ENV_NAME/bin/python" "$MODULE_DIR/update_tiles.py" --once \
    2>&1 | tee "$LOG_DIR/tiles_init.log"

############################
# SYSTEMD TIMER (hourly CSV check)
############################

echo "Installing systemd timer for 30-minute tile updates..."
PYTHON="$CONDA_DIR/envs/$CONDA_ENV_NAME/bin/python"

sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null <<SERVICE
[Unit]
Description=MoM map viewer — update PMTiles from latest CSV
After=network.target

[Service]
Type=oneshot
User=${USER}
WorkingDirectory=${MODULE_DIR}
ExecStart=${PYTHON} ${MODULE_DIR}/update_tiles.py --once
StandardOutput=append:${LOG_DIR}/update.log
StandardError=append:${LOG_DIR}/update.log
SERVICE

sudo tee /etc/systemd/system/${SERVICE_NAME}.timer > /dev/null <<TIMER
[Unit]
Description=MoM map viewer — 30-minute CSV check

[Timer]
OnBootSec=5min
OnUnitActiveSec=30min
Persistent=true

[Install]
WantedBy=timers.target
TIMER

sudo systemctl daemon-reload
sudo systemctl enable  "${SERVICE_NAME}.timer"
sudo systemctl start   "${SERVICE_NAME}.timer"

############################
# NGINX
############################

echo "Configuring nginx..."
sudo tee /etc/nginx/sites-available/${NGINX_SITE} > /dev/null <<NGINX
server {
    listen 80;
    server_name _;

    root ${MODULE_DIR};
    index map.html;

    location / {
        try_files \$uri /map.html;
    }

    # PMTiles and metadata — static files, enable range requests
    location /data/ {
        add_header Accept-Ranges bytes;
        try_files \$uri =404;
    }
}
NGINX

sudo ln -sf /etc/nginx/sites-available/${NGINX_SITE} /etc/nginx/sites-enabled/${NGINX_SITE}
sudo rm -f /etc/nginx/sites-enabled/default

sudo nginx -t
sudo systemctl enable  nginx
sudo systemctl restart nginx

############################
# DONE
############################

echo ""
echo "======================================"
echo "Map viewer setup complete."
echo "Open in browser: ${PUBLIC_URL}"
echo ""
echo "Tile update timer:"
echo "  sudo systemctl status  ${SERVICE_NAME}.timer"
echo "  sudo systemctl list-timers ${SERVICE_NAME}.timer"
echo "  sudo journalctl -u ${SERVICE_NAME}.service -f"
echo ""
echo "Logs: ${LOG_DIR}/"
echo "======================================"