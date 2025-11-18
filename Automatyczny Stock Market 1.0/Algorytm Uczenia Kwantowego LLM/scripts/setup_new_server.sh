#!/bin/bash
set -euo pipefail

# This script is intended to be run as root on a fresh Ubuntu server.

echo "--- 1. Initial System Setup ---"
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    sudo vim curl git python3 python3-venv python3-pip \
    nginx certbot python3-certbot-nginx \
    build-essential pkg-config libssl-dev \
    fuse3 mergerfs \
    cargo rustc

echo "--- 2. Create Service User and App Directory ---"
if ! id "tradingbot" &>/dev/null; then
    useradd -m -s /bin/bash tradingbot
    usermod -aG sudo tradingbot
    echo "User 'tradingbot' created and added to sudo group."
else
    echo "User 'tradingbot' already exists."
fi

mkdir -p /opt/trading-bot
chown -R tradingbot:tradingbot /opt/trading-bot
chmod -R 775 /opt/trading-bot

echo "--- 3. Disk and MergerFS Setup ---"
# Assuming vdb is the data disk and is safe to format
if [ -b /dev/vdb ]; then
    echo "Formatting /dev/vdb..."
    mkfs.ext4 -F /dev/vdb
    
    mkdir -p /data
    # Add to fstab if not already present
    grep -q '^/dev/vdb' /etc/fstab || echo "/dev/vdb  /data  ext4  defaults,nofail  0  2" >> /etc/fstab
else
    echo "WARN: /dev/vdb not found, skipping data disk setup."
    mkdir -p /data # create it anyway for mergerfs
fi

mkdir -p /root_storage /mnt/storage

# Add bind mount and mergerfs to fstab if not already present
grep -q '/root_storage' /etc/fstab || echo "/  /root_storage  none  bind  0  0" >> /etc/fstab
grep -q 'fuse.mergerfs' /etc/fstab || echo "/root_storage:/data  /mnt/storage  fuse.mergerfs  defaults,allow_other,use_ino,category.create=mfs,moveonenospc=true,minfreespace=10G,fsname=pool,nofail,x-systemd.automount,x-systemd.after=network-online.target  0  0" >> /etc/fstab

# FUSE config for allow_other
grep -q '^user_allow_other' /etc/fuse.conf || echo 'user_allow_other' >> /etc/fuse.conf

echo "Reloading systemd and mounting all filesystems..."
systemctl daemon-reload
mount -a

df -h

echo "--- 4. Nginx Initial Setup (placeholder) ---"
cat > /etc/nginx/sites-available/ase-bot.live <<'NGINX'
server {
    listen 80;
    listen [::]:80;
    server_name ase-bot.live;

    location / {
        return 200 "Server setup complete. Awaiting application deployment.\n";
        add_header Content-Type text/plain;
    }
}
NGINX
ln -sf /etc/nginx/sites-available/ase-bot.live /etc/nginx/sites-enabled/
# remove default site
rm -f /etc/nginx/sites-enabled/default

echo "Testing and restarting Nginx..."
nginx -t
systemctl restart nginx

echo "--- Server Base Setup Finished ---"

