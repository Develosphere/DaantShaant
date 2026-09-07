#!/usr/bin/env bash
# ==============================================================================
# DaantShaant Production Deployment Script
#
# Production domain:  https://daantshaant.codemelodies.com
# Candidate ports:    Next.js (3107), Orchestrator (8107),
#                     Teeth Analyzer (8108), Diagnosis (8109)
#
# Runtime Architecture:
#   - Frontend (Next.js): PM2 (daantshaant-web ONLY) on 127.0.0.1:3107
#   - Backend Python Services: systemd --user services
#       * daantshaant-orchestrator.service   (127.0.0.1:8107)
#       * daantshaant-teeth-analyzer.service (127.0.0.1:8108)
#       * daantshaant-diagnosis.service      (127.0.0.1:8109)
#   - Python: Standard python3 -m venv (.venv) + pip editable installs + Uvicorn
#   - Node.js: Next.js 14 SSR + npm ci (cached)
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${APP_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
cd "$APP_DIR"

echo "[DEPLOY] ======================================================"
echo "[DEPLOY] Starting DaantShaant Production VPS Deployment"
echo "[DEPLOY] Working directory: $APP_DIR"
echo "[DEPLOY] User: $(whoami) (UID: $(id -u))"
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
  echo "[ERROR] Deployment aborted. Install python3-venv on the VPS (e.g. sudo apt install python3-venv)."
  exit 1
fi

# PM2 inspection (used for daantshaant-web frontend ONLY)
if ! command -v pm2 >/dev/null 2>&1; then
  echo "[ERROR] PM2 is not installed or not available in PATH on this VPS."
  echo "[ERROR] Deployment aborted. DaantShaant frontend process management requires PM2."
  exit 1
fi

# systemd user manager verification
echo "[DEPLOY] Inspecting user systemd environment..."
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
if [ -d "$XDG_RUNTIME_DIR" ] && [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
  if [ -S "$XDG_RUNTIME_DIR/bus" ]; then
    export DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR}/bus"
  fi
fi

if ! command -v systemctl >/dev/null 2>&1; then
  echo "[ERROR] systemctl is not available in PATH on this VPS."
  echo "[ERROR] Deployment aborted. DaantShaant Python microservices require systemd."
  exit 1
fi

if ! systemctl --user list-units >/dev/null 2>&1; then
  echo "[ERROR] systemd user manager is not accessible for user $(whoami) (UID: $(id -u))."
  echo "[ERROR] Possible causes: user lingering is not enabled or XDG_RUNTIME_DIR is not mounted."
  echo "[ERROR] To enable lingering on the VPS, Nathan must execute once:"
  echo "[ERROR]   sudo loginctl enable-linger $(whoami)"
  echo "[ERROR] and verify that /run/user/$(id -u) is active."
  echo "[ERROR] Deployment aborted."
  exit 1
fi
echo "[DEPLOY] systemd user manager verified."

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
# 8. Systemd User Services Installation & Daemon Reload
# ------------------------------------------------------------------------------
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_USER_DIR"

echo "[DEPLOY] Installing DaantShaant systemd service units to $SYSTEMD_USER_DIR..."
cp "$APP_DIR/deploy/systemd/daantshaant-orchestrator.service" "$SYSTEMD_USER_DIR/"
cp "$APP_DIR/deploy/systemd/daantshaant-teeth-analyzer.service" "$SYSTEMD_USER_DIR/"
cp "$APP_DIR/deploy/systemd/daantshaant-diagnosis.service" "$SYSTEMD_USER_DIR/"

echo "[DEPLOY] Reloading systemd user daemon..."
systemctl --user daemon-reload

# ------------------------------------------------------------------------------
# 9. Migrate Legacy Python Processes off PM2 (Before starting systemd services)
# ------------------------------------------------------------------------------
if command -v pm2 >/dev/null 2>&1; then
  echo "[DEPLOY] Inspecting PM2 for legacy Python processes to migrate..."
  LEGACY_PM2_MIGRATED=0
  for legacy_proc in daantshaant-orchestrator daantshaant-teeth-analyzer daantshaant-diagnosis; do
    if pm2 describe "$legacy_proc" >/dev/null 2>&1; then
      echo "[DEPLOY] Stopping and removing legacy PM2 process: $legacy_proc..."
      pm2 stop "$legacy_proc" >/dev/null 2>&1 || true
      pm2 delete "$legacy_proc" >/dev/null 2>&1 || true
      LEGACY_PM2_MIGRATED=1
    fi
  done
  if [ "$LEGACY_PM2_MIGRATED" -eq 1 ]; then
    echo "[DEPLOY] Saving PM2 state after removing legacy Python processes..."
    pm2 save
  fi
fi

# ------------------------------------------------------------------------------
# 10. Enable and Restart Systemd Python Microservices
# ------------------------------------------------------------------------------
echo "[DEPLOY] Enabling DaantShaant systemd user services..."
systemctl --user enable daantshaant-orchestrator.service
systemctl --user enable daantshaant-teeth-analyzer.service
systemctl --user enable daantshaant-diagnosis.service

echo "[DEPLOY] Restarting DaantShaant systemd user services..."
systemctl --user restart daantshaant-orchestrator.service
systemctl --user restart daantshaant-teeth-analyzer.service
systemctl --user restart daantshaant-diagnosis.service

# ------------------------------------------------------------------------------
# 11. PM2 Process Management (Frontend Only)
# ------------------------------------------------------------------------------
echo "[DEPLOY] Reloading PM2 frontend service (daantshaant-web only)..."
pm2 startOrReload ecosystem.config.cjs --only daantshaant-web --update-env
pm2 save
echo "[DEPLOY] PM2 frontend configuration reloaded and state saved."

# ------------------------------------------------------------------------------
# 12. Health Checks
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

FRONTEND_HEALTH=0
ORCHESTRATOR_HEALTH=0
TEETH_ANALYZER_HEALTH=0
DIAGNOSIS_HEALTH=0

check_endpoint "Orchestrator" "http://127.0.0.1:8107/health" || ORCHESTRATOR_HEALTH=1
check_endpoint "Teeth Analyzer" "http://127.0.0.1:8108/health" || TEETH_ANALYZER_HEALTH=1
check_endpoint "Diagnosis" "http://127.0.0.1:8109/health" || DIAGNOSIS_HEALTH=1
check_endpoint "Frontend (Next.js)" "http://127.0.0.1:3107/" || FRONTEND_HEALTH=1

HEALTH_FAILED=$((FRONTEND_HEALTH + ORCHESTRATOR_HEALTH + TEETH_ANALYZER_HEALTH + DIAGNOSIS_HEALTH))

if [ "$HEALTH_FAILED" -ne 0 ]; then
  echo ""
  echo "[ERROR] One or more DaantShaant services failed health checks."

  if [ "$FRONTEND_HEALTH" -ne 0 ]; then
    echo ""
    echo "[DIAGNOSTIC] === DaantShaant Frontend (Next.js) Diagnostics ==="
    pm2 describe daantshaant-web || true
    pm2 logs daantshaant-web --lines 40 --nostream || true
  fi

  if [ "$ORCHESTRATOR_HEALTH" -ne 0 ]; then
    echo ""
    echo "[DIAGNOSTIC] === daantshaant-orchestrator Service Diagnostics ==="
    systemctl --user status daantshaant-orchestrator.service --no-pager || true
    journalctl --user-unit daantshaant-orchestrator.service -n 40 --no-pager || true
  fi

  if [ "$TEETH_ANALYZER_HEALTH" -ne 0 ]; then
    echo ""
    echo "[DIAGNOSTIC] === daantshaant-teeth-analyzer Service Diagnostics ==="
    systemctl --user status daantshaant-teeth-analyzer.service --no-pager || true
    journalctl --user-unit daantshaant-teeth-analyzer.service -n 40 --no-pager || true
  fi

  if [ "$DIAGNOSIS_HEALTH" -ne 0 ]; then
    echo ""
    echo "[DIAGNOSTIC] === daantshaant-diagnosis Service Diagnostics ==="
    systemctl --user status daantshaant-diagnosis.service --no-pager || true
    journalctl --user-unit daantshaant-diagnosis.service -n 40 --no-pager || true
  fi

  exit 1
fi

echo "[DEPLOY] ======================================================"
echo "[DEPLOY] Deployment successful!"
echo "[DEPLOY] Next.js (PM2):               http://127.0.0.1:3107"
echo "[DEPLOY] Orchestrator (systemd):      http://127.0.0.1:8107"
echo "[DEPLOY] Teeth Analyzer (systemd):    http://127.0.0.1:8108"
echo "[DEPLOY] Diagnosis (systemd):         http://127.0.0.1:8109"
echo "[DEPLOY] Public URL:                  https://daantshaant.codemelodies.com"
echo "[DEPLOY] ======================================================"
