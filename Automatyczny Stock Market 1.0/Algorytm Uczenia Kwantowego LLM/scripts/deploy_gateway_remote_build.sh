#!/bin/bash
set -euo pipefail

REMOTE_USER="admin"
REMOTE_HOST="185.70.198.201"
REMOTE_DIR="/opt/trading-bot/gateway"
LOCAL_SOURCE_DIR="Algorytm Uczenia Kwantowego LLM/gateway"
PACKAGE_NAME="gateway_source.tar.gz"

echo "--- 1. Packaging gateway source code ---"
# Use COPYFILE_DISABLE to avoid including ._ AppleDouble files in tarball
# Exclude Cargo.lock to allow the server's cargo to resolve dependencies
COPYFILE_DISABLE=1 tar -czf "/tmp/$PACKAGE_NAME" -C "$LOCAL_SOURCE_DIR" --exclude 'Cargo.lock' .

echo "--- 2. Uploading package to server: $REMOTE_HOST ---"
sshpass -p 'MIlik112' scp -o StrictHostKeyChecking=no "/tmp/$PACKAGE_NAME" "${REMOTE_USER}@${REMOTE_HOST}:/tmp/"

echo "--- 3. Executing remote build and setup script ---"
sshpass -p 'MIlik112' ssh -o StrictHostKeyChecking=no -t "${REMOTE_USER}@${REMOTE_HOST}" "
    set -euo pipefail
    
    echo '---> Rebuilding gateway in home directory to ensure clean environment...'
    cd ~
    rm -rf gateway_build
    mkdir gateway_build
    cd gateway_build
    
    echo '---> Unpacking source code...'
    tar -xzf /tmp/$PACKAGE_NAME
    
    echo '---> Building Rust application (this may take a few minutes)...'
    cargo build --release
    
    echo '---> Build complete. Moving binary and setting permissions...'
    sudo mv target/release/gateway /opt/trading-bot/gateway/gateway
    sudo chown tradingbot:tradingbot /opt/trading-bot/gateway/gateway
    sudo chmod 775 /opt/trading-bot/gateway/gateway
    
    echo '---> Gateway build and setup complete.'
"

echo "--- 4. Cleaning up local package ---"
rm "/tmp/$PACKAGE_NAME"

echo "--- Full gateway deployment process completed! ---"


