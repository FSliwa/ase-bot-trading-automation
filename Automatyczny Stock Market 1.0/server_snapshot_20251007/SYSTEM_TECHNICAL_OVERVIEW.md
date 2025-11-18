# ASE Trading Bot Platform — Technical Overview (October 2025)

> Comprehensive reference for the FastAPI v2 backend, data & analytics services, AI integrations, and supporting infrastructure that power the ASE autonomous trading platform.

## 1. High-Level Architecture

| Layer | Key Modules | Responsibilities | Notes |
| --- | --- | --- | --- |
| Presentation (API & UI) | `src/main.py`, `src/presentation/api/v2/*`, `src/presentation/websocket/trading_ws.py`, Jinja templates under `web/` | HTTP/WS interfaces, security middleware, telemetry hooks | Currently deployed as FastAPI app (ASGI). HTML routes serve marketing/auth dashboard. |
| Application | `src/application/services/user_service.py`, `bot/*.py` | Business orchestration (user auth, session mgmt, trading workflows) | Domain-driven structure; async services use circuit breakers + Redis cache. |
| Domain | `src/domain/entities`, `src/domain/repositories` | Core business objects and repository interfaces | Keeps business logic DB-agnostic. |
| Infrastructure | `src/infrastructure/**` | Integrations: Postgres/SQLite, Redis, external APIs (Gemini, OpenAI, news), security, telemetry, audit, resilience | All external side effects live here. |
| Analytics & Offline Jobs | `advanced_analytics_engine.py`, `analytics_database_integration.py` | Quant metrics, portfolio analytics, caching | Standalone async workers or cron jobs. |
| Deployment & Ops | `docker-compose.yml`, `deploy_*.sh`, `manual_deployment_guide.md` | Provisioning scripts, systemd helpers, VPS runbooks | Docker + bare‑metal scripts provided.

### Runtime Topology

- **FastAPI ASGI app** behind WAF & rate limiting middleware.
- **Redis** (async) for cache, sessions, rate counters, audit queues, SLO metrics.
- **PostgreSQL** (recommended) or SQLite fallback (`DATABASE_URL` env). ORM: SQLAlchemy async.
- **Optional bot workers**: CLI/daemon processes in `bot/` connecting to exchanges.
- **Observability stack** via OpenTelemetry → OTLP collector (configurable endpoint).

## 2. API Surface (FastAPI v2)

All routes require HTTPS and, unless flagged as public, a Bearer token issued by `/api/v2/users/login`. Rate limiting happens in middleware (default: 100 requests/minute/IP).

### 2.1 User & Auth (`src/presentation/api/v2/users.py`)

| Method | Path | Auth | Description | Implementation Notes |
| --- | --- | --- | --- | --- |
| POST | `/api/v2/users/register` | Public (rate limited 5/h) | Register new user. Validates strong password (Pydantic). | Persists via `UserService` → SQL repo. Hashing: Argon2 (Passlib). |
| POST | `/api/v2/users/login` | Public (rate limited 10/h) | Authenticate, emit session token. | Session stored in Redis (`session:{token}`), last login updated. |
| GET | `/api/v2/users/me` | Bearer token | Retrieve current user profile. | Returns domain entity serialized to Pydantic. |
| POST | `/api/v2/users/logout` | Bearer token | Invalidate session token. | Deletes Redis keys `session:*` + cached user snapshot. |

### 2.2 Trading API (`src/presentation/api/v2/trading.py`)

> **Status:** Currently returns mock/synthetic data while storage/exchange connectors are being wired. Each handler records an audit event.

| Method | Path | Auth | Purpose | Data Source |
| --- | --- | --- | --- | --- |
| GET | `/api/v2/trading/portfolio` | Bearer | Portfolio KPIs (balance, PnL, win rate). | Randomized placeholder values. |
| GET | `/api/v2/trading/positions` | Bearer | Active positions list. | Synthetic list w/ random symbol data. |
| GET | `/api/v2/trading/market-data` | Optional | Market snapshot for given symbols. | In-memory base prices + random drift. |
| GET/POST | `/api/v2/trading/settings` | Bearer | Fetch/update user trading prefs. | Mock data; update endpoint just echoes payload. |
| GET | `/api/v2/trading/ai-insights/{symbol}` | Bearer | Gemini-powered trading insight JSON. | Calls `GeminiService.get_trading_insights`; cached in Redis. |
| POST | `/api/v2/trading/execute-trade` | Bearer | Submit mock order. | Validates payload, returns synthetic fill info. |
| GET | `/api/v2/trading/exchange-status` | Bearer | Connection health for supported exchanges. | Static stub.
| GET | `/api/v2/trading/news-sentiment/{symbol}` | Bearer | AI news sentiment summary. | Gemini sentiment + mock news. |
| GET | `/api/v2/trading/news/{symbol}` | Bearer | Recent news list. | `web_search_service.search_crypto_news` (mock). |
| GET | `/api/v2/trading/market-overview` | Bearer | Macro overview (cap, dominance). | Mock; caching via Redis. |
| GET | `/api/v2/trading/signals/{symbol}` | Bearer | Trading signals digest. | `web_search_service.search_trading_signals` stub. |
| GET | `/api/v2/trading/social-sentiment/{symbol}` | Bearer | Social sentiment stats. | `web_search_service.get_social_sentiment` stub. |

### 2.3 Debug & Ops (`src/presentation/api/v2/debug.py`)

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/api/v2/debug/health-comprehensive` | Bearer | Aggregated health check across DB, cache, AI, external services, WAF, SLO, circuit breakers. |
| GET | `/api/v2/debug/test-all-endpoints` | Bearer | Sanity-check of core routes (mock). |
| POST | `/api/v2/debug/clear-cache` | Admin only | Flush Redis patterns (uses role check). |
| GET | `/api/v2/debug/performance-metrics` | Public | Returns SLO stats + circuit breaker states.

### 2.4 Compatibility & Misc

- `POST /api/login` — Legacy V1 login proxying to V2 (`v1_compatibility.py`).
- `GET /health` — Simple liveness probe (no auth).
- `GET /slo` — SLO dashboard data.
- `POST /admin/waf/unblock/{ip}`, `/admin/waf/clear-blocks` — Emergency WAF controls (no auth gating yet; should be restricted upstream).
- Web pages: `/`, `/login`, `/register`, `/dashboard` render via Jinja templates.
- WebSocket: `GET /ws` -> `TradingWebSocket` handler with channel subscriptions and simulated price feed broadcast.

## 3. Authentication, Authorization & Sessions

- **Bearer tokens** are opaque session IDs generated by `UserService.authenticate_user`.
- Tokens stored in Redis: `session:{token}` (24h TTL) + cached user snapshot `user:session:{token}`.
- `get_current_user` dependency validates token, raises 401 if missing/expired.
- Rate limiting uses middleware + Redis counters per IP/path (`rate_limit:{ip}:{route}`).
- Passwords hashed with Argon2 (fallback to bcrypt for legacy). Strength enforced via Pydantic validators.

## 4. Data Storage & Persistence

### 4.1 Primary Database

- **Engine:** PostgreSQL recommended (`Settings.database_url`), async via `create_async_engine`.
- **Models:** Defined in `src/infrastructure/database/models.py` — Users, Sessions, TradingBots, Transactions.
- **RLS Support:** `get_db_session(user_id)` sets `app.current_user_id` for row-level security policies.
- **Monitoring:** SQLAlchemy events capture slow queries (>100ms) and export histogram metric (`db_query_duration`).

### 4.2 Cache & Session Store

- **Redis** in `src/infrastructure/cache/redis_cache.py` (async, JSON-serialized values).
- Usage: session tokens, rate limits, AI output caching, audit events, SLO buckets, analytics caches.
- Circuit breakers wrap Redis/DB operations to tolerate outages (`src/infrastructure/resilience/circuit_breaker.py`).

### 4.3 Analytics Tables

- Standalone scripts (`analytics_database_integration.py`) write to SQLite/Postgres tables such as `portfolio_snapshots`, `trading_metrics_cache`.
- Calculates Sharpe ratio, VAR, max drawdown, caches results with TTLs.
- Designed to run as async background jobs; ensures data freshness via periodic tasks.

### 4.4 Bot Data Layer (Standalone Worker)

- `bot/db.py` implements SQLAlchemy ORM (synchronous) for bot operations, defaulting to SQLite `trading.db`.
- Tables for Positions, Orders, Fills, Trading Stats, Risk Events, Strategy performance, AI analyses, Portfolio snapshots.
- `DatabaseManager` context manager simplifies CRUD with commit/rollback semantics.

## 5. Analytics & Quant Modules

- **`advanced_analytics_engine.py`** — Portfolio & risk analytics (Sharpe, Sortino, drawdown, VaR, CVaR, diversification). Uses NumPy, pandas, SciPy, scikit-learn.
- **`analytics_database_integration.py`** — Bridges analytics results into database, provides scheduled batch calculations and dashboard APIs.
- **Inputs** expected: equity curves, trade logs, market prices. Many functions include safeguards to return neutral metrics when insufficent data.
- **Outputs:** `AnalyticsResult` dataclass with metric, confidence intervals, additional context and timestamp.

## 6. AI & Prompting Strategy

### 6.1 Gemini Service (`src/infrastructure/ai/gemini_service.py`)

- Wraps Google Gemini `gemini-1.5-pro` (configurable) with safety settings.
- Caches responses (Redis) per symbol/timeframe: insights TTL 15 min, sentiment TTL 30 min.
- Tracks daily usage vs `ai_daily_budget_usd`: caches usage in `ai:usage:{date}` to throttle requests.
- Sanitizes user data before sending to AI; adds disclaimers in prompts.

### 6.2 OpenAI Fallback (`src/infrastructure/ai/openai_service.py`)

- Provides mock/simulated analytics when Gemini API unavailable.
- Computes trend, levels, sentiment heuristics without API calls (all synthetic).

### 6.3 Prompt Library (`bot/prompts/*.txt`)

- `market_analysis_prompt.txt` — Multi-layer quant research brief focusing on PrimeXBT derivatives; includes guardrails, required outputs, JSON schema.
- `trade_execution_prompt.txt` — Execution runbook with strict gating for live/paper trades, risk checks, JSON schema for autopilot decisions.
- Prompts emphasize disclaimers, probability calibration, and risk-of-ruin reporting.

### 6.4 AI Governance

- Audit logging (`AuditLogger`) records each AI call success/failure with sanitized payload references.
- Circuit breaker `ai_breaker` prevents cascading failures when API is degraded.
- Sentiment/trading insights include caching + budget enforcement to avoid runaway costs.

## 7. External Integrations

| Integration | Module | Purpose | Notes |
| --- | --- | --- | --- |
| News & Market Web Search | `src/infrastructure/external/websearch.py` | Fetches crypto news, market overview, signals, social sentiment. Currently mock data with caching. | Decorated with circuit breakers and uses aiohttp session pool. |
| Exchange Connectivity | `bot/exchange_manager.py` | Handles OAuth/API-key storage for Binance, Bybit, PrimeXBT. Encrypts credentials, tests keys, stores in DB. | Relies on `bot/security` manager; ensures masked keys, supports OAuth flows. |
| Email/Ops | `bot/email_notifications.py` (not fully inspected) | Notifications & alerts. | Use SMTP settings from `.env`. |
| Observability | `src/infrastructure/observability/telemetry.py` | OpenTelemetry exporters, metrics, tracing decorators. | Exposes histograms/counters used by middleware.

## 8. Security Controls

- **CSP middleware** adds strict headers, nonces per request, sets HSTS, COOP/COEP, etc.
- **WAF middleware** inspects IPs, SQLi/XSS patterns, rate-limits, manages allow/block lists.
- **RateLimit middleware** (Redis-based) gracefully degrades if Redis unavailable.
- **Audit logging** captures user actions (`AuditAction` enum) with sanitization, stores in Redis for up to 1 hour, future DB sink placeholder.
- **Password hashing** uses Argon2/bcrypt; secrets loaded via Pydantic `SecretStr` with validation (rejects placeholder values).
- **Circuit breakers** guard DB (`database_breaker`), Redis (`redis_breaker`), AI (`ai_breaker`), web search, etc.
- **SIEM hooks** (`siem_logger`) prepared for forwarding high severity events.

## 9. Observability & SLO Tracking

- OpenTelemetry instrumentation for FastAPI, SQLAlchemy, Redis, logging, system metrics.
- Metrics created: `http_requests_total`, `http_request_duration_seconds`, `db_query_duration_seconds`, cache hits/misses.
- `slo_monitor` tracks availability, latency P95, error rate, login success rate via Redis buckets. Alerts stored under `alerts:slo:*` and optionally forwarded.
- `debug/health-comprehensive` endpoint aggregates health across stack (DB ping, Redis info, AI usage, WAF stats, circuit states).

## 10. Infrastructure & Deployment Requirements

### 10.1 Environment Variables (`src/infrastructure/config/settings.py`)

| Variable | Required | Description |
| --- | --- | --- |
| `DATABASE_URL` | ✅ | Postgres DSN (async) or fallback to SQLite. Must not be empty/default. |
| `REDIS_URL` | ✅ | Redis connection string (e.g., `redis://:password@host:6379/0`). |
| `SECRET_KEY` | ✅ | Signing/encryption seed (non-default). |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL` | ✅ | Email delivery. |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` | ✅ | Push notifications. |
| `OTEL_EXPORTER_ENDPOINT` | Optional | Enables OpenTelemetry export when set. |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` | Optional | AI providers (Gemini required for live AI features). |
| `RATE_LIMIT_MAX_REQUESTS`, `RATE_LIMIT_WINDOW_SECONDS` | Optional | Override rate limiting defaults. |

Additional `.env` values used by `bot/config.py` for exchange access (API keys, OAuth client IDs), autopilot gates (`CONFIRM=YES`).

### 10.2 Server Sizing Guidance

| Component | Recommended Minimum (Prod) |
| --- | --- |
| API Server | 2 vCPU, 4–8 GB RAM, SSD storage; run under Uvicorn + Gunicorn workers. |
| Redis | Managed or local instance with persistence disabled for session cache; 1–2 GB RAM. |
| Postgres | Managed or containerized, 2 vCPU, 4 GB RAM, automated backups. |
| Worker Nodes (analytics/bot) | Optional 1–2 vCPU, 2–4 GB RAM depending on concurrency. |

GPU not required unless extending AI workloads locally. Ensure low-latency connectivity to exchanges if running live autopilot.

### 10.3 Deployment Tooling

- **Docker** (`docker-compose.yml`, `Dockerfile.v2`) for containerized deployment.
- **Shell scripts** (`deploy_*.sh`, `auto_deploy.sh`, `monitor.sh`, etc.) for VPS automation, systemd management, debugging.
- **Manual guides** in root (`MANUAL_DEPLOYMENT*.md`, `DEPLOYMENT_GUIDE.md`) provide step-by-step instructions for provisioning, firewall, SSL, service restart.

## 11. Known Gaps & TODOs

- Trading endpoints still return mock data—needs integration with real exchange/bot services (`bot/exchange_manager`, `bot/auto_trader`).
- Audit logger persistence layer unimplemented (currently only Redis). Planned: dedicated `audit_log` table or external log sink.
- Admin endpoints lack authentication guard; restrict via reverse proxy/API gateway.
- `debug/clear-cache` ensures admin role but relies on `current_user.role`; confirm domain values align (`UserRole.ADMIN`).
- Schema migrations handled via Alembic project under `alembic/`; ensure migrations kept up to date with models.
- Need background job runner to execute analytics batch (`AnalyticsIntegrationManager.schedule_analytics_calculation`).
- Provide production-ready rate limiting (per user + per token) and IP allowlists for WAF.
- WebSocket authentication currently expects token in first message; consider URL query or header-level auth.

## 12. Quick Start References

1. **Install dependencies:** `pip install -r requirements.txt` (or use poetry/pyproject for analytics engine).
2. **Set environment:** copy `env.example` → `.env`, populate secrets.
3. **Run database migrations:** `alembic upgrade head` (for async Postgres). For bot SQLite, run `create_tables.py`.
4. **Launch API:** `uvicorn src.main:app --host 0.0.0.0 --port 8000` (behind reverse proxy recommended).
5. **Start background analytics (optional):** run `python analytics_database_integration.py` or integrate into Celery/task runner.
6. **Monitor health:** call `/api/v2/debug/health-comprehensive`, monitor OpenTelemetry collector, tail logs with trace IDs.

## 13. Appendix: Key Modules At a Glance

- **Security** — `src/presentation/middleware/security.py`, `src/infrastructure/security/waf.py`, `bot/security.py`.
- **Resilience** — `src/infrastructure/resilience/circuit_breaker.py` (global manager & decorators).
- **Audit** — `src/infrastructure/audit/audit_service.py` (event logging, security alerts).
- **Monitoring** — `src/infrastructure/monitoring/slo.py` + `src/infrastructure/observability/telemetry.py`.
- **Bot Ops** — Exchange connectors, AI analytics, notification systems under `bot/`.

---

_This document reflects repository state as of 2 October 2025 and should be revisited after significant feature releases or infrastructure changes._
