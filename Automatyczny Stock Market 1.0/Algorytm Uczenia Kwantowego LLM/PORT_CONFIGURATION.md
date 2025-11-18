# Port Configuration and Recommendations

## 📊 Current Port Status

### ✅ Active Ports (Currently Running)
- **8008** - Trading Bot Web Application (PRIMARY)
- **8080** - Python Application (CONFLICT - needs relocation)
- **5432** - PostgreSQL Database (LOCAL - will conflict with Docker)
- **5000** - System ControlCenter
- **7000** - System ControlCenter  
- **3000** - Node.js Development Server (CONFLICT with Grafana)
- **7545** - Ganache Blockchain (Development)

### 🔄 Recommended Production Port Layout

#### Core Application Stack
```
80    - Nginx HTTP (redirects to HTTPS)
443   - Nginx HTTPS (main public access)
8008  - Trading Bot API (current, keep)
8009  - Trading Bot Admin Interface (future)
```

#### Database & Cache Layer
```
5433  - PostgreSQL (Docker) - changed from 5432 to avoid conflict
6379  - Redis Cache
6380  - Redis Backup Instance (optional)
```

#### Monitoring & Observability
```
9090  - Prometheus Metrics Collection
3001  - Grafana Dashboard - changed from 3000 to avoid conflict
9100  - Node Exporter (system metrics)
9121  - Redis Exporter (Redis metrics)
9187  - PostgreSQL Exporter (database metrics)
8081  - Nginx Monitoring Endpoints - changed from 8080
```

#### Development & Testing
```
8010  - OAuth Callback Server
8082  - Testing/Staging Environment
5434  - Testing Database
6381  - Testing Redis
```

## 🔧 Configuration Changes Made

### 1. Docker Compose Adjustments
- PostgreSQL: `5432:5432` → `5433:5432`
- Grafana: `3000:3000` → `3001:3000`
- Added monitoring exporters with dedicated ports

### 2. Nginx Configuration Updates
- Monitoring endpoint: `8080` → `8081`
- Added routes for all metric exporters
- Centralized monitoring access point

### 3. New Monitoring Services Added
- Node Exporter (9100) - System metrics
- Redis Exporter (9121) - Redis performance
- PostgreSQL Exporter (9187) - Database metrics

## 🚀 Deployment Commands

### Start Full Stack (Production)
```bash
# Deploy with new port configuration
./deploy.sh deploy

# Check all services
docker-compose ps

# Verify port allocation
netstat -tulpn | grep LISTEN
```

### Access Points After Deployment
```bash
# Main application
https://localhost/              # Public access (port 443)
http://localhost:8008/         # Direct API access

# Monitoring
http://localhost:3001/         # Grafana Dashboard
http://localhost:9090/         # Prometheus
http://localhost:8081/metrics  # All metrics via Nginx

# Database (for admin)
localhost:5433                 # PostgreSQL (Docker)
localhost:6379                 # Redis
```

### Health Checks
```bash
# Application health
curl http://localhost:8008/health

# Prometheus targets
curl http://localhost:9090/api/v1/targets

# Grafana readiness
curl http://localhost:3001/api/health

# All metrics endpoint
curl http://localhost:8081/metrics
```

## ⚠️ Port Conflict Resolution

### Before Deployment
1. **Stop conflicting services:**
   ```bash
   # Stop Node.js on port 3000 if needed
   lsof -ti:3000 | xargs kill -9
   
   # Stop Python app on port 8080 if needed  
   lsof -ti:8080 | xargs kill -9
   ```

2. **Verify port availability:**
   ```bash
   # Check if ports are free
   lsof -i :3001  # Should be empty
   lsof -i :5433  # Should be empty
   lsof -i :8081  # Should be empty
   ```

### Alternative Configurations
If you prefer to keep current services running:

#### Option 1: Different Port Range
```yaml
# Use higher port range to avoid conflicts
grafana: "4000:3000"
postgres: "6432:5432" 
nginx-monitoring: "9080:8080"
```

#### Option 2: localhost-only binding
```yaml
# Bind only to localhost to reduce conflicts
grafana: "127.0.0.1:3001:3000"
postgres: "127.0.0.1:5433:5432"
```

## 📈 Monitoring Port Overview

After full deployment, you'll have comprehensive monitoring:

- **Application Metrics** (8008/metrics) - Trading bot performance
- **System Metrics** (9100) - CPU, RAM, Disk, Network
- **Database Metrics** (9187) - PostgreSQL performance
- **Cache Metrics** (9121) - Redis performance  
- **Web Server Metrics** (8081) - Nginx performance

All accessible through Grafana on port 3001 with pre-configured dashboards.

## 🔒 Security Considerations

### Firewall Rules (Production)
```bash
# Public access
ufw allow 80/tcp   # HTTP
ufw allow 443/tcp  # HTTPS

# Admin access (restrict IP if needed)
ufw allow 8008/tcp  # API
ufw allow 3001/tcp  # Grafana
ufw allow 9090/tcp  # Prometheus

# Database access (localhost only recommended)
ufw allow from 127.0.0.1 to any port 5433
ufw allow from 127.0.0.1 to any port 6379
```

### Environment Variables Update
Update `.env.production` with new database URL:
```env
DATABASE_URL=postgresql://tradingbot:${DB_PASSWORD}@localhost:5433/tradingbot
```
