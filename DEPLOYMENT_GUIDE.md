# Trading Bot Production Deployment Guide

## 🚀 Deployment Overview

Ten system jest gotowy do wdrożenia produkcyjnego z pełną infrastrukturą Docker, monitoringiem i bezpieczeństwem.

## 📋 Wymagania Systemu

### Minimalne Wymagania:
- **CPU**: 4 cores (8 cores zalecane)
- **RAM**: 8GB (16GB zalecane)
- **Dysk**: 100GB SSD
- **System**: Ubuntu 20.04+ / CentOS 8+ / RHEL 8+
- **Docker**: 20.10+
- **Docker Compose**: 2.0+

### Zalecane dla Produkcji:
- **CPU**: 8+ cores
- **RAM**: 32GB+
- **Dysk**: 500GB SSD NVMe
- **Backup**: Oddzielny dysk dla kopii zapasowych

## 🔧 Przygotowanie Serwera

### 1. Instalacja Docker i Docker Compose

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### 2. Konfiguracja Firewall

```bash
# UFW (Ubuntu)
sudo ufw allow 80/tcp      # HTTP
sudo ufw allow 443/tcp     # HTTPS
sudo ufw allow 8008/tcp    # Application
sudo ufw allow 3000/tcp    # Grafana
sudo ufw allow 9090/tcp    # Prometheus
sudo ufw enable
```

## 🔐 Konfiguracja Bezpieczeństwa

### 1. Aktualizacja Pliku .env.production

**WAŻNE**: Zaktualizuj wszystkie hasła i klucze API przed wdrożeniem!

```bash
# Skopiuj i dostosuj plik środowiskowy
cp .env.production .env.production.local

# Wygeneruj bezpieczne hasła
openssl rand -base64 32  # Dla DB_PASSWORD
openssl rand -base64 32  # Dla REDIS_PASSWORD
openssl rand -base64 64  # Dla SECRET_KEY
```

### 2. Ustawienie Kluczy API

W pliku `.env.production.local`:

```env
# OpenAI API Key (produkcyjny)
OPENAI_API_KEY=sk-proj-YOUR_PRODUCTION_KEY

# Exchange API Keys (produkcyjne)
PRIMEXBT_API_KEY=your_production_api_key
PRIMEXBT_SECRET_KEY=your_production_secret_key
PRIMEXBT_PASSPHRASE=your_production_passphrase
PRIMEXBT_SANDBOX=false

BINANCE_API_KEY=your_production_binance_key
BINANCE_SECRET_KEY=your_production_binance_secret
```

## 🚀 Wdrażanie Aplikacji

### 1. Klonowanie i Przygotowanie

```bash
# Sklonuj repozytorium
git clone <your-repo-url> trading-bot-production
cd trading-bot-production

# Skopiuj pliki konfiguracyjne
cp .env.production .env.production.local
# Dostosuj ustawienia w .env.production.local
```

### 2. Automatyczne Wdrożenie

```bash
# Uruchom skrypt wdrożeniowy
./deploy.sh deploy
```

### 3. Ręczne Wdrożenie (krok po kroku)

```bash
# 1. Zbuduj obrazy
docker-compose build --no-cache

# 2. Uruchom usługi
docker-compose up -d

# 3. Sprawdź status
docker-compose ps

# 4. Sprawdź logi
docker-compose logs -f tradingbot
```

## 🔍 Weryfikacja Wdrożenia

### 1. Health Check

```bash
# Sprawdź endpoint zdrowia
curl -k https://localhost/health

# Sprawdź API
curl -k https://localhost/api/test-ai
```

### 2. Sprawdzenie Usług

```bash
# Status kontenerów
docker-compose ps

# Logi aplikacji
./deploy.sh logs tradingbot

# Monitoring
curl http://localhost:9090  # Prometheus
curl http://localhost:3000  # Grafana
```

## 📊 Monitoring i Dashboardy

### Prometheus Metrics
- **URL**: `http://your-server:9090`
- **Metryki**: Trading bot performance, system resources
- **Alerty**: Skonfigurowane dla błędów krytycznych

### Grafana Dashboards
- **URL**: `http://your-server:3000`
- **Login**: admin / (hasło z .env.production)
- **Dashboardy**: Trading performance, system health

### Kluczowe Metryki:
- 🔄 Trading operations per minute
- 💰 Profit/Loss tracking
- 🚨 Error rates
- 📈 API response times
- 💾 Database performance
- 🖥️ System resources

## 🔄 Zarządzanie Produkcją

### Backup i Recovery

```bash
# Backup bazy danych
./deploy.sh backup

# Przywracanie z kopii zapasowej
./deploy.sh rollback
```

### Aktualizacje

```bash
# Aktualizacja aplikacji
git pull origin main
./deploy.sh deploy

# W przypadku problemów - rollback
./deploy.sh rollback
```

### Skalowanie

```bash
# Zwiększenie zasobów dla aplikacji
docker-compose up -d --scale tradingbot=3
```

## 🚨 Troubleshooting

### Częste Problemy:

1. **Aplikacja nie startuje**
   ```bash
   docker-compose logs tradingbot
   # Sprawdź .env.production.local
   ```

2. **Błędy bazy danych**
   ```bash
   docker-compose exec postgres psql -U tradingbot -d tradingbot
   ```

3. **Problemy z SSL**
   ```bash
   # Regeneruj certyfikaty
   rm -rf ssl/*
   ./deploy.sh deploy
   ```

4. **Wysokie zużycie CPU/RAM**
   ```bash
   # Sprawdź zużycie zasobów
   docker stats
   ```

### Logi i Diagnostyka:

```bash
# Wszystkie logi
docker-compose logs --tail=100

# Logi konkretnej usługi
docker-compose logs tradingbot
docker-compose logs postgres
docker-compose logs redis
```

## 🔐 Bezpieczeństwo Produkcyjne

### SSL/TLS
- ✅ Automatyczne przekierowanie HTTP→HTTPS
- ✅ TLS 1.2/1.3 only
- ✅ Secure headers (HSTS, CSP, etc.)

### Rate Limiting
- ✅ API: 10 req/s per IP
- ✅ Web: 30 req/s per IP
- ✅ Burst protection

### Monitoring Bezpieczeństwa
- ✅ Failed login attempts
- ✅ Unusual trading patterns
- ✅ API abuse detection

## 📞 Wsparcie

W przypadku problemów:
1. Sprawdź logi: `./deploy.sh logs`
2. Health check: `./deploy.sh health`
3. Sprawdź dokumentację błędów w logach
4. Kontakt z zespołem DevOps

---

## 🎯 Status Wdrożenia

✅ **Docker Configuration** - Gotowe  
✅ **Database Setup** - PostgreSQL + Redis  
✅ **Security Configuration** - SSL, Rate limiting, Headers  
✅ **Monitoring Stack** - Prometheus + Grafana  
✅ **Backup Strategy** - Automatyczne kopie zapasowe  
✅ **Deployment Scripts** - Automatyzacja wdrożeń  
✅ **Health Checks** - Monitoring kondycji systemu  

**System jest gotowy do wdrożenia produkcyjnego! 🚀**
