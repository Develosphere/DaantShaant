#!/usr/bin/env bash
# ==============================================================================
# DaantShaant Production Port Safety Checker
#
# Inspects candidate ports:
#   Next.js:          3107
#   Orchestrator:     8107
#   Teeth Analyzer:   8108
#   Diagnosis:        8109
#
# Fails clearly if any port is occupied by an external, non-DaantShaant process.
# Never kills or disturbs other processes on the VPS.
# ==============================================================================

set -euo pipefail

FRONTEND_PORT="${FRONTEND_PORT:-3107}"
ORCHESTRATOR_PORT="${ORCHESTRATOR_PORT:-8107}"
TEETH_ANALYZER_PORT="${TEETH_ANALYZER_PORT:-8108}"
DIAGNOSIS_PORT="${DIAGNOSIS_PORT:-8109}"

PORTS=("$FRONTEND_PORT" "$ORCHESTRATOR_PORT" "$TEETH_ANALYZER_PORT" "$DIAGNOSIS_PORT")
SERVICE_NAMES=("Next.js (Web)" "Orchestrator" "Teeth Analyzer" "Diagnosis")

echo "[PORTS] Running DaantShaant production port safety check..."

# Discover existing DaantShaant PM2 PIDs if PM2 is running
DAANTSHAANT_PIDS=()
if command -v pm2 >/dev/null 2>&1; then
  for proc_name in daantshaant-web daantshaant-orchestrator daantshaant-teeth-analyzer daantshaant-diagnosis; do
    pid=$(pm2 pid "$proc_name" 2>/dev/null || true)
    if [ -n "$pid" ] && [ "$pid" != "0" ] && [ "$pid" != "N/A" ]; then
      DAANTSHAANT_PIDS+=("$pid")
    fi
  done
fi

is_daantshaant_pid() {
  local check_pid="$1"
  for d_pid in "${DAANTSHAANT_PIDS[@]:-}"; do
    if [ "$d_pid" = "$check_pid" ]; then
      return 0
    fi
  done
  return 1
}

OCCUPIED_CONFLICT=0

for i in "${!PORTS[@]}"; do
  port="${PORTS[$i]}"
  svc_name="${SERVICE_NAMES[$i]}"

  # Check if port is in use via ss
  listener_info=$(ss -tlnp "sport = :$port" 2>/dev/null | grep -E ":$port\b" || true)

  if [ -z "$listener_info" ]; then
    echo "[PORTS] Port $port ($svc_name): AVAILABLE"
    continue
  fi

  # Port is in use — extract PID if visible
  # Format in ss output typically contains: users:(("process",pid=12345,fd=...))
  pid=$(echo "$listener_info" | grep -o 'pid=[0-9]*' | head -n 1 | cut -d'=' -f2 || true)

  if [ -n "$pid" ] && is_daantshaant_pid "$pid"; then
    echo "[PORTS] Port $port ($svc_name): Currently held by DaantShaant PM2 process (PID $pid) — safe to reload."
  elif [ -n "$pid" ]; then
    proc_cmd=$(ps -p "$pid" -o args= 2>/dev/null || echo "unknown")
    echo "[ERROR] Port $port ($svc_name) is OCCUPIED by external process (PID: $pid, Command: $proc_cmd)!"
    OCCUPIED_CONFLICT=1
  else
    # PID could not be inspected (permission or different user) but port is listening
    if [ ${#DAANTSHAANT_PIDS[@]} -gt 0 ]; then
      echo "[PORTS] Port $port ($svc_name): Listening (assuming managed by existing DaantShaant stack)."
    else
      echo "[ERROR] Port $port ($svc_name) is OCCUPIED by an unknown/non-DaantShaant process!"
      echo "        Details: $listener_info"
      OCCUPIED_CONFLICT=1
    fi
  fi
done

if [ "$OCCUPIED_CONFLICT" -ne 0 ]; then
  echo ""
  echo "[ERROR] Port collision detected. Deployment aborted to prevent disturbing existing VPS services."
  echo "[ERROR] Please resolve the port conflict or update the candidate ports in configuration."
  exit 1
fi

echo "[PORTS] Port safety verification passed. All ports are clear or owned by DaantShaant."
