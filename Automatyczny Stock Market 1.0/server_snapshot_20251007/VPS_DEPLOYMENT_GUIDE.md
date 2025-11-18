# VPS Deployment Guide for Trading Bot - UPDATED

## 🚀 **CURRENT DEPLOYMENT STATUS**

### 🌐 **VPS Information:**
- **IP Address**: 185.70.196.214 (UPDATED)
- **Authentication**: SSH Key Only
- **Expected Fingerprint**: SHA256:e5b7EB06IiR3BcLaBUm2fhDpptU5VXX3xf4h8cv56xI
- **Your SSH Key**: ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJse5FI4ZPuXQvtL7eqqKvCEGPr2FgQzQRW1CfxjWasr f.sliwa@nowybankpolski.pl

## Overview

This guide provides step-by-step instructions for deploying the automated trading bot on a VPS (Virtual Private Server). The deployment includes a complete production-ready setup with multi-user support, real-time streaming, AI analysis, and enterprise-grade security.

## Prerequisites

### Server Requirements

**Minimum Requirements:**
- **OS**: Ubuntu 20.04+ or Debian 11+ (64-bit)
- **RAM**: 2GB (4GB recommended)
- **Storage**: 20GB SSD (50GB recommended)
- **CPU**: 1 vCPU (2+ recommended)
- **Network**: 1Gbps connection

**Recommended VPS Providers:**
- DigitalOcean (Droplet)
- Linode
- Vultr
- AWS EC2
- Google Cloud Platform
- Microsoft Azure

### Domain and DNS (Optional)

If you want to use a custom domain:
1. Purchase a domain name
2. Point A record to your VPS IP address
3. Configure DNS propagation (may take 24-48 hours)

## 🎯 **IMMEDIATE NEXT STEPS**

### 1. 🔑 **SSH Key Setup (REQUIRED)**
**PRZED KONTYNUACJĄ:** Dodaj swój klucz SSH do panelu VPS!

```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJse5FI4ZPuXQvtL7eqqKvCEGPr2FgQzQRW1CfxjWasr f.sliwa@nowybankpolski.pl
```

**Instrukcje:**
1. Zaloguj się do panelu VPS
2. Przejdź do sekcji SSH Keys / Klucze SSH
3. Dodaj powyższy klucz publiczny
4. Zrestartuj VPS jeśli wymagane

### 2. ✅ **Verify SSH Connection**

```bash
ssh root@185.70.196.214
```

Expected fingerprint: `SHA256:e5b7EB06IiR3BcLaBUm2fhDpptU5VXX3xf4h8cv56xI`

### 3. 🚀 **Automated Deployment**

```bash
# Run automated deployment script
./auto_deploy_with_ssh.sh
```

## Quick Start

### 2. Download and Run Installation Script

```bash
# Download the trading bot code
git clone <your-repository-url> /tmp/trading-bot
cd /tmp/trading-bot

# Run the VPS initialization script
sudo ./init_vps.sh

# For custom domain with SSL:
sudo ./init_vps.sh --domain your-domain.com

# For PostgreSQL instead of SQLite:
sudo ./init_vps.sh --postgresql

# To skip Nginx (if you have your own reverse proxy):
sudo ./init_vps.sh --no-nginx
```

### 3. Deploy Project Files

```bash
# Run deployment helper
sudo ./deploy_helper.sh full
```

### 4. Configure API Keys

```bash
# Edit environment file
sudo nano /opt/trading-bot/.env

# Add your API keys:
# OPENAI_API_KEY=your_openai_key
# BINANCE_API_KEY=your_binance_key
# BINANCE_SECRET_KEY=your_binance_secret
# (etc.)
```

### 5. Restart Services

```bash
sudo systemctl restart trading-bot-api trading-bot trading-bot-monitor
```

### 6. Verify Installation

```bash
# Check service status
sudo systemctl status trading-bot-api

# Test API endpoints
curl http://185.70.196.214:8000/health
```

## Detailed Installation Steps

### Step 1: VPS Setup and Initial Configuration

1. **Create VPS Instance**
   - Choose Ubuntu 20.04+ LTS
   - Select appropriate size (minimum 2GB RAM)
   - Configure SSH key authentication
   - Note the public IP address

2. **Initial Server Setup**
   ```bash
   # Update system
   sudo apt update && sudo apt upgrade -y
   
   # Create non-root user (optional but recommended)
   sudo adduser deployer
   sudo usermod -aG sudo deployer
   
   # Configure SSH key for new user
   sudo mkdir /home/deployer/.ssh
   sudo cp ~/.ssh/authorized_keys /home/deployer/.ssh/
   sudo chown -R deployer:deployer /home/deployer/.ssh
   sudo chmod 700 /home/deployer/.ssh
   sudo chmod 600 /home/deployer/.ssh/authorized_keys
   ```

### Step 2: Run VPS Initialization Script

The `init_vps.sh` script automates the entire server setup:

```bash
# Basic installation
sudo ./init_vps.sh

# With custom domain and SSL
sudo ./init_vps.sh --domain yourdomain.com

# With PostgreSQL database
sudo ./init_vps.sh --postgresql

# Without Nginx (if using external load balancer)
sudo ./init_vps.sh --no-nginx
```

**What the script does:**
- Installs Python 3.11, Node.js, Redis, Nginx
- Creates dedicated service user (`tradingbot`)
- Sets up project directory (`/opt/trading-bot`)
- Creates systemd service files
- Configures firewall and security
- Sets up log rotation and backups
- Generates SSL certificates (if domain provided)

### Step 3: Deploy Application Code

```bash
# Copy your project files to the server
scp -r ./your-project/* root@185.70.196.214:/tmp/trading-bot/

# Or clone from git repository
git clone https://github.com/your-username/trading-bot.git /tmp/trading-bot

# Run deployment helper
cd /tmp/trading-bot
sudo ./deploy_helper.sh full
```

### Step 4: Environment Configuration

1. **Edit Environment File**
   ```bash
   sudo nano /opt/trading-bot/.env
   ```

2. **Required Configuration**
   ```env
   # Security (auto-generated)
   JWT_SECRET=auto_generated_secret
   SECRET_KEY=auto_generated_secret
   
   # AI APIs
   OPENAI_API_KEY=your_openai_api_key
   ANTHROPIC_API_KEY=your_anthropic_api_key
   
   # Exchange APIs
   BINANCE_API_KEY=your_binance_api_key
   BINANCE_SECRET_KEY=your_binance_secret_key
   BINANCE_TESTNET=true
   
   BYBIT_API_KEY=your_bybit_api_key
   BYBIT_SECRET_KEY=your_bybit_secret_key
   BYBIT_TESTNET=true
   
   PRIMEXBT_API_KEY=your_primexbt_api_key
   PRIMEXBT_SECRET_KEY=your_primexbt_secret_key
   
   # Notifications (optional)
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   TELEGRAM_CHAT_ID=your_telegram_chat_id
   
   SMTP_SERVER=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USERNAME=your_email@gmail.com
   SMTP_PASSWORD=your_app_password
   FROM_EMAIL=your_email@gmail.com
   ```

### Step 5: Database Setup

```bash
# Initialize database
sudo -u tradingbot bash -c "cd /opt/trading-bot && source venv/bin/activate && python init_database.py"

# Add demo data (optional)
sudo -u tradingbot bash -c "cd /opt/trading-bot && source venv/bin/activate && python initialize_demo_data.py"
```

### Step 6: Start Services

```bash
# Enable services to start on boot
sudo systemctl enable trading-bot-api trading-bot trading-bot-monitor

# Start services
sudo systemctl start trading-bot-api
sudo systemctl start trading-bot
sudo systemctl start trading-bot-monitor

# Check status
sudo systemctl status trading-bot-api
```

### Step 7: Configure Nginx (if using domain)

```bash
# Edit Nginx configuration
sudo nano /etc/nginx/sites-available/trading-bot

# Update server_name with your domain
server_name yourdomain.com www.yourdomain.com;

# Test configuration
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx
```

### Step 8: SSL Certificate Setup

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx

# Get SSL certificate
sudo certbot --nginx -d yourdomain.com

# Test auto-renewal
sudo certbot renew --dry-run
```

## Configuration Options

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `JWT_SECRET` | Secret for JWT tokens | Yes |
| `SECRET_KEY` | Application secret key | Yes |
| `OPENAI_API_KEY` | OpenAI API key for AI analysis | Yes |
| `ANTHROPIC_API_KEY` | Anthropic API key (optional) | No |
| `BINANCE_API_KEY` | Binance exchange API key | No |
| `BINANCE_SECRET_KEY` | Binance exchange secret | No |
| `BYBIT_API_KEY` | Bybit exchange API key | No |
| `BYBIT_SECRET_KEY` | Bybit exchange secret | No |
| `PRIMEXBT_API_KEY` | PrimeXBT exchange API key | No |
| `PRIMEXBT_SECRET_KEY` | PrimeXBT exchange secret | No |
| `TELEGRAM_BOT_TOKEN` | Telegram bot for notifications | No |
| `TELEGRAM_CHAT_ID` | Telegram chat ID | No |
| `SMTP_SERVER` | Email server for notifications | No |
| `SMTP_USERNAME` | Email username | No |
| `SMTP_PASSWORD` | Email password | No |

### Service Configuration

#### API Service (`trading-bot-api`)
- **Port**: 8000
- **Purpose**: Web interface and REST API
- **Health Check**: `http://localhost:8000/health`

#### Trading Bot (`trading-bot`)
- **Purpose**: Core trading logic and automation
- **Logs**: `/opt/trading-bot/logs/trading.log`

#### Monitor Service (`trading-bot-monitor`)
- **Purpose**: System monitoring and alerts
- **Health Check**: Internal health checks

### Database Configuration

#### SQLite (Default)
- **File**: `/opt/trading-bot/trading.db`
- **Backup**: Automatic daily backups
- **Performance**: Suitable for up to 1000 concurrent users

#### PostgreSQL (Optional)
- **Database**: `trading_bot`
- **User**: `tradingbot`
- **Port**: 5432
- **Performance**: Suitable for unlimited users

## Security Configuration

### Firewall Rules

```bash
# Check firewall status
sudo ufw status

# Default rules applied by init script:
# - Allow SSH (port 22)
# - Allow HTTP (port 80)
# - Allow HTTPS (port 443)
# - Block all other external access
# - Allow localhost access to Redis and monitoring
```

### File Permissions

```bash
# Check important file permissions
ls -la /opt/trading-bot/.env          # Should be 600 (tradingbot:tradingbot)
ls -la /opt/trading-bot/trading.db    # Should be 644 (tradingbot:tradingbot)
ls -ld /opt/trading-bot/              # Should be 755 (tradingbot:tradingbot)
```

### SSL/TLS Configuration

- **Certificate Provider**: Let's Encrypt (free)
- **Auto-renewal**: Configured via cron job
- **Cipher Suites**: Modern, secure configurations
- **HSTS**: Enabled for security

## Monitoring and Maintenance

### Health Checks

```bash
# Run manual health check
sudo /opt/trading-bot/health_check.sh

# Check system status
sudo systemctl status trading-bot-api trading-bot trading-bot-monitor

# View logs
sudo journalctl -u trading-bot-api -f
```

### Log Files

| Service | Log Location |
|---------|--------------|
| API Server | `/opt/trading-bot/logs/app.log` |
| Trading Bot | `/opt/trading-bot/logs/trading.log` |
| Monitor | `/opt/trading-bot/logs/monitor.log` |
| Nginx | `/var/log/nginx/access.log` |
| System | `journalctl -u trading-bot-api` |

### Backup and Recovery

```bash
# Manual backup
sudo /opt/trading-bot/backup.sh

# List backups
ls -la /opt/trading-bot/backups/

# Restore from backup
sudo tar -xzf /opt/trading-bot/backups/trading_bot_backup_YYYYMMDD_HHMMSS.tar.gz -C /opt/trading-bot/
```

### Performance Monitoring

```bash
# Check resource usage
htop
iotop
df -h

# Check API performance
curl -w "@curl-format.txt" -o /dev/null -s http://localhost:8000/health

# Monitor WebSocket connections
netstat -an | grep :8000 | grep ESTABLISHED | wc -l
```

## Troubleshooting

### Common Issues

#### 1. Service Won't Start

```bash
# Check service status
sudo systemctl status trading-bot-api

# Check logs
sudo journalctl -u trading-bot-api -n 50

# Common causes:
# - Missing environment variables
# - Database connection issues
# - Port conflicts
# - Permission problems
```

#### 2. API Not Accessible

```bash
# Check if port is listening
sudo netstat -tlnp | grep :8000

# Check firewall
sudo ufw status

# Check Nginx configuration
sudo nginx -t
sudo systemctl status nginx
```

#### 3. Database Issues

```bash
# Check database file permissions
ls -la /opt/trading-bot/trading.db

# Reinitialize database
sudo -u tradingbot bash -c "cd /opt/trading-bot && source venv/bin/activate && python init_database.py"
```

#### 4. SSL Certificate Problems

```bash
# Check certificate status
sudo certbot certificates

# Renew certificate manually
sudo certbot renew

# Check Nginx SSL configuration
sudo nginx -t
```

### Debug Mode

To enable debug mode for troubleshooting:

```bash
# Edit environment file
sudo nano /opt/trading-bot/.env

# Change DEBUG setting
DEBUG=true
LOG_LEVEL=DEBUG

# Restart services
sudo systemctl restart trading-bot-api trading-bot trading-bot-monitor
```

### Getting Support

1. **Check Logs**: Always check logs first
2. **Verify Configuration**: Ensure all required environment variables are set
3. **Test API**: Use curl to test individual endpoints
4. **Check Resources**: Monitor CPU, memory, and disk usage
5. **Review Security**: Ensure firewall and permissions are correct

## Performance Optimization

### System-Level Optimizations

```bash
# Apply performance tuning
sudo /opt/trading-bot/tune_performance.sh

# Monitor system performance
htop
iotop
iostat 1
```

### Application-Level Optimizations

1. **Database Optimization**
   - Use indexes for frequently queried data
   - Regular database maintenance
   - Consider PostgreSQL for high traffic

2. **Caching**
   - Redis for session and data caching
   - API response caching
   - Static file caching via Nginx

3. **Connection Pooling**
   - Database connection pooling
   - HTTP connection reuse
   - WebSocket connection management

### Scaling Considerations

#### Vertical Scaling (Single Server)
- Increase RAM (up to 8GB recommended)
- Add CPU cores (up to 4 cores recommended)
- Use SSD storage
- Optimize database

#### Horizontal Scaling (Multiple Servers)
- Load balancer (Nginx, HAProxy)
- Database replication
- Redis clustering
- Microservices architecture

## Maintenance Schedule

### Daily
- [ ] Check service status
- [ ] Review error logs
- [ ] Monitor system resources

### Weekly
- [ ] Review performance metrics
- [ ] Check backup integrity
- [ ] Update system packages
- [ ] Review security logs

### Monthly
- [ ] Rotate API keys
- [ ] Update application dependencies
- [ ] Performance optimization review
- [ ] Disaster recovery testing

## Production Checklist

Before going live with real trading:

- [ ] SSL certificate installed and working
- [ ] All API keys configured and tested
- [ ] Firewall properly configured
- [ ] Backup system working
- [ ] Monitoring and alerting configured
- [ ] Performance testing completed
- [ ] Security audit performed
- [ ] Documentation updated
- [ ] Team training completed
- [ ] Emergency procedures documented

## Support and Resources

- **Documentation**: Check project README files
- **Logs**: Always check application and system logs
- **Community**: GitHub issues and discussions
- **Professional Support**: Consider hiring DevOps consultant for complex setups

---

## Quick Reference Commands

```bash
# Service Management
sudo systemctl status trading-bot-api
sudo systemctl restart trading-bot-api
sudo systemctl enable trading-bot-api

# Log Viewing
sudo journalctl -u trading-bot-api -f
sudo tail -f /opt/trading-bot/logs/app.log

# Health Checks
curl http://localhost:8000/health
sudo /opt/trading-bot/health_check.sh

# Backup and Restore
sudo /opt/trading-bot/backup.sh
ls /opt/trading-bot/backups/

# SSL Management
sudo certbot certificates
sudo certbot renew

# Database Management
sudo -u tradingbot sqlite3 /opt/trading-bot/trading.db
sudo /opt/trading-bot/backup.sh
```

This deployment guide provides comprehensive instructions for setting up the trading bot on a VPS with enterprise-grade security, monitoring, and performance optimization.
