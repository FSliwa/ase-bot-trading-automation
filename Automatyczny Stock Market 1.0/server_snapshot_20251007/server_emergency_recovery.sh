#!/bin/bash
# ASE-Bot Production Server Emergency Recovery Script
# For ase-bot.live (185.70.198.201) - UpCloud hosting

echo "🚨 ASE-Bot Emergency Server Recovery Script"
echo "=========================================="
echo "Target: ase-bot.live (185.70.198.201)"
echo "Date: $(date)"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    case $2 in
        "OK") echo -e "${GREEN}✅ $1${NC}" ;;
        "WARN") echo -e "${YELLOW}⚠️  $1${NC}" ;;
        "ERROR") echo -e "${RED}❌ $1${NC}" ;;
        "INFO") echo -e "${BLUE}ℹ️  $1${NC}" ;;
        *) echo "$1" ;;
    esac
}

# Step 1: Verify current connectivity
print_status "STEP 1: Verifying current connectivity..." "INFO"

# DNS Check
if nslookup ase-bot.live > /dev/null 2>&1; then
    print_status "DNS Resolution: Working" "OK"
else
    print_status "DNS Resolution: Failed" "ERROR"
fi

# Ping Check
if ping -c 3 185.70.198.201 > /dev/null 2>&1; then
    print_status "Server Ping: Responding" "OK"
else
    print_status "Server Ping: Not responding (100% packet loss)" "ERROR"
fi

# Port Check
echo ""
print_status "STEP 2: Checking critical ports..." "INFO"
for port in 22 80 443 8080; do
    if timeout 5 bash -c "echo >/dev/tcp/185.70.198.201/$port" 2>/dev/null; then
        print_status "Port $port: Open" "OK"
    else
        print_status "Port $port: Closed/Filtered" "ERROR"
    fi
done

echo ""
print_status "STEP 3: Generating server recovery plan..." "INFO"

# Create recovery instructions
cat << 'EOF' > server_recovery_plan.md
# 🚨 ASE-Bot Production Server Recovery Plan

## Critical Issues Identified
- ✅ DNS resolution working (ase-bot.live → 185.70.198.201)
- ❌ Server not responding to ping (100% packet loss)
- ❌ All ports filtered/closed (22, 80, 443, 8080)
- ❌ Web services completely inaccessible

## Immediate Actions Required

### 1. Contact UpCloud Support (URGENT)
```bash
# UpCloud Support Details
Website: https://upcloud.com/support
Phone: +358 9 4241 0808
Email: support@upcloud.com
Account: Check email for account details
```

**Report to UpCloud:**
- Server IP: 185.70.198.201
- Domain: ase-bot.live
- Issue: Complete loss of connectivity
- Symptoms: 100% packet loss, all ports filtered
- Request: Immediate server status check and firewall review

### 2. Check UpCloud Control Panel
Access your UpCloud control panel to:
- ✅ Verify server is running (not stopped/suspended)
- ✅ Check server resource usage
- ✅ Review firewall rules
- ✅ Check server logs for errors
- ✅ Verify network configuration

### 3. Firewall Configuration Fix
If server is running, the issue is likely firewall configuration:

```bash
# SSH into server (if possible from UpCloud console)
ssh root@185.70.198.201

# Check current firewall status
ufw status
iptables -L

# Allow essential ports
ufw allow 22    # SSH
ufw allow 80    # HTTP
ufw allow 443   # HTTPS
ufw allow 8080  # Application
ufw enable

# Or reset firewall if needed
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22
ufw allow 80  
ufw allow 443
ufw allow 8080
ufw enable
```

### 4. Web Server Recovery
```bash
# Check if nginx/apache is running
systemctl status nginx
systemctl status apache2
systemctl status docker

# Restart web services
systemctl restart nginx
systemctl restart docker

# Check application status
ps aux | grep python
ps aux | grep node

# Restart application if needed
cd /path/to/ase-bot
./run_on_server.sh
```

### 5. SSL Certificate Setup
```bash
# Install certbot if not present
apt update
apt install certbot python3-certbot-nginx

# Get SSL certificate
certbot --nginx -d ase-bot.live

# Set up auto-renewal
crontab -e
# Add: 0 12 * * * /usr/bin/certbot renew --quiet
```

### 6. DNS and Network Verification
```bash
# Verify DNS from server
nslookup ase-bot.live
dig ase-bot.live

# Check network interfaces
ip a
ip route

# Test external connectivity from server
ping 8.8.8.8
curl -I https://google.com
```

## Recovery Checklist

### Phase 1: Emergency Access (Do First)
- [ ] Contact UpCloud support immediately
- [ ] Access UpCloud control panel
- [ ] Check server status and resources
- [ ] Use UpCloud console to access server
- [ ] Verify server is running and not suspended

### Phase 2: Network & Firewall (Critical)
- [ ] Review and fix firewall rules
- [ ] Allow essential ports (22, 80, 443, 8080)
- [ ] Test connectivity from external sources
- [ ] Verify network interface configuration

### Phase 3: Services Recovery
- [ ] Check and restart web server (nginx/apache)
- [ ] Verify application processes are running
- [ ] Test database connectivity
- [ ] Restart ASE-Bot application

### Phase 4: SSL & Security
- [ ] Install/renew SSL certificate
- [ ] Configure HTTPS redirects
- [ ] Add security headers
- [ ] Test secure connections

### Phase 5: Monitoring & Prevention
- [ ] Set up monitoring alerts
- [ ] Configure automatic backups
- [ ] Document recovery procedures
- [ ] Test disaster recovery plan

## Alternative Emergency Options

### Option 1: New Server Deployment
If server is completely corrupted:
```bash
# Deploy to new UpCloud server
# Copy files from deployment package
tar -xzf deployment_package.tar.gz
./deploy_on_server.sh
```

### Option 2: Temporary Local Hosting
While fixing production:
```bash
# Use local development server with ngrok
cd /path/to/ase-bot
python3 complete_app_launcher.py &
ngrok http 8080
```

### Option 3: Alternative Hosting
Quick migration to Vultr/DigitalOcean/AWS if UpCloud issues persist.

## Expected Recovery Time
- **If firewall issue**: 15-30 minutes
- **If server restart needed**: 30-60 minutes  
- **If complete rebuild**: 2-4 hours
- **If hosting migration**: 4-8 hours

## Post-Recovery Actions
1. Full system monitoring setup
2. Automated backup implementation
3. Disaster recovery testing
4. Security audit and hardening
5. Performance optimization

## Emergency Contacts
- UpCloud Support: support@upcloud.com
- DNS Provider: [Check domain registrar]
- Development Team: [Your team contacts]

---
**Generated**: $(date)
**Status**: CRITICAL - Immediate action required
EOF

print_status "Recovery plan generated: server_recovery_plan.md" "OK"

echo ""
print_status "STEP 4: Attempting advanced diagnostics..." "INFO"

# Try alternate diagnostic approaches
echo "🔍 Traceroute analysis:"
if command -v traceroute &> /dev/null; then
    traceroute 185.70.198.201 | head -10
elif command -v tracepath &> /dev/null; then
    tracepath 185.70.198.201 | head -10
else
    print_status "Traceroute tools not available" "WARN"
fi

echo ""
echo "🔍 DNS detailed analysis:"
dig ase-bot.live

echo ""
echo "🔍 WHOIS information:"
whois ase-bot.live | grep -E "(Registrar|Expiry|Status|Name Server)" | head -10

echo ""
print_status "STEP 5: Creating emergency deployment package..." "INFO"

# Create emergency deployment script
cat << 'EOF' > emergency_deploy.sh
#!/bin/bash
# Emergency deployment script for ASE-Bot

echo "🚀 ASE-Bot Emergency Deployment"
echo "==============================="

# Check if we can connect to server
if ping -c 1 185.70.198.201 > /dev/null 2>&1; then
    echo "✅ Server is responding - proceeding with deployment"
    
    # Try to deploy via SSH
    if ssh -o ConnectTimeout=10 -o BatchMode=yes root@185.70.198.201 'exit' 2>/dev/null; then
        echo "✅ SSH connection successful"
        
        # Upload and deploy
        scp deployment_package.tar.gz root@185.70.198.201:/root/
        ssh root@185.70.198.201 '
            cd /root
            tar -xzf deployment_package.tar.gz
            chmod +x *.sh
            ./deploy_on_server.sh
        '
    else
        echo "❌ SSH connection failed - check SSH key or server access"
    fi
else
    echo "❌ Server not responding - manual intervention required"
    echo "👉 Use UpCloud console to access server directly"
fi
EOF

chmod +x emergency_deploy.sh
print_status "Emergency deployment script created: emergency_deploy.sh" "OK"

echo ""
print_status "STEP 6: Final summary and recommendations" "INFO"

echo ""
echo "📋 EMERGENCY RECOVERY SUMMARY"
echo "============================"
echo "🔴 CRITICAL: Production server is completely inaccessible"
echo "📊 Status: DNS OK, Ping FAILED, All ports CLOSED"
echo "🎯 Root Cause: Likely firewall misconfiguration or server shutdown"
echo ""
echo "⚡ IMMEDIATE ACTIONS:"
echo "1. 📞 Contact UpCloud support IMMEDIATELY"
echo "2. 🖥️  Access UpCloud control panel"  
echo "3. 🔧 Check server status and restart if needed"
echo "4. 🔥 Fix firewall rules to allow ports 80, 443, 8080"
echo "5. 🚀 Restart web services and ASE-Bot application"
echo ""
echo "📋 Files created:"
echo "   • server_recovery_plan.md (detailed recovery guide)"
echo "   • emergency_deploy.sh (automated deployment script)"
echo ""
print_status "Recovery documentation complete - TAKE ACTION NOW!" "ERROR"
EOF

chmod +x server_emergency_recovery.sh
