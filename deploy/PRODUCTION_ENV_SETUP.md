# Production Environment Setup Guide

This checklist helps migrate the ASE backend to a fresh host. It assumes the application code already lives in `/home/admin/asebot-backend` and a Python virtual environment exists at `/home/admin/asebot-backend/.venv`.

## 1. Gather required secrets

| Variable | Description | Source |
| --- | --- | --- |
| `SUPABASE_DB_URL` | Full Postgres connection string from the Supabase project (`postgresql://...`). Must include `sslmode=require`. | Supabase dashboard → Project Settings → Database → Connection string (`psycopg` or `URI`). |
| `DATABASE_URL` | Fallback to the same value as `SUPABASE_DB_URL`. Keep for backward compatibility. | Copy from above; update if future migration uses a different provider. |
| `REDIS_URL` | Redis connection string. Use existing managed Redis or reuse the container from the legacy project. | Old host (`/home/admin/trading-bot-v2/.env`) or cloud provider dashboard. |
| `GEMINI_API_KEY` | Google Gemini API key for AI endpoints. | Google AI Studio (generate a new key if the previous one was exposed). |
| `TAVILY_API_KEY` | Tavily search key powering market intel. | https://app.tavily.com/ |
| `OPENAI_API_KEY` | Optional backup LLM provider. | https://platform.openai.com/ |
| `JWT_SECRET` | 128-hex secret for API tokens. | Generate locally: `openssl rand -hex 64`. |
| `ENCRYPTION_KEY` | 32-byte Fernet key for secrets at rest. | `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `SMTP_*` | Outbound email credentials for verification emails. | Google Workspace / SMTP provider. |
| `VAPID_*` | Web push keys (optional). | Generate with `web-push` CLI or `npx web-push generate-vapid-keys`. |
| Exchange keys | Live Binance/Bybit API credentials if running live trading. | Exchange dashboard (use testnet when experimenting). |

> **Tip:** Keep a decrypted copy of the previous production `.env` handy (`/home/admin/trading-bot-v2/.env`) to migrate Redis URLs, SMTP hosts, etc.

## 2. Update `/home/admin/asebot-backend/.env`

1. SSH into the server (`ssh admin@185.70.198.201`).
2. Create a backup before editing:
   ```bash
   cd /home/admin/asebot-backend
   cp .env .env.backup.$(date +%Y%m%d-%H%M%S)
   ```
3. Open the file with your preferred editor. Example using `nano`:
   ```bash
   nano .env
   ```
4. Replace placeholder values with the secrets gathered above. Ensure:
   - `SUPABASE_DB_URL` includes `sslmode=require`.
   - `DATABASE_URL` mirrors `SUPABASE_DB_URL`.
   - Any command substitutions (e.g., `$(openssl rand ...)`) are replaced with the _literal_ values generated locally; the init scripts will not expand shell expressions.
5. Save the file and restrict permissions:
   ```bash
   chmod 600 .env
   ```

## 3. Reload systemd and start the service

```bash
sudo systemctl daemon-reload
sudo systemctl enable asebot.service
sudo systemctl restart asebot.service
```

### Check status and logs

```bash
sudo systemctl status asebot.service --no-pager
sudo journalctl -u asebot.service -n 100 --no-pager
```

If the service fails to start, tail logs in real time while troubleshooting:

```bash
sudo journalctl -u asebot.service -f
```

## 4. Smoke test the API

```bash
curl -sf http://127.0.0.1:8008/health
curl -sf http://127.0.0.1:8008/api
```

Expect JSON payloads with status `healthy`. If the host uses a reverse proxy (Nginx), test via the public domain as well.

## 5. Optional: Nginx reverse proxy

If not yet configured, drop a site descriptor at `/etc/nginx/sites-available/asebot.conf`:

```nginx
server {
    listen 80;
    server_name your.domain.com;

    location / {
        proxy_pass http://127.0.0.1:8008;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /home/admin/asebot-backend/static/;
    }
}
```

Then enable and reload Nginx:

```bash
sudo ln -s /etc/nginx/sites-available/asebot.conf /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

Use `certbot` to add TLS:

```bash
sudo certbot --nginx -d your.domain.com
```

## 6. Cleanup & hardening

- Remove tarballs once deployment succeeds:
  ```bash
  rm -f ~/asebot-backend-*.tar.gz
  ```
- Restrict backup files to the `admin` user (`chmod 600 .env.backup*`).
- Configure unattended upgrades and fail2ban if not already enabled.
- Schedule database backups in Supabase and Redis snapshots if using managed Redis.

## 7. Post-deployment validation

- Verify trading tasks by hitting `/api/trading/symbols` and `/api/trading/orders`.
- Confirm AI features by calling `/api/ai/analysis/BTCUSDT` (requires valid API keys).
- Monitor metrics via `/metrics` endpoint (Prometheus format) if scraping is set up.
- Review the dashboard or monitoring script `advanced-monitoring.sh` for runtime anomalies.

Keep this document updated as infrastructure changes.
