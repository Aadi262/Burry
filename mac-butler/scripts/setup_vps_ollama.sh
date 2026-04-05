#!/bin/bash
# Run this ON your VPS (not your Mac)
# ssh user@your-vps, then run this script
# Sets up Ollama as a persistent HTTP server

set -euo pipefail

AUTH_USER="${OLLAMA_BASIC_AUTH_USER:-butler}"
AUTH_PASS="${OLLAMA_BASIC_AUTH_PASS:-}"
PROXY_PORT="${OLLAMA_PROXY_PORT:-8765}"
OLLAMA_HOST_PORT="${OLLAMA_HOST_PORT:-11434}"
OLLAMA_NUM_PARALLEL="${OLLAMA_NUM_PARALLEL:-1}"
OLLAMA_MAX_LOADED_MODELS="${OLLAMA_MAX_LOADED_MODELS:-1}"
SWAP_SIZE_GB="${OLLAMA_SWAP_GB:-8}"

echo "=== Setting up Ollama on VPS ==="

# This VPS has 8 GB RAM and other resident apps. Add swap if none exists so
# the larger model has headroom instead of killing existing containers.
if [ "$(swapon --show | wc -l | tr -d ' ')" = "0" ] && [ ! -f /swapfile ]; then
    echo "Creating ${SWAP_SIZE_GB}G swapfile..."
    fallocate -l "${SWAP_SIZE_GB}G" /swapfile || dd if=/dev/zero of=/swapfile bs=1G count="${SWAP_SIZE_GB}"
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

if ss -tulpn | grep -q ":${PROXY_PORT}\\b"; then
    echo "Port ${PROXY_PORT} is already in use"
    exit 1
fi

if ! command -v ollama &> /dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh
    echo "Ollama installed"
else
    echo "Ollama already installed"
fi

echo "Pulling Qwen 14B (main orchestrator)..."
ollama pull qwen2.5:14b

echo "Pulling specialist models..."
ollama pull deepseek-r1:7b
ollama pull qwen2.5-coder:7b
ollama pull phi4-mini
ollama pull llama3.2:3b

mkdir -p /etc/systemd/system/ollama.service.d
cat > /etc/systemd/system/ollama.service.d/butler.conf << EOF
[Service]
Environment="OLLAMA_NUM_PARALLEL=${OLLAMA_NUM_PARALLEL}"
Environment="OLLAMA_MAX_LOADED_MODELS=${OLLAMA_MAX_LOADED_MODELS}"
EOF

systemctl daemon-reload
systemctl disable --now ollama-server.service 2>/dev/null || true
systemctl enable ollama.service
systemctl restart ollama.service

echo "Ollama server running on port 11434"
echo "Test with: curl http://localhost:11434/api/tags"

apt-get update
apt-get install -y nginx apache2-utils curl

if [ -n "${AUTH_PASS}" ]; then
    echo "Setting up auth from OLLAMA_BASIC_AUTH_PASS"
    htpasswd -bc /etc/nginx/.ollama_passwd "${AUTH_USER}" "${AUTH_PASS}"
else
    echo "Setting up auth (choose a password when prompted):"
    htpasswd -c /etc/nginx/.ollama_passwd "${AUTH_USER}"
fi

cat > /etc/nginx/sites-available/ollama << 'NGINX'
server {
    listen 8765;

    location /ollama/ {
        auth_basic "Butler API";
        auth_basic_user_file /etc/nginx/.ollama_passwd;

        proxy_pass http://127.0.0.1:11434/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
        client_max_body_size 10m;
    }

    location /health {
        return 200 'ok';
        add_header Content-Type text/plain;
    }
}
NGINX

ln -sf /etc/nginx/sites-available/ollama /etc/nginx/sites-enabled/ollama
sed -i "s/listen 8765;/listen ${PROXY_PORT};/" /etc/nginx/sites-available/ollama
nginx -t
systemctl enable nginx
systemctl restart nginx

echo ""
echo "=== VPS setup complete ==="
echo "Ollama API: http://YOUR_VPS_IP:${PROXY_PORT}/ollama/"
echo "Health check: http://YOUR_VPS_IP:${PROXY_PORT}/health"
echo ""
echo "Now add to butler_config.py on your Mac:"
echo "  VPS_OLLAMA_URL = 'http://YOUR_VPS_IP:${PROXY_PORT}/ollama'"
echo "  VPS_OLLAMA_USER = '${AUTH_USER}'"
echo "  VPS_OLLAMA_PASS = ''  # keep the password in secrets/local_secrets.json"
echo "  USE_VPS_OLLAMA = True"
echo ""
echo "Save the password locally under:"
echo '  {"ollama": {"user": "'"${AUTH_USER}"'", "password": "<password>"}}'
