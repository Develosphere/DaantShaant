#!/usr/bin/env bash
# ==============================================================================
# DaantShaant Production Deployment Script
#
# Production domain:  https://daantshaant.codemelodies.com
# Candidate ports:    Next.js (3107), Orchestrator (8107),
#                     Teeth Analyzer (8108), Diagnosis (8109)
#
# Runtime Architecture:
#   - Python: Standard python3 -m venv (.venv) + pip editable installs + Uvicorn
#   - Node.js: Next.js 14 SSR + npm ci (cached)
#   - PM2: Process management (zero-downtime reloads)
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${APP_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
cd "$APP_DIR"

echo "[DEPLOY] ======================================================"
echo "[DEPLOY] Starting DaantShaant Production VPS Deployment"
echo "[DEPLOY] Working directory: $APP_DIR"
echo "[DEPLOY] ======================================================"

# ------------------------------------------------------------------------------
# 1. Environment Verification
# ------------------------------------------------------------------------------
echo "[DEPLOY] Verifying production environment configuration..."

if [ ! -f "$APP_DIR/.env" ]; then
  echo "[ERROR] Required root production environment file (.env) is missing at $APP_DIR/.env"
  echo "[ERROR] Deployment aborted. Production secrets must be pre-configured on the VPS."
  exit 1
fi

if [ ! -f "$APP_DIR/apps/web/.env.production" ]; then
  echo "[ERROR] Required frontend production environment file (apps/web/.env.production) is missing at $APP_DIR/apps/web/.env.production"
  echo "[ERROR] Deployment aborted. Frontend NEXT_PUBLIC_ variables must be pre-configured."
  exit 1
fi

echo "[DEPLOY] Production environment files verified (content remains private)."

# ------------------------------------------------------------------------------
# 2. DentalTensor Production Model Checkpoint Verification
# ------------------------------------------------------------------------------
echo "[DEPLOY] Verifying DentalTensor production model checkpoint..."
MODEL_CHECKPOINT="$APP_DIR/services/teeth_analyzer/models/oral_disease/dentaltensor_nathan_asif_v1.pt"

if [ ! -f "$MODEL_CHECKPOINT" ]; then
  echo "[ERROR] DentalTensor checkpoint not found at: $MODEL_CHECKPOINT"
  echo "[ERROR] Deployment aborted. The production model checkpoint must be present for inference."
  exit 1
fi

echo "[DEPLOY] DentalTensor checkpoint verified ($(du -h "$MODEL_CHECKPOINT" | cut -f1))."

# ------------------------------------------------------------------------------
# 3. System Runtime & Tooling Inspection
# ------------------------------------------------------------------------------
echo "[DEPLOY] Inspecting VPS system runtime prerequisites..."

# Node.js & npm inspection
if ! command -v node >/dev/null 2>&1; then
  echo "[ERROR] Node.js is not installed or not available in PATH on this VPS."
  echo "[ERROR] Deployment aborted. Next.js cannot run without Node.js."
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "[ERROR] npm is not installed or not available in PATH on this VPS."
  echo "[ERROR] Deployment aborted. Next.js dependencies and build require npm."
  exit 1
fi

NODE_VERSION=$(node --version)
NPM_VERSION=$(npm --version)
echo "[DEPLOY] Node runtime found: $NODE_VERSION, npm: $NPM_VERSION"

# Python 3 & venv inspection
if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] python3 is not installed or not available in PATH on this VPS."
  echo "[ERROR] Deployment aborted. DaantShaant backend requires Python 3.11+."
  exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1)
echo "[DEPLOY] Python runtime found: $PYTHON_VERSION"

if ! python3 -m venv --help >/dev/null 2>&1; then
  echo "[ERROR] python3-venv module is not available on this VPS."
  echo "[ERROR] Deployment aborted. Install python3-venv on the VPS (e.g. sudo apt install python3-venv or python3.<version>-venv)."
  exit 1
fi

# PM2 inspection
if ! command -v pm2 >/dev/null 2>&1; then
  echo "[ERROR] PM2 is not installed or not available in PATH on this VPS."
  echo "[ERROR] Deployment aborted. DaantShaant process management requires PM2."
  exit 1
fi

# ------------------------------------------------------------------------------
# 4. Port Safety Verification
# ------------------------------------------------------------------------------
export FRONTEND_PORT=3107
export ORCHESTRATOR_PORT=8107
export TEETH_ANALYZER_PORT=8108
export DIAGNOSIS_PORT=8109

chmod +x "$APP_DIR/scripts/check-production-ports.sh"
bash "$APP_DIR/scripts/check-production-ports.sh"

# ------------------------------------------------------------------------------
# 5. Persistent Cache Setup
# ------------------------------------------------------------------------------
CACHE_DIR="$APP_DIR/.deploy-cache"
mkdir -p "$CACHE_DIR"

compute_hash() {
  local files=("$@")
  local existing_files=()
  for f in "${files[@]}"; do
    if [ -f "$f" ]; then
      existing_files+=("$f")
    fi
  done

  if [ ${#existing_files[@]} -eq 0 ]; then
    echo "empty"
    return
  fi

  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "${existing_files[@]}" | sha256sum | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "${existing_files[@]}" | shasum -a 256 | awk '{print $1}'
  else
    cksum "${existing_files[@]}" | awk '{print $1}'
  fi
}

# ------------------------------------------------------------------------------
# 6. Python Backend Dependency Synchronization (Standard venv + pip)
# ------------------------------------------------------------------------------
PYTHON_CACHE_FILE="$CACHE_DIR/python-deps.sha256"
PYTHON_HASH=$(compute_hash \
  "$APP_DIR/packages/dantshaant_common/pyproject.toml" \
  "$APP_DIR/services/diagnosis/pyproject.toml" \
  "$APP_DIR/services/diagnosis/uv.lock" \
  "$APP_DIR/services/teeth_analyzer/pyproject.toml" \
  "$APP_DIR/services/teeth_analyzer/uv.lock" \
  "$APP_DIR/orchestrator/pyproject.toml" \
  "$APP_DIR/orchestrator/uv.lock" \
)

CACHED_PYTHON_HASH=""
if [ -f "$PYTHON_CACHE_FILE" ]; then
  CACHED_PYTHON_HASH=$(cat "$PYTHON_CACHE_FILE")
fi

VENV_DIR="$APP_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

if [ ! -d "$VENV_DIR" ] || [ ! -f "$VENV_PYTHON" ] || [ ! -f "$VENV_PIP" ] || [ "$PYTHON_HASH" != "$CACHED_PYTHON_HASH" ]; then
  if [ ! -d "$VENV_DIR" ] || [ ! -f "$VENV_PYTHON" ]; then
    echo "[DEPLOY] Creating production Python virtual environment (.venv)..."
    python3 -m venv "$VENV_DIR"
  fi

  echo "[DEPLOY] Upgrading pip in production virtual environment..."
  "$VENV_PYTHON" -m pip install --upgrade pip

  echo "[DEPLOY] Installing dantshaant_common..."
  "$VENV_PIP" install -e "$APP_DIR/packages/dantshaant_common"

  echo "[DEPLOY] Installing diagnosis service..."
  "$VENV_PIP" install -e "$APP_DIR/services/diagnosis"

  echo "[DEPLOY] Installing teeth_analyzer service..."
  "$VENV_PIP" install -e "$APP_DIR/services/teeth_analyzer"

  echo "[DEPLOY] Installing orchestrator service..."
  "$VENV_PIP" install -e "$APP_DIR/orchestrator"

  echo "$PYTHON_HASH" > "$PYTHON_CACHE_FILE"
  echo "[DEPLOY] Python backend dependencies installed successfully."
else
  echo "[DEPLOY] Python dependencies unchanged — skipping pip install"
fi

# ------------------------------------------------------------------------------
# 7. Frontend Dependency Synchronization & Build
# ------------------------------------------------------------------------------
WEB_DIR="$APP_DIR/apps/web"
WEB_CACHE_FILE="$CACHE_DIR/frontend-deps.sha256"

WEB_HASH=$(compute_hash "$WEB_DIR/package.json" "$WEB_DIR/package-lock.json")
CACHED_WEB_HASH=""
if [ -f "$WEB_CACHE_FILE" ]; then
  CACHED_WEB_HASH=$(cat "$WEB_CACHE_FILE")
fi

if [ ! -d "$WEB_DIR/node_modules" ] || [ "$WEB_HASH" != "$CACHED_WEB_HASH" ]; then
  echo "[DEPLOY] Frontend dependencies changed or missing — running npm ci..."
  (cd "$WEB_DIR" && npm ci)
  echo "$WEB_HASH" > "$WEB_CACHE_FILE"
  echo "[DEPLOY] Frontend dependencies installed successfully."
else
  echo "[DEPLOY] Frontend dependencies unchanged — skipping npm ci"
fi

echo "[DEPLOY] Building Next.js production application..."
(cd "$WEB_DIR" && npm run build)
echo "[DEPLOY] Next.js production build complete."

# ------------------------------------------------------------------------------
# 8. PM2 Process Management
# ------------------------------------------------------------------------------
echo "[DEPLOY] Restarting DaantShaant PM2 services..."
pm2 startOrReload ecosystem.config.cjs --update-env
pm2 save
echo "[DEPLOY] PM2 configuration reloaded and state saved."

# ------------------------------------------------------------------------------
# 9. Health Checks
# ------------------------------------------------------------------------------
echo "[DEPLOY] Health checks starting..."

check_endpoint() {
  local service_title="$1"
  local url="$2"
  local max_retries=10
  local interval=2
  local count=1

  echo "[DEPLOY] Probing $service_title at $url..."
  while [ "$count" -le "$max_retries" ]; do
    if curl -s -f -o /dev/null "$url"; then
      echo "[DEPLOY] [OK] $service_title responded with healthy status on attempt $count."
      return 0
    fi
    echo "[DEPLOY] Attempt $count/$max_retries failed. Waiting ${interval}s..."
    sleep "$interval"
    count=$((count + 1))
  done

  echo "[ERROR] $service_title failed to become healthy at $url after $max_retries attempts!"
  return 1
}

HEALTH_FAILED=0

check_endpoint "Orchestrator" "http://127.0.0.1:8107/health" || HEALTH_FAILED=1
check_endpoint "Teeth Analyzer" "http://127.0.0.1:8108/health" || HEALTH_FAILED=1
check_endpoint "Diagnosis" "http://127.0.0.1:8109/health" || HEALTH_FAILED=1
check_endpoint "Frontend (Next.js)" "http://127.0.0.1:3107/" || HEALTH_FAILED=1

if [ "$HEALTH_FAILED" -ne 0 ]; then
  echo ""
  echo "[ERROR] One or more DaantShaant services failed health checks."
  echo "[ERROR] Dumping PM2 status:"
  pm2 status
  echo ""
  echo "[ERROR] Dumping recent logs for DaantShaant services:"
  for p in daantshaant-web daantshaant-orchestrator daantshaant-teeth-analyzer daantshaant-diagnosis; do
    echo "--- Last 30 lines for $p ---"
    pm2 logs "$p" --lines 30 --nostream || true
  done
  exit 1
fi

echo "[DEPLOY] ======================================================"
echo "[DEPLOY] Deployment successful!"
echo "[DEPLOY] Next.js:          http://127.0.0.1:3107"
echo "[DEPLOY] Orchestrator:     http://127.0.0.1:8107"
echo "[DEPLOY] Teeth Analyzer:   http://127.0.0.1:8108"
echo "[DEPLOY] Diagnosis:        http://127.0.0.1:8109"
echo "[DEPLOY] Public URL:       https://daantshaant.codemelodies.com"
echo "[DEPLOY] ======================================================"
