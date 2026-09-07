# DaantShaant Production Deployment Guide

> **Target Domain:** [https://daantshaant.codemelodies.com](https://daantshaant.codemelodies.com)  
> **Repository:** `Develosphere/DaantShaant`  
> **Deployment Method:** GitHub Actions CI/CD over Secure SSH + PM2 Process Management

---

## 1. Production Architecture Overview

```text
[Internet / Browser]
        │
        ▼ (HTTPS :443)
┌──────────────────────────────────────────────────────────┐
│ Apache Reverse Proxy (SSL Termination & Route Isolation) │
│                                                          │
│  /           ──► Next.js Frontend     (127.0.0.1:3107)   │
│  /backend/   ──► FastAPI Orchestrator (127.0.0.1:8107)   │
└──────────────────────────────────────────────────────────┘
                            │
               ┌────────────┴────────────┐
               ▼ (Internal HTTP)         ▼ (Internal HTTP)
   ┌───────────────────────┐ ┌───────────────────────┐
   │ Teeth Analyzer :8108  │ │ Diagnosis :8109       │
   │ (DentalTensor Vision) │ │ (Deterministic Rules) │
   └───────────────────────┘ └───────────────────────┘
               │
               ▼ (Direct External)
   ┌─────────────────────────────────────────────────┐
   │ Supabase PostgreSQL DB / Alibaba Model Studio   │
   └─────────────────────────────────────────────────┘
```

All backend microservices bind strictly to `127.0.0.1`. Only Apache listens on public HTTP/HTTPS ports (80/443).

---

## 2. Production Server & Port Specifications

| Service | Technology | Port | Binding | PM2 Process Name | Health Endpoint |
|---|---|---|---|---|---|
| **Frontend** | Next.js 14 | `3107` | `127.0.0.1` | `daantshaant-web` | `http://127.0.0.1:3107/` |
| **Orchestrator** | FastAPI + Uvicorn | `8107` | `127.0.0.1` | `daantshaant-orchestrator` | `http://127.0.0.1:8107/health` |
| **Teeth Analyzer** | FastAPI + YOLO11n | `8108` | `127.0.0.1` | `daantshaant-teeth-analyzer` | `http://127.0.0.1:8108/health` |
| **Diagnosis** | FastAPI + Triage | `8109` | `127.0.0.1` | `daantshaant-diagnosis` | `http://127.0.0.1:8109/health` |

- **VPS Host:** `137.74.41.148`
- **SSH Port:** `2221`
- **SSH User:** `webadmin`
- **Application Directory:** `/var/www/html/daantshaant.codemelodies.com`

---

## 3. GitHub Actions Secrets Configuration

In your GitHub repository settings (`Settings -> Secrets and variables -> Actions`), configure the following 6 secrets:

| Secret Name | Description | Example / Value |
|---|---|---|
| `DAANTSHAANT_VPS_HOST` | Production server IP or hostname | `137.74.41.148` |
| `DAANTSHAANT_VPS_PORT` | Custom SSH port on production server | `2221` |
| `DAANTSHAANT_VPS_USER` | Deploy user with write permissions to app dir | `webadmin` |
| `DAANTSHAANT_VPS_APP_DIR` | Absolute path to repository on VPS | `/var/www/html/daantshaant.codemelodies.com` |
| `DAANTSHAANT_VPS_SSH_KEY` | Private SSH key for `webadmin` user | `-----BEGIN OPENSSH PRIVATE KEY-----...` |
| `DAANTSHAANT_VPS_KNOWN_HOSTS` | Known host key string for VPS SSH host & port | Output of `ssh-keyscan` command |

### Generating the Host Key Secret:
To populate `DAANTSHAANT_VPS_KNOWN_HOSTS`, run locally:
```bash
ssh-keyscan -p 2221 137.74.41.148
```
Paste the complete output directly into the `DAANTSHAANT_VPS_KNOWN_HOSTS` secret.

---

## 4. VPS Prerequisites

Ensure the following tools are installed and available in `webadmin`'s PATH:

1. **Node.js (v18.x or v20.x LTS) & npm:**
   ```bash
   node -v
   npm -v
   ```
2. **PM2 Process Manager:**
   ```bash
   npm install -g pm2
   pm2 startup
   ```
3. **Python (3.11+) and `uv`:**
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   source ~/.cargo/env
   uv --version
   ```

---

## 5. One-Time Production VPS Environment Setup

Before triggering the first deployment, configure the production environment files directly on the VPS.

### A. Root Backend Environment: `/var/www/html/daantshaant.codemelodies.com/.env`
```env
APP_ENV=production
LOG_LEVEL=INFO
APP_FRONTEND_URL=https://daantshaant.codemelodies.com
CORS_ORIGINS=https://daantshaant.codemelodies.com,http://127.0.0.1:3107

# Ports & Internal Microservice Routing
ORCHESTRATOR_HOST=127.0.0.1
ORCHESTRATOR_PORT=8107
ORCHESTRATOR_TEETH_ANALYZER_URL=http://127.0.0.1:8108
ORCHESTRATOR_DIAGNOSIS_URL=http://127.0.0.1:8109

TEETH_ANALYZER_HOST=127.0.0.1
TEETH_ANALYZER_PORT=8108
TEETH_ANALYZER_REJECT_LOW_QUALITY=false

DIAGNOSIS_HOST=127.0.0.1
DIAGNOSIS_PORT=8109

# Model Weight Path
YOLO_DENTAL_MODEL_PATH=services/teeth_analyzer/models/oral_disease/dentaltensor_nathan_asif_v1.pt
YOLO_DENTAL_CONFIDENCE_THRESHOLD=0.50

# Supabase PostgreSQL Application Persistence
DATABASE_URL=postgresql+asyncpg://<postgres_user>:<postgres_password>@<supabase_host>:5432/postgres
DATABASE_MIGRATION_URL=postgresql://<postgres_user>:<postgres_password>@<supabase_host>:5432/postgres

# Auth
JWT_SECRET=<strong-random-64-character-hex-secret>
AUTH_COOKIE_SECURE=true

# Alibaba Model Studio (Primary AI Chat & Screening)
DASHSCOPE_API_KEY=<your-dashscope-api-key>
QWEN_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
CHAT_LLM_PROVIDER=qwen
CHAT_QWEN_MODEL=qwen3.7-flash
CHAT_QWEN_ENABLE_THINKING=false

# Google Gemini (Secondary AI Fallback)
GEMINI_API_KEY=<your-gemini-api-key>
CHAT_FALLBACK_PROVIDER=gemini
CHAT_GEMINI_MODEL=gemini-flash-lite-latest
```

### B. Frontend Environment: `/var/www/html/daantshaant.codemelodies.com/apps/web/.env.production`
```env
NEXT_PUBLIC_ORCHESTRATOR_URL=https://daantshaant.codemelodies.com/backend
NEXT_PUBLIC_ORCHESTRATOR_WS=wss://daantshaant.codemelodies.com/backend
```

### C. Verify DentalTensor Checkpoint
Ensure the canonical model file is present at:
`/var/www/html/daantshaant.codemelodies.com/services/teeth_analyzer/models/oral_disease/dentaltensor_nathan_asif_v1.pt`

---

## 6. Apache Reverse Proxy Configuration

Create or update `/etc/apache2/sites-available/daantshaant.codemelodies.com.conf`:

```apache
<VirtualHost *:80>
    ServerName daantshaant.codemelodies.com
    ServerAdmin webadmin@codemelodies.com

    RewriteEngine On
    RewriteCond %{HTTPS} off
    RewriteRule ^(.*)$ https://%{HTTP_HOST}%{REQUEST_URI} [L,R=301]
</VirtualHost>

<VirtualHost *:443>
    ServerName daantshaant.codemelodies.com
    ServerAdmin webadmin@codemelodies.com

    SSLEngine on
    SSLCertificateFile /etc/letsencrypt/live/daantshaant.codemelodies.com/fullchain.pem
    SSLCertificateKeyFile /etc/letsencrypt/live/daantshaant.codemelodies.com/privkey.pem

    # Proxy preserve host and headers
    ProxyPreserveHost On
    ProxyRequests Off
    RequestHeader set X-Forwarded-Proto "https"
    RequestHeader set X-Forwarded-Port "443"

    # 1. WebSocket endpoint for live camera feed
    RewriteCond %{HTTP:Upgrade} websocket [NC]
    RewriteCond %{HTTP:Connection} upgrade [NC]
    RewriteRule ^/backend/?(.*) "ws://127.0.0.1:8107/$1" [P,L]

    # 2. REST API forward to FastAPI Orchestrator (:8107)
    ProxyPass /backend/ http://127.0.0.1:8107/
    ProxyPassReverse /backend/ http://127.0.0.1:8107/

    # 3. Frontend Next.js SSR and Static Assets (:3107)
    ProxyPass / http://127.0.0.1:3107/
    ProxyPassReverse / http://127.0.0.1:3107/

    ErrorLog ${APACHE_LOG_DIR}/daantshaant_error.log
    CustomLog ${APACHE_LOG_DIR}/daantshaant_access.log combined
</VirtualHost>
```

Enable required Apache modules and reload:
```bash
sudo a2enmod proxy proxy_http proxy_wstunnel rewrite headers ssl
sudo a2ensite daantshaant.codemelodies.com.conf
sudo apache2ctl configtest
sudo systemctl reload apache2
```

---

## 7. Deployment Pipeline Mechanics

Every `git push origin main` or manual `workflow_dispatch` executes:

1. **SSH Connection & Authenticated Handshake:** Connects using `DAANTSHAANT_VPS_SSH_KEY` without interactive prompts.
2. **Repository Synchronization:** Clones on first run; fetches and hard-resets to `origin/main` on subsequent deploys (preserving `.env`, venvs, and `.deploy-cache`).
3. **Environment & Checkpoint Validation:** Verifies `.env`, `apps/web/.env.production`, and `dentaltensor_nathan_asif_v1.pt`.
4. **Port Safety Inspection:** `ss` checks ports `3107`, `8107`, `8108`, `8109` to guarantee no third-party processes are disturbed.
5. **SHA-256 Dependency Caching:**
   - Evaluates `apps/web/package.json` + `apps/web/package-lock.json` -> executes `npm ci` only if changed.
   - Evaluates Python `pyproject.toml` + `uv.lock` for each service -> executes `uv sync --frozen` only if changed.
6. **Production Next.js Build:** Executes `npm run build` in `apps/web`.
7. **PM2 Zero-Downtime Reload:** `pm2 startOrReload ecosystem.config.cjs --update-env && pm2 save`.
8. **Health Check Probing:** 10 bounded retries across all 4 microservice endpoints.

---

## 8. Useful PM2 Operational Commands

```bash
# Check service status
pm2 status

# View live aggregate logs
pm2 logs

# View specific microservice logs
pm2 logs daantshaant-orchestrator --lines 50
pm2 logs daantshaant-teeth-analyzer --lines 50
pm2 logs daantshaant-diagnosis --lines 50
pm2 logs daantshaant-web --lines 50

# Restart individual microservice manually
pm2 reload daantshaant-orchestrator
```
