# Manual VPS Deployment Guide

## Server Information
- **IP**: 185.70.196.55
- **OS**: Ubuntu 24.04 LTS (Noble Numbat)
- **Hostname**: ubuntu-1cpu-2gb-pl-waw1
- **Server Name**: Automatic Stock Market Bot

## Step 1: SSH Connection Setup

You'll need to connect to your server manually first. The server requires password authentication.

### Connect to your VPS:
```bash
ssh root@185.70.196.55
```

When prompted:
1. Type "yes" to accept the SSH fingerprint
2. Enter the root password provided by your hosting provider

## Step 2: Upload Project Files

Once connected, you have two options:

### Option A: Clone from Git (if you have a repository)
```bash
git clone <your-repo-url> /tmp/trading-bot-deploy
```

### Option B: Manual File Upload (recommended)
On your local machine, run:
```bash
# Upload project files using rsync or scp
rsync -avz --progress \
    --exclude='venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.git/' \
    --exclude='node_modules/' \
    --exclude='logs/' \
    --exclude='*.log' \
    ./ root@185.70.196.55:/tmp/trading-bot-deploy/
```

Or use scp:
```bash
scp -r . root@185.70.196.55:/tmp/trading-bot-deploy/
```

## Step 3: Run VPS Initialization

After uploading files, connect to your server and run:

```bash
ssh root@185.70.196.55
cd /tmp/trading-bot-deploy
chmod +x init_vps.sh deploy_helper.sh
./init_vps.sh
```

## Step 4: Deploy Application

```bash
./deploy_helper.sh full
```

## Step 5: Configure Environment

```bash
# Edit environment variables
nano /opt/trading-bot/.env

# Add your API keys:
# OPENAI_API_KEY=your_openai_key
# BINANCE_API_KEY=your_binance_key
# etc.
```

## Step 6: Start Services

```bash
systemctl start trading-bot-api trading-bot trading-bot-monitor
systemctl status trading-bot-api
```

## Step 7: Test Deployment

```bash
curl http://localhost:8000/health
curl http://185.70.196.55:8000/health
```

## Alternative: Interactive Deployment Script

I'll create an interactive deployment script that handles password authentication.
