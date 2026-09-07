#!/usr/bin/env bash
# ==============================================================================
# DaantShaant Production Port Safety Checker
#
# Inspects candidate ports:
#   Next.js:          3107 (owned by daantshaant-web PM2 / descendant next-server)
#   Orchestrator:     8107 (owned by active daantshaant-orchestrator.service)
#   Teeth Analyzer:   8108 (owned by active daantshaant-teeth-analyzer.service)
#   Diagnosis:        8109 (owned by active daantshaant-diagnosis.service)
#
# Rules:
#   - 3107: Safe when free OR owned by daantshaant-web / descendant next-server.
#   - 8107: Safe when free OR daantshaant-orchestrator.service is active (or legacy PM2 pending migration).
#   - 8108: Safe when free OR daantshaant-teeth-analyzer.service is active (or legacy PM2 pending migration).
#   - 8109: Safe when free OR daantshaant-diagnosis.service is active (or legacy PM2 pending migration).
#
# Fails clearly if any port is occupied by an external, non-DaantShaant process.
# Never kills or disturbs any process during the check.
# ==============================================================================

set -euo pipefail

# Ensure user systemd environment is set for non-interactive SSH
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
if [ -d "$XDG_RUNTIME_DIR" ] && [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
  if [ -S "$XDG_RUNTIME_DIR/bus" ]; then
    export DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR}/bus"
  fi
fi

FRONTEND_PORT="${FRONTEND_PORT:-3107}"
ORCHESTRATOR_PORT="${ORCHESTRATOR_PORT:-8107}"
TEETH_ANALYZER_PORT="${TEETH_ANALYZER_PORT:-8108}"
DIAGNOSIS_PORT="${DIAGNOSIS_PORT:-8109}"

echo "[PORTS] Running DaantShaant production port safety check..."

# ------------------------------------------------------------------------------
# Process Descendant Detection
# Traverses parent PIDs upwards to verify exact ownership by an ancestor PID
# (Fixes the PM2 -> npm -> next-server child process ownership bug)
# ------------------------------------------------------------------------------
is_pid_or_descendant() {
  local target_pid="$1"
  local ancestor_pid="$2"

  if [ -z "$target_pid" ] || [ -z "$ancestor_pid" ]; then
    return 1
  fi
  if ! [[ "$target_pid" =~ ^[0-9]+$ ]] || ! [[ "$ancestor_pid" =~ ^[0-9]+$ ]]; then
    return 1
  fi
  if [ "$target_pid" = "0" ] || [ "$ancestor_pid" = "0" ]; then
    return 1
  fi
  if [ "$target_pid" = "$ancestor_pid" ]; then
    return 0
  fi

  local cur="$target_pid"
  local depth=0
  local max_depth=15

  while [ -n "$cur" ] && [ "$cur" -gt 1 ] && [ "$depth" -lt "$max_depth" ]; do
    local parent
    parent=$(ps -o ppid= -p "$cur" 2>/dev/null | tr -d ' ' || true)
    if [ -z "$parent" ] || [ "$parent" = "$cur" ] || [ "$parent" -le 1 ]; then
      break
    fi
    if [ "$parent" = "$ancestor_pid" ]; then
      return 0
    fi
    cur="$parent"
    depth=$((depth + 1))
  done

  return 1
}

# ------------------------------------------------------------------------------
# Ownership Validators
# ------------------------------------------------------------------------------
is_owned_by_frontend() {
  local check_pid="$1"
  if ! command -v pm2 >/dev/null 2>&1; then
    return 1
  fi
  local pm2_pid
  pm2_pid=$(pm2 pid daantshaant-web 2>/dev/null || true)
  if [ -n "$pm2_pid" ] && [ "$pm2_pid" != "0" ] && [ "$pm2_pid" != "N/A" ]; then
    if is_pid_or_descendant "$check_pid" "$pm2_pid"; then
      return 0
    fi
  fi
  return 1
}

is_owned_by_systemd_service() {
  local check_pid="$1"
  local service_name="$2"

  if ! command -v systemctl >/dev/null 2>&1; then
    return 1
  fi

  # Service must be active in systemd --user
  if ! systemctl --user is-active --quiet "$service_name" 2>/dev/null; then
    return 1
  fi

  # Inspect MainPID for the user service
  local main_pid
  main_pid=$(systemctl --user show "$service_name" -p MainPID 2>/dev/null | grep -o 'MainPID=[0-9]*' | cut -d'=' -f2 || true)

  if [ -n "$main_pid" ] && [ "$main_pid" != "0" ]; then
    if is_pid_or_descendant "$check_pid" "$main_pid"; then
      return 0
    fi
  fi

  return 1
}

is_owned_by_legacy_pm2() {
  local check_pid="$1"
  local legacy_proc="$2"

  if ! command -v pm2 >/dev/null 2>&1; then
    return 1
  fi

  local pm2_pid
  pm2_pid=$(pm2 pid "$legacy_proc" 2>/dev/null || true)
  if [ -n "$pm2_pid" ] && [ "$pm2_pid" != "0" ] && [ "$pm2_pid" != "N/A" ]; then
    if is_pid_or_descendant "$check_pid" "$pm2_pid"; then
      return 0
    fi
  fi

  return 1
}

# ------------------------------------------------------------------------------
# Port Inspection
# ------------------------------------------------------------------------------
OCCUPIED_CONFLICT=0

check_service_port() {
  local port="$1"
  local svc_name="$2"
  local systemd_unit="$3"
  local legacy_pm2_name="$4"

  local listener_info
  listener_info=$(ss -tlnp "sport = :$port" 2>/dev/null | grep -E ":$port\b" || true)

  if [ -z "$listener_info" ]; then
    echo "[PORTS] Port $port ($svc_name): AVAILABLE"
    return 0
  fi

  # Extract all listening PIDs for this port
  local pids
  pids=$(echo "$listener_info" | grep -o 'pid=[0-9]*' | cut -d'=' -f2 | sort -u || true)

  if [ -z "$pids" ]; then
    echo "[ERROR] Port $port ($svc_name) is OCCUPIED by an unknown or non-DaantShaant process!"
    echo "        Listener details: $listener_info"
    OCCUPIED_CONFLICT=1
    return 1
  fi

  local port_has_conflict=0
  for pid in $pids; do
    if [ "$systemd_unit" = "NONE" ]; then
      # Frontend check (PM2 only)
      if is_owned_by_frontend "$pid"; then
        echo "[PORTS] Port $port ($svc_name): Owned by DaantShaant PM2 frontend (PID $pid, descendant of daantshaant-web) — safe to reload."
      else
        local proc_cmd
        proc_cmd=$(ps -p "$pid" -o args= 2>/dev/null || echo "unknown")
        echo "[ERROR] Port $port ($svc_name) is OCCUPIED by external process (PID: $pid, Command: $proc_cmd)!"
        port_has_conflict=1
      fi
    else
      # Python service check (systemd user unit, or legacy PM2 awaiting migration)
      if is_owned_by_systemd_service "$pid" "$systemd_unit"; then
        echo "[PORTS] Port $port ($svc_name): Owned by active systemd user service $systemd_unit (PID $pid) — safe."
      elif [ -n "$legacy_pm2_name" ] && is_owned_by_legacy_pm2 "$pid" "$legacy_pm2_name"; then
        echo "[PORTS] Port $port ($svc_name): Owned by legacy DaantShaant PM2 process $legacy_pm2_name (PID $pid) — safe to migrate."
      else
        local proc_cmd
        proc_cmd=$(ps -p "$pid" -o args= 2>/dev/null || echo "unknown")
        echo "[ERROR] Port $port ($svc_name) is OCCUPIED by external process (PID: $pid, Command: $proc_cmd)!"
        port_has_conflict=1
      fi
    fi
  done

  if [ "$port_has_conflict" -ne 0 ]; then
    OCCUPIED_CONFLICT=1
    return 1
  fi

  return 0
}

# 1. Frontend Next.js (:3107) - PM2 daantshaant-web only
check_service_port "$FRONTEND_PORT" "Next.js (Web)" "NONE" ""

# 2. Orchestrator (:8107) - daantshaant-orchestrator.service
check_service_port "$ORCHESTRATOR_PORT" "Orchestrator" "daantshaant-orchestrator.service" "daantshaant-orchestrator"

# 3. Teeth Analyzer (:8108) - daantshaant-teeth-analyzer.service
check_service_port "$TEETH_ANALYZER_PORT" "Teeth Analyzer" "daantshaant-teeth-analyzer.service" "daantshaant-teeth-analyzer"

# 4. Diagnosis (:8109) - daantshaant-diagnosis.service
check_service_port "$DIAGNOSIS_PORT" "Diagnosis" "daantshaant-diagnosis.service" "daantshaant-diagnosis"

if [ "$OCCUPIED_CONFLICT" -ne 0 ]; then
  echo ""
  echo "[ERROR] Port collision detected. Deployment aborted to prevent disturbing existing VPS services."
  echo "[ERROR] Please resolve the port conflict or update the candidate ports in configuration."
  exit 1
fi

echo "[PORTS] Port safety verification passed. All ports are clear or owned by DaantShaant."
