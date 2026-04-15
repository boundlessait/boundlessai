#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# x402 Guard — interactive demo script
# Usage: ./demo.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
RESET='\033[0m'

BACKEND_PORT=4402
BACKEND_URL="http://localhost:${BACKEND_PORT}"
BACKEND_PID=""

# ── Cleanup on exit ───────────────────────────────────────────────────────────
cleanup() {
  echo ""
  echo -e "${YELLOW}Cleaning up...${RESET}"
  if [[ -n "${BACKEND_PID}" ]]; then
    kill "${BACKEND_PID}" 2>/dev/null || true
    echo -e "${GREEN}Backend stopped (pid ${BACKEND_PID}).${RESET}"
  fi
}
trap cleanup EXIT INT TERM

# ── Helpers ───────────────────────────────────────────────────────────────────
print_banner() {
  echo -e "${CYAN}"
  echo "  ╔═══════════════════════════════════════════════════╗"
  echo "  ║       x402 Guard — Live Demo                      ║"
  echo "  ║   AI Agent Spending Policy & Security Co-Pilot    ║"
  echo "  ╚═══════════════════════════════════════════════════╝"
  echo -e "${RESET}"
}

step() {
  echo ""
  echo -e "${BOLD}${CYAN}▶  $1${RESET}"
}

ok() {
  echo -e "  ${GREEN}✓  $1${RESET}"
}

fail() {
  echo -e "  ${RED}✗  $1${RESET}"
  exit 1
}

wait_for_health() {
  local url="${1}/health"
  local max_attempts=30
  local attempt=0
  echo -n "  Waiting for backend"
  while ! curl -sf "${url}" >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [[ ${attempt} -ge ${max_attempts} ]]; then
      echo ""
      fail "Backend did not start within ${max_attempts}s"
    fi
    echo -n "."
    sleep 1
  done
  echo ""
  ok "Backend is healthy at ${url}"
}

# ── 1. Pre-flight checks ──────────────────────────────────────────────────────
print_banner
step "Checking prerequisites"

command -v python3 >/dev/null 2>&1 || fail "python3 is required but not found"
ok "python3 found: $(python3 --version)"

command -v node >/dev/null 2>&1 || fail "node is required but not found"
ok "node found: $(node --version)"

command -v curl >/dev/null 2>&1 || fail "curl is required but not found"
ok "curl found"

# ── 2. Install dependencies ───────────────────────────────────────────────────
step "Installing backend dependencies (silent)"
pip install -q -r backend/requirements.txt
ok "Backend deps installed"

# ── 3. Start backend ─────────────────────────────────────────────────────────
step "Starting backend on port ${BACKEND_PORT}"
(
  cd backend
  PORT=${BACKEND_PORT} DEV=false python3 main.py
) &
BACKEND_PID=$!
ok "Backend started (pid ${BACKEND_PID})"

wait_for_health "${BACKEND_URL}"

# ── 4. Create a balanced demo policy ─────────────────────────────────────────
step "Creating demo policy via REST API"

POLICY_RESPONSE=$(curl -sf -X POST "${BACKEND_URL}/policies/" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id":            "demo-agent-001",
    "daily_limit":         5.0,
    "hourly_limit":        1.0,
    "per_tx_limit":        0.25,
    "alert_threshold_pct": 0.8,
    "cooldown_seconds":    5,
    "allowed_domains":     [],
    "blocked_domains":     ["drain.example.com", "phishing.io"],
    "active":              true
  }' 2>&1)

echo "  Response: ${POLICY_RESPONSE}" | head -c 200
echo ""
ok "Policy created for agent demo-agent-001"

# ── 5. Run demo agent ─────────────────────────────────────────────────────────
step "Running demo agent simulation (offline mode)"
echo ""
python3 tests/demo_agent.py --offline
echo ""

# ── 6. Show summary ───────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${BOLD}${GREEN}  Demo Complete!${RESET}"
echo ""
echo -e "  ${CYAN}Backend API  :${RESET}  ${BACKEND_URL}"
echo -e "  ${CYAN}Swagger Docs :${RESET}  ${BACKEND_URL}/docs"
echo -e "  ${CYAN}Health       :${RESET}  ${BACKEND_URL}/health"
echo ""
echo -e "  Start the full stack: ${YELLOW}make dev${RESET}"
echo -e "  Run tests           : ${YELLOW}make test${RESET}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""
