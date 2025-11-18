#!/bin/bash
set -euo pipefail

# --- Konfiguracja ---
REMOTE_USER="admin"
REMOTE_HOST="185.70.198.201"
REMOTE_APP_DIR="/opt/trading-bot-docker"
LOCAL_SOURCE_DIR="Algorytm Uczenia Kwantowego LLM/"

echo "--- 1. Pakowanie kodu aplikacji ---"
# Opcja dla macOS, aby uniknąć plików ._
export COPYFILE_DISABLE=1
tar -czf /tmp/app_package.tar.gz -C "$LOCAL_SOURCE_DIR" .

echo "--- 2. Wysyłanie paczki na serwer ---"
sshpass -p 'MIlik112' scp /tmp/app_package.tar.gz "${REMOTE_USER}@${REMOTE_HOST}:/tmp/"

echo "--- 3. Uruchamianie skryptu instalacyjnego na serwerze ---"
sshpass -p 'MIlik112' ssh -o StrictHostKeyChecking=no -t "${REMOTE_USER}@${REMOTE_HOST}" "
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

echo '---> 1. Konfiguracja DNS dla demona Docker...'
if [ ! -f /etc/docker/daemon.json ]; then
    echo '{\"dns\": [\"8.8.8.8\", \"8.8.4.4\"]}' | sudo tee /etc/docker/daemon.json
    sudo systemctl restart docker
fi

echo '---> 2. Instalacja Docker i Docker Compose (jeśli potrzebne)...'
if ! command -v docker &> /dev/null; then
    sudo apt-get update -y
    sudo apt-get install -y ca-certificates curl
    sudo install -m 0755 -d /etc/apt/keyrings
    sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    sudo chmod a+r /etc/apt/keyrings/docker.asc
    echo \\
      \"deb [arch=\$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \\
      \$(. /etc/os-release && echo \"\$VERSION_CODENAME\") stable\" | \\
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update -y
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

echo '---> 3. Przygotowanie katalogu aplikacji...'
sudo rm -rf ${REMOTE_APP_DIR}
sudo mkdir -p ${REMOTE_APP_DIR}
sudo tar -xzf /tmp/app_package.tar.gz -C ${REMOTE_APP_DIR}
sudo chown -R admin:admin ${REMOTE_APP_DIR}
cd ${REMOTE_APP_DIR}

echo '---> 4. Tworzenie pliku .env na serwerze...'
cat > .env <<EOF
DATABASE_URL=postgresql+psycopg2://upadmin:AVNS_ynqNx-mSYLQXZiCgbhi@public-automatic-stock-exchange-bot-hhiyptsoiomb.db.upclouddatabases.com:11569/defaultdb?sslmode=require
GEMINI_API_KEY=AIzaSyDX-_pQ1A4xvh1hAL0txS_tXpd1Nh8g0M8
GEMINI_MODEL=gemini-2.5-pro-latest
JWT_SECRET=\$(openssl rand -hex 32)
BACKEND_BASE=http://backend:8009
EOF

echo '---> 5. Budowanie i uruchamianie kontenerów Docker...'
# Najpierw budujemy obrazy, nie uruchamiając ich
sudo docker compose build

echo '---> 5a. Uruchamianie migracji bazy danych...'
# Uruchamiamy jednorazowy kontener backendu, aby wykonać migracje
sudo docker compose run --rm backend alembic upgrade head

# Teraz uruchamiamy wszystkie usługi w tle
sudo docker compose up -d

echo '---> 6. Aktualizacja konfiguracji Nginx...'
sudo cp \"${REMOTE_APP_DIR}/deploy/nginx/ase-bot.live-gateway.conf\" /etc/nginx/sites-available/ase-bot.live
if [ ! -f /etc/nginx/sites-enabled/ase-bot.live ]; then
    sudo ln -s /etc/nginx/sites-available/ase-bot.live /etc/nginx/sites-enabled/
fi
sudo nginx -t
sudo systemctl reload nginx
echo 'Nginx reloaded.'

echo '--- Wdrożenie Docker zakończone pomyślnie! ---'
"

echo "--- 4. Czyszczenie lokalnych plików ---"
rm /tmp/app_package.tar.gz

echo "Gotowe!"
