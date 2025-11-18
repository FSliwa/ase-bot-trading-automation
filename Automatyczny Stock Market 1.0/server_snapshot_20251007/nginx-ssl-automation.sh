#!/bin/bash

################################################################################
# ASE-Bot Nginx and SSL Configuration Automation
# Automatyczna konfiguracja nginx, SSL, certyfikatów i bezpieczeństwa
# Wersja: 1.0
################################################################################

set -euo pipefail

# === KONFIGURACJA ===
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NGINX_VERSION="1.0"

# Ścieżki
NGINX_CONFIG_DIR="/etc/nginx"
NGINX_SITES_AVAILABLE="$NGINX_CONFIG_DIR/sites-available"
NGINX_SITES_ENABLED="$NGINX_CONFIG_DIR/sites-enabled"
SSL_DIR="/etc/ssl/certs/asebot"
LOG_DIR="/var/log/asebot"

# Konfiguracja domenowa
DOMAIN="ase-bot.live"
SUBDOMAIN="www.ase-bot.live"
API_SUBDOMAIN="api.ase-bot.live"
DASHBOARD_SUBDOMAIN="dashboard.ase-bot.live"

# Porty aplikacji
API_PORT=8012
PROXY_PORT=8008
DASHBOARD_PORT=9999

# Kolory
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

# === FUNKCJE POMOCNICZE ===

log() {
    local level=$1
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    case $level in
        "INFO")  echo -e "${GREEN}[INFO]${NC}  [$timestamp] $message" ;;
        "WARN")  echo -e "${YELLOW}[WARN]${NC}  [$timestamp] $message" ;;
        "ERROR") echo -e "${RED}[ERROR]${NC} [$timestamp] $message" ;;
        "DEBUG") echo -e "${BLUE}[DEBUG]${NC} [$timestamp] $message" ;;
        *)       echo -e "[$timestamp] $message" ;;
    esac
    
    # Zapisz do pliku loga
    mkdir -p "$LOG_DIR"
    echo "[$level] [$timestamp] $message" >> "$LOG_DIR/nginx-ssl-$(date +%Y%m%d).log"
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

check_root() {
    if [[ $EUID -eq 0 ]]; then
        log "ERROR" "Nie uruchamiaj tego skryptu jako root. Użyj sudo tylko gdy potrzeba."
        exit 1
    fi
}

# === INSTALACJA I KONFIGURACJA NGINX ===

install_nginx() {
    log "INFO" "🌐 Instalacja i konfiguracja Nginx..."
    
    # Sprawdź czy nginx jest zainstalowany
    if command_exists nginx; then
        local current_version
        current_version=$(nginx -v 2>&1 | cut -d'/' -f2 | cut -d' ' -f1)
        log "INFO" "Nginx już zainstalowany (wersja: $current_version)"
    else
        log "INFO" "Instalowanie Nginx..."
        if sudo apt-get update && sudo apt-get install -y nginx; then
            log "INFO" "✅ Nginx zainstalowany pomyślnie"
        else
            log "ERROR" "❌ Nie udało się zainstalować Nginx"
            return 1
        fi
    fi
    
    # Uruchom i włącz nginx
    sudo systemctl enable nginx
    sudo systemctl start nginx
    
    # Sprawdź status
    if sudo systemctl is-active --quiet nginx; then
        log "INFO" "✅ Nginx działa poprawnie"
    else
        log "WARN" "⚠️ Problem z uruchomieniem Nginx"
        return 1
    fi
    
    return 0
}

create_nginx_config() {
    log "INFO" "📝 Tworzenie konfiguracji Nginx..."
    
    # Backup istniejącej konfiguracji
    if [[ -f "$NGINX_SITES_AVAILABLE/$DOMAIN" ]]; then
        sudo cp "$NGINX_SITES_AVAILABLE/$DOMAIN" "$NGINX_SITES_AVAILABLE/$DOMAIN.backup.$(date +%Y%m%d_%H%M%S)"
    fi
    
    # Główna konfiguracja serwera
    sudo tee "$NGINX_SITES_AVAILABLE/$DOMAIN" > /dev/null << EOF
# ASE-Bot Nginx Configuration
# Generated: $(date)

# Rate limiting
limit_req_zone \$binary_remote_addr zone=api_limit:10m rate=10r/s;
limit_req_zone \$binary_remote_addr zone=general_limit:10m rate=60r/m;

# Upstream servers
upstream api_backend {
    server 127.0.0.1:$API_PORT max_fails=3 fail_timeout=30s;
    keepalive 32;
}

upstream proxy_server {
    server 127.0.0.1:$PROXY_PORT max_fails=3 fail_timeout=30s;
    keepalive 32;
}

upstream dashboard_server {
    server 127.0.0.1:$DASHBOARD_PORT max_fails=3 fail_timeout=30s;
    keepalive 32;
}

# HTTP Redirect to HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN $SUBDOMAIN $API_SUBDOMAIN $DASHBOARD_SUBDOMAIN;
    
    # Security headers
    add_header X-Robots-Tag noindex;
    
    # ACME Challenge for Let's Encrypt
    location /.well-known/acme-challenge/ {
        root /var/www/html;
        try_files \$uri =404;
    }
    
    # Redirect all HTTP to HTTPS
    location / {
        return 301 https://\$server_name\$request_uri;
    }
}

# Main HTTPS Server
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name $DOMAIN $SUBDOMAIN;
    
    # SSL Configuration
    ssl_certificate $SSL_DIR/fullchain.pem;
    ssl_certificate_key $SSL_DIR/privkey.pem;
    include /etc/nginx/ssl-params.conf;
    
    # Document root
    root /var/www/html;
    index index.html index.php;
    
    # Logging
    access_log /var/log/nginx/asebot_access.log;
    error_log /var/log/nginx/asebot_error.log;
    
    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header Referrer-Policy strict-origin-when-cross-origin;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self'; font-src 'self' https://cdn.jsdelivr.net;";
    
    # Rate limiting
    limit_req zone=general_limit burst=20 nodelay;
    
    # Hide nginx version
    server_tokens off;
    
    # Main location
    location / {
        try_files \$uri \$uri/ =404;
    }
    
    # API Proxy
    location /api/ {
        limit_req zone=api_limit burst=5 nodelay;
        
        proxy_pass http://api_backend/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$server_name;
        
        # Timeouts
        proxy_connect_timeout 10s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
        
        # Connection reuse
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        
        # Error handling
        proxy_intercept_errors on;
        error_page 502 503 504 /50x.html;
    }
    
    # Proxy Server
    location /proxy/ {
        limit_req zone=api_limit burst=5 nodelay;
        
        proxy_pass http://proxy_server/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # WebSocket support (if needed)
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        
        proxy_connect_timeout 10s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        proxy_http_version 1.1;
    }
    
    # Health check
    location /health {
        access_log off;
        return 200 "healthy";
        add_header Content-Type text/plain;
    }
    
    # Deny access to sensitive files
    location ~ /\\. {
        deny all;
    }
    
    location ~ \\.(env|log|conf)\$ {
        deny all;
    }
    
    # Error pages
    error_page 404 /404.html;
    error_page 500 502 503 504 /50x.html;
    
    location = /50x.html {
        root /var/www/html;
    }
}

# API Subdomain
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name $API_SUBDOMAIN;
    
    # SSL Configuration
    ssl_certificate $SSL_DIR/fullchain.pem;
    ssl_certificate_key $SSL_DIR/privkey.pem;
    include /etc/nginx/ssl-params.conf;
    
    # Logging
    access_log /var/log/nginx/api_access.log;
    error_log /var/log/nginx/api_error.log;
    
    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    
    # Rate limiting for API
    limit_req zone=api_limit burst=10 nodelay;
    
    location / {
        proxy_pass http://api_backend;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        proxy_connect_timeout 10s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
        
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }
}

# Dashboard Subdomain
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name $DASHBOARD_SUBDOMAIN;
    
    # SSL Configuration
    ssl_certificate $SSL_DIR/fullchain.pem;
    ssl_certificate_key $SSL_DIR/privkey.pem;
    include /etc/nginx/ssl-params.conf;
    
    # Logging
    access_log /var/log/nginx/dashboard_access.log;
    error_log /var/log/nginx/dashboard_error.log;
    
    # Security headers
    add_header X-Frame-Options SAMEORIGIN;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    
    # Basic auth for dashboard (optional)
    # auth_basic "ASE-Bot Dashboard";
    # auth_basic_user_file /etc/nginx/.htpasswd;
    
    location / {
        proxy_pass http://dashboard_server;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        proxy_connect_timeout 10s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
        
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }
}
EOF
    
    log "INFO" "✅ Konfiguracja Nginx utworzona"
    return 0
}

create_ssl_config() {
    log "INFO" "🔒 Tworzenie konfiguracji SSL..."
    
    # Utwórz plik z parametrami SSL
    sudo tee /etc/nginx/ssl-params.conf > /dev/null << 'EOF'
# SSL Configuration Parameters
# Mozilla Intermediate configuration

ssl_protocols TLSv1.2 TLSv1.3;
ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384;
ssl_prefer_server_ciphers off;

# SSL session settings
ssl_session_timeout 1d;
ssl_session_cache shared:SSL:50m;
ssl_session_tickets off;

# OCSP stapling
ssl_stapling on;
ssl_stapling_verify on;
resolver 8.8.8.8 8.8.4.4 valid=300s;
resolver_timeout 5s;

# Security headers
add_header Strict-Transport-Security "max-age=63072000" always;

# Diffie-Hellman parameter for DHE ciphersuites
ssl_dhparam /etc/nginx/dhparam.pem;
EOF
    
    # Wygeneruj parametry Diffie-Hellman (jeśli nie istnieją)
    if [[ ! -f /etc/nginx/dhparam.pem ]]; then
        log "INFO" "🔐 Generowanie parametrów Diffie-Hellman (może potrwać kilka minut)..."
        sudo openssl dhparam -out /etc/nginx/dhparam.pem 2048
        log "INFO" "✅ Parametry DH wygenerowane"
    fi
    
    log "INFO" "✅ Konfiguracja SSL utworzona"
    return 0
}

# === CERTYFIKATY SSL ===

install_certbot() {
    log "INFO" "🔒 Instalacja Certbot dla Let's Encrypt..."
    
    if command_exists certbot; then
        log "INFO" "Certbot już zainstalowany"
    else
        log "INFO" "Instalowanie Certbot..."
        if sudo apt-get update && sudo apt-get install -y certbot python3-certbot-nginx; then
            log "INFO" "✅ Certbot zainstalowany"
        else
            log "ERROR" "❌ Nie udało się zainstalować Certbot"
            return 1
        fi
    fi
    
    return 0
}

generate_self_signed_cert() {
    log "INFO" "📜 Generowanie certyfikatu self-signed (tymczasowy)..."
    
    sudo mkdir -p "$SSL_DIR"
    
    # Wygeneruj klucz prywatny
    sudo openssl genrsa -out "$SSL_DIR/privkey.pem" 2048
    
    # Wygeneruj certyfikat self-signed
    sudo openssl req -new -x509 -key "$SSL_DIR/privkey.pem" -out "$SSL_DIR/fullchain.pem" -days 90 -subj "/C=PL/ST=Poland/L=Warsaw/O=ASE-Bot/CN=$DOMAIN"
    
    # Ustaw uprawnienia
    sudo chmod 600 "$SSL_DIR/privkey.pem"
    sudo chmod 644 "$SSL_DIR/fullchain.pem"
    
    log "INFO" "✅ Certyfikat self-signed utworzony"
    return 0
}

obtain_letsencrypt_cert() {
    log "INFO" "🌐 Pobieranie certyfikatu Let's Encrypt..."
    
    # Sprawdź czy nginx jest uruchomiony
    if ! sudo systemctl is-active --quiet nginx; then
        log "WARN" "Nginx nie działa - uruchamianie..."
        sudo systemctl start nginx
    fi
    
    # Utwórz katalog dla ACME challenge
    sudo mkdir -p /var/www/html/.well-known/acme-challenge
    
    # Spróbuj uzyskać certyfikat
    local domains="-d $DOMAIN -d $SUBDOMAIN -d $API_SUBDOMAIN -d $DASHBOARD_SUBDOMAIN"
    
    if sudo certbot certonly --webroot -w /var/www/html $domains --email admin@$DOMAIN --agree-tos --non-interactive; then
        
        # Skopiuj certyfikaty do naszego katalogu SSL
        sudo cp "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" "$SSL_DIR/"
        sudo cp "/etc/letsencrypt/live/$DOMAIN/privkey.pem" "$SSL_DIR/"
        
        # Ustaw uprawnienia
        sudo chmod 644 "$SSL_DIR/fullchain.pem"
        sudo chmod 600 "$SSL_DIR/privkey.pem"
        
        log "INFO" "✅ Certyfikat Let's Encrypt pobrany"
        
        # Skonfiguruj automatyczne odnowienie
        setup_cert_renewal
        
        return 0
    else
        log "WARN" "⚠️ Nie udało się pobrać certyfikatu Let's Encrypt - używam self-signed"
        generate_self_signed_cert
        return 1
    fi
}

setup_cert_renewal() {
    log "INFO" "⏰ Konfiguracja automatycznego odnowienia certyfikatów..."
    
    # Dodaj zadanie cron dla odnowienia
    (sudo crontab -l 2>/dev/null; echo "0 12 * * * /usr/bin/certbot renew --quiet --post-hook 'systemctl reload nginx'") | sudo crontab -
    
    # Utwórz skrypt hook dla post-renewal
    sudo tee /etc/letsencrypt/renewal-hooks/post/nginx-reload.sh > /dev/null << 'EOF'
#!/bin/bash
systemctl reload nginx
# Skopiuj certyfikaty do katalogu ASE-Bot
cp "/etc/letsencrypt/live/ase-bot.live/fullchain.pem" "/etc/ssl/certs/asebot/"
cp "/etc/letsencrypt/live/ase-bot.live/privkey.pem" "/etc/ssl/certs/asebot/"
chmod 644 "/etc/ssl/certs/asebot/fullchain.pem"
chmod 600 "/etc/ssl/certs/asebot/privkey.pem"
EOF
    
    sudo chmod +x /etc/letsencrypt/renewal-hooks/post/nginx-reload.sh
    
    log "INFO" "✅ Automatyczne odnowienie certyfikatów skonfigurowane"
    return 0
}

# === BEZPIECZEŃSTWO I OPTYMALIZACJA ===

configure_security() {
    log "INFO" "🛡️ Konfiguracja bezpieczeństwa Nginx..."
    
    # Utwórz niestandardową stronę błędów
    sudo mkdir -p /var/www/html
    
    # Strona 404
    sudo tee /var/www/html/404.html > /dev/null << 'EOF'
<!DOCTYPE html>
<html>
<head>
    <title>404 - Page Not Found</title>
    <style>
        body { font-family: Arial, sans-serif; text-align: center; margin-top: 100px; }
        .error { color: #666; }
    </style>
</head>
<body>
    <h1>404</h1>
    <p class="error">The requested page was not found.</p>
</body>
</html>
EOF
    
    # Strona 50x
    sudo tee /var/www/html/50x.html > /dev/null << 'EOF'
<!DOCTYPE html>
<html>
<head>
    <title>Service Temporarily Unavailable</title>
    <style>
        body { font-family: Arial, sans-serif; text-align: center; margin-top: 100px; }
        .error { color: #666; }
    </style>
</head>
<body>
    <h1>Service Temporarily Unavailable</h1>
    <p class="error">The server is temporarily unable to service your request. Please try again later.</p>
</body>
</html>
EOF
    
    # Główna strona index
    sudo tee /var/www/html/index.html > /dev/null << 'EOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ASE-Bot Trading Platform</title>
    <style>
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            margin: 0;
            padding: 0;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container { text-align: center; max-width: 600px; padding: 40px; }
        .logo { font-size: 3em; margin-bottom: 20px; }
        .title { font-size: 2.5em; margin-bottom: 10px; font-weight: 300; }
        .subtitle { font-size: 1.2em; margin-bottom: 40px; opacity: 0.9; }
        .links { margin-top: 40px; }
        .link { 
            display: inline-block;
            margin: 10px 20px;
            padding: 12px 24px;
            background: rgba(255,255,255,0.2);
            color: white;
            text-decoration: none;
            border-radius: 6px;
            transition: background 0.3s;
        }
        .link:hover { background: rgba(255,255,255,0.3); }
        .status { margin-top: 30px; font-size: 0.9em; opacity: 0.8; }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">🚀</div>
        <h1 class="title">ASE-Bot</h1>
        <p class="subtitle">Advanced Stock Exchange Trading Platform</p>
        <p>Automated trading system with AI-powered algorithms</p>
        
        <div class="links">
            <a href="/api/health" class="link">API Status</a>
            <a href="/proxy/health" class="link">Proxy Status</a>
            <a href="https://dashboard.ase-bot.live" class="link">Dashboard</a>
        </div>
        
        <div class="status">
            System Status: <span style="color: #4CAF50;">●</span> Online
        </div>
    </div>
</body>
</html>
EOF
    
    # Konfiguruj logrotate dla nginx
    sudo tee /etc/logrotate.d/asebot-nginx > /dev/null << 'EOF'
/var/log/nginx/asebot_*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0644 www-data adm
    sharedscripts
    prerotate
        if [ -d /etc/logrotate.d/httpd-prerotate ]; then \
            run-parts /etc/logrotate.d/httpd-prerotate; \
        fi
    endscript
    postrotate
        invoke-rc.d nginx rotate >/dev/null 2>&1
    endscript
}
EOF
    
    log "INFO" "✅ Bezpieczeństwo skonfigurowane"
    return 0
}

optimize_nginx() {
    log "INFO" "⚡ Optymalizacja wydajności Nginx..."
    
    # Backup głównej konfiguracji nginx
    sudo cp /etc/nginx/nginx.conf /etc/nginx/nginx.conf.backup.$(date +%Y%m%d_%H%M%S)
    
    # Utwórz zoptymalizowaną konfigurację główną
    sudo tee /etc/nginx/nginx.conf > /dev/null << 'EOF'
user www-data;
worker_processes auto;
pid /run/nginx.pid;
include /etc/nginx/modules-enabled/*.conf;

events {
    worker_connections 2048;
    use epoll;
    multi_accept on;
}

http {
    ##
    # Basic Settings
    ##
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    keepalive_requests 100;
    types_hash_max_size 2048;
    server_tokens off;
    
    # Buffer sizes
    client_body_buffer_size 128k;
    client_max_body_size 50m;
    client_header_buffer_size 1k;
    large_client_header_buffers 4 16k;
    
    # Timeouts
    client_body_timeout 12;
    client_header_timeout 12;
    send_timeout 10;
    
    # File cache
    open_file_cache max=200000 inactive=20s;
    open_file_cache_valid 30s;
    open_file_cache_min_uses 2;
    open_file_cache_errors on;
    
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    
    ##
    # SSL Settings
    ##
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    
    ##
    # Logging Settings
    ##
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                   '$status $body_bytes_sent "$http_referer" '
                   '"$http_user_agent" "$http_x_forwarded_for" '
                   'rt=$request_time uct="$upstream_connect_time" '
                   'uht="$upstream_header_time" urt="$upstream_response_time"';
                   
    access_log /var/log/nginx/access.log main;
    error_log /var/log/nginx/error.log;
    
    ##
    # Gzip Settings
    ##
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types
        text/plain
        text/css
        text/xml
        text/javascript
        application/json
        application/javascript
        application/xml+rss
        application/atom+xml
        image/svg+xml;
    
    ##
    # Rate Limiting (moved to site config)
    ##
    include /etc/nginx/conf.d/*.conf;
    include /etc/nginx/sites-enabled/*;
}
EOF
    
    log "INFO" "✅ Nginx zoptymalizowany"
    return 0
}

# === TESTOWANIE I WALIDACJA ===

test_nginx_config() {
    log "INFO" "🧪 Testowanie konfiguracji Nginx..."
    
    if sudo nginx -t; then
        log "INFO" "✅ Konfiguracja Nginx jest poprawna"
        return 0
    else
        log "ERROR" "❌ Błąd w konfiguracji Nginx"
        return 1
    fi
}

enable_site() {
    log "INFO" "🔗 Włączanie strony $DOMAIN..."
    
    # Usuń domyślną stronę nginx
    sudo rm -f "$NGINX_SITES_ENABLED/default"
    
    # Włącz naszą stronę
    sudo ln -sf "$NGINX_SITES_AVAILABLE/$DOMAIN" "$NGINX_SITES_ENABLED/"
    
    # Testuj konfigurację
    if test_nginx_config; then
        # Przeładuj nginx
        sudo systemctl reload nginx
        log "INFO" "✅ Strona włączona i nginx przeładowany"
        return 0
    else
        log "ERROR" "❌ Błąd w konfiguracji - strona nie została włączona"
        return 1
    fi
}

test_ssl_connectivity() {
    log "INFO" "🔒 Testowanie połączeń SSL..."
    
    local test_results=()
    
    # Test domenę główną
    if curl -I --connect-timeout 10 "https://$DOMAIN" >/dev/null 2>&1; then
        test_results+=("✅ $DOMAIN - OK")
    else
        test_results+=("❌ $DOMAIN - FAIL")
    fi
    
    # Test poddomenę dashboard
    if curl -I --connect-timeout 10 "https://$DASHBOARD_SUBDOMAIN" >/dev/null 2>&1; then
        test_results+=("✅ $DASHBOARD_SUBDOMAIN - OK")
    else
        test_results+=("❌ $DASHBOARD_SUBDOMAIN - FAIL")
    fi
    
    # Test API
    if curl -I --connect-timeout 10 "https://$API_SUBDOMAIN/health" >/dev/null 2>&1; then
        test_results+=("✅ $API_SUBDOMAIN - OK")
    else
        test_results+=("❌ $API_SUBDOMAIN - FAIL")
    fi
    
    # Wyświetl wyniki
    log "INFO" "📊 Wyniki testów SSL:"
    for result in "${test_results[@]}"; do
        log "INFO" "  $result"
    done
    
    return 0
}

# === MONITORING I DIAGNOSTYKA ===

create_nginx_monitoring() {
    log "INFO" "📊 Tworzenie monitoringu Nginx..."
    
    # Skrypt sprawdzający status nginx
    sudo tee /usr/local/bin/nginx-health-check.sh > /dev/null << 'EOF'
#!/bin/bash

NGINX_STATUS=$(systemctl is-active nginx)
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

if [[ "$NGINX_STATUS" != "active" ]]; then
    echo "[$TIMESTAMP] ERROR: Nginx is not running - attempting restart"
    systemctl restart nginx
    
    sleep 5
    
    if systemctl is-active --quiet nginx; then
        echo "[$TIMESTAMP] INFO: Nginx restarted successfully"
        echo "Nginx service recovered" | mail -s "Nginx Recovery Alert" admin@ase-bot.live 2>/dev/null || true
    else
        echo "[$TIMESTAMP] CRITICAL: Failed to restart nginx"
        echo "Critical: Nginx failed to restart" | mail -s "CRITICAL: Nginx Down" admin@ase-bot.live 2>/dev/null || true
    fi
else
    echo "[$TIMESTAMP] INFO: Nginx is running normally"
fi

# Test połączeń
if ! curl -f --connect-timeout 5 http://localhost/health >/dev/null 2>&1; then
    echo "[$TIMESTAMP] WARN: Health check failed"
fi
EOF
    
    sudo chmod +x /usr/local/bin/nginx-health-check.sh
    
    # Dodaj do cron
    (sudo crontab -l 2>/dev/null; echo "*/5 * * * * /usr/local/bin/nginx-health-check.sh >> /var/log/nginx/health-check.log 2>&1") | sudo crontab -
    
    log "INFO" "✅ Monitoring Nginx skonfigurowany"
    return 0
}

show_nginx_info() {
    log "INFO" ""
    log "INFO" "🌐 INFORMACJE O NGINX I SSL"
    log "INFO" "=========================="
    log "INFO" "Główna domena: https://$DOMAIN"
    log "INFO" "Dashboard: https://$DASHBOARD_SUBDOMAIN"
    log "INFO" "API: https://$API_SUBDOMAIN"
    log "INFO" "WWW: https://$SUBDOMAIN"
    log "INFO" ""
    log "INFO" "📁 ŚCIEŻKI KONFIGURACJI"
    log "INFO" "======================"
    log "INFO" "Konfiguracja: $NGINX_SITES_AVAILABLE/$DOMAIN"
    log "INFO" "SSL Certs: $SSL_DIR/"
    log "INFO" "Logi: /var/log/nginx/"
    log "INFO" "Web root: /var/www/html"
    log "INFO" ""
    log "INFO" "🔧 KOMENDY ZARZĄDZANIA"
    log "INFO" "===================="
    log "INFO" "sudo systemctl reload nginx  - Przeładuj konfigurację"
    log "INFO" "sudo nginx -t                - Test konfiguracji"
    log "INFO" "sudo certbot renew          - Odnów certyfikaty"
    log "INFO" ""
}

# === MAIN ===

show_help() {
    echo "ASE-Bot Nginx and SSL Configuration v$NGINX_VERSION"
    echo ""
    echo "Użycie:"
    echo "  $0 COMMAND [OPTIONS]"
    echo ""
    echo "Komendy:"
    echo "  setup                Pełna konfiguracja Nginx + SSL"
    echo "  nginx-only           Tylko instalacja i konfiguracja Nginx"
    echo "  ssl-only             Tylko konfiguracja SSL"
    echo "  test                 Test konfiguracji i połączeń"
    echo "  reload               Przeładuj konfigurację Nginx"
    echo "  status               Status Nginx i SSL"
    echo "  renew-certs          Odnów certyfikaty SSL"
    echo "  logs                 Pokaż logi Nginx"
    echo ""
    echo "Opcje:"
    echo "  --domain DOMAIN      Ustaw domenę (domyślnie: ase-bot.live)"
    echo "  --self-signed        Użyj certyfikatów self-signed"
    echo ""
    echo "Przykłady:"
    echo "  $0 setup             # Pełna konfiguracja"
    echo "  $0 test              # Test konfiguracji"
    echo "  $0 status            # Status systemu"
    echo ""
}

main() {
    local command=${1:-"help"}
    
    # Sprawdź czy nie jest uruchamiany jako root
    check_root
    
    case $command in
        "setup"|"s")
            log "INFO" "🚀 Rozpoczynam pełną konfigurację Nginx + SSL..."
            
            install_nginx || exit 1
            create_ssl_config || exit 1
            create_nginx_config || exit 1
            configure_security || exit 1
            optimize_nginx || exit 1
            
            # SSL Setup
            install_certbot || exit 1
            
            # Najpierw użyj self-signed dla testu
            generate_self_signed_cert || exit 1
            enable_site || exit 1
            
            # Następnie spróbuj uzyskać prawdziwy certyfikat
            if obtain_letsencrypt_cert; then
                enable_site  # Przeładuj z prawdziwymi certyfikatami
            fi
            
            create_nginx_monitoring || exit 1
            test_ssl_connectivity
            
            show_nginx_info
            log "INFO" "✅ Konfiguracja Nginx + SSL zakończona pomyślnie"
            ;;
        "nginx-only"|"n")
            install_nginx || exit 1
            create_nginx_config || exit 1
            configure_security || exit 1
            optimize_nginx || exit 1
            generate_self_signed_cert || exit 1
            enable_site || exit 1
            show_nginx_info
            ;;
        "ssl-only"|"ssl")
            install_certbot || exit 1
            create_ssl_config || exit 1
            obtain_letsencrypt_cert || exit 1
            test_ssl_connectivity
            ;;
        "test"|"t")
            test_nginx_config
            test_ssl_connectivity
            ;;
        "reload"|"r")
            if test_nginx_config; then
                sudo systemctl reload nginx
                log "INFO" "✅ Nginx przeładowany"
            fi
            ;;
        "status"|"st")
            log "INFO" "📊 Status Nginx:"
            sudo systemctl status nginx --no-pager
            
            log "INFO" "🔒 Certyfikaty SSL:"
            if [[ -f "$SSL_DIR/fullchain.pem" ]]; then
                local cert_info
                cert_info=$(sudo openssl x509 -in "$SSL_DIR/fullchain.pem" -text -noout | grep -E "(Subject:|Not After)")
                log "INFO" "$cert_info"
            else
                log "WARN" "Brak certyfikatów SSL"
            fi
            ;;
        "renew-certs"|"renew")
            sudo certbot renew --quiet
            log "INFO" "🔄 Certyfikaty odnowione"
            ;;
        "logs"|"l")
            log "INFO" "📋 Ostatnie logi Nginx:"
            sudo tail -50 /var/log/nginx/error.log
            ;;
        "help"|"h"|"-h"|"--help")
            show_help
            ;;
        *)
            log "ERROR" "Nieznana komenda: $command"
            show_help
            exit 1
            ;;
    esac
}

# Uruchom główną funkcję
main "$@"
