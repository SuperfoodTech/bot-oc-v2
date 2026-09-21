#!/usr/bin/env bash
set -e

# setup.sh - Installer Systemd Service FoodMaster (bot-oc, bot-vb, bot-web)

CURRENT_USER=$(whoami)
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_DIR=$(cd "${SCRIPT_DIR}/.." && pwd)
UV_BIN=$(which uv || echo "/home/${CURRENT_USER}/.cargo/bin/uv")

if [ ! -f "${UV_BIN}" ]; then
  echo "❌ 'uv' tidak ditemukan di sistem. Harap install uv terlebih dahulu: curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

NODE_BIN=$(which node || echo "/home/${CURRENT_USER}/.nvm/versions/node/$(ls /home/${CURRENT_USER}/.nvm/versions/node 2>/dev/null | tail -n 1)/bin/node")
NODE_BIN_DIR=$(dirname "${NODE_BIN}" 2>/dev/null || echo "/usr/local/bin")

echo "=================================================="
echo "🚀 FoodMaster Systemd Service Setup"
echo "=================================================="
echo "User        : ${CURRENT_USER}"
echo "Project Dir : ${PROJECT_DIR}"
echo "uv Binary   : ${UV_BIN}"
echo "Node Binary : ${NODE_BIN}"
echo "=================================================="

# Function to render template
render_service() {
  local service_name="$1"
  local src_file="${SCRIPT_DIR}/${service_name}.service"
  local dest_file="/etc/systemd/system/${service_name}.service"

  if [ ! -f "${src_file}" ]; then
    echo "❌ Template ${src_file} tidak ditemukan!"
    return 1
  fi

  echo "⚙️ Memproses ${service_name}.service..."
  sed -e "s|%USER%|${CURRENT_USER}|g" \
      -e "s|%PROJECT_DIR%|${PROJECT_DIR}|g" \
      -e "s|%UV_BIN%|${UV_BIN}|g" \
      -e "s|%NODE_BIN%|${NODE_BIN}|g" \
      -e "s|%NODE_BIN_DIR%|${NODE_BIN_DIR}|g" \
      "${src_file}" | sudo tee "${dest_file}" > /dev/null

  sudo chmod 644 "${dest_file}"
  echo "✅ Terpasang di ${dest_file}"
}

# Install all services
render_service "bot-oc"
render_service "bot-vb"
render_service "bot-web"
render_service "bot-wa"

echo "🔄 Menjalankan systemctl daemon-reload..."
sudo systemctl daemon-reload

echo ""
echo "🎉 Setup selesai! Gunakan perintah berikut untuk mengelola service:"
echo ""
echo "▶️ Menjalankan service:"
echo "   sudo systemctl start bot-oc"
echo "   sudo systemctl start bot-vb"
echo "   sudo systemctl start bot-web"
echo "   sudo systemctl start bot-wa"
echo ""
echo "🔁 Auto-start saat boot server:"
echo "   sudo systemctl enable bot-oc bot-vb bot-web bot-wa"
echo ""
echo "📊 Melihat status service:"
echo "   sudo systemctl status bot-wa"
echo ""
echo "📜 Melihat real-time log:"
echo "   journalctl -u bot-wa -f"
echo "=================================================="

