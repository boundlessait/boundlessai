.PHONY: install dev test demo build clean help

# ── Colours ───────────────────────────────────────────────────────────────────
CYAN  := \033[0;36m
GREEN := \033[0;32m
RESET := \033[0m

# ── Defaults ──────────────────────────────────────────────────────────────────

help: ## Show this help message
	@echo ""
	@echo "  x402 Guard — Makefile targets"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-12s$(RESET) %s\n", $$1, $$2}'
	@echo ""

# ── Install ───────────────────────────────────────────────────────────────────

install: ## Install backend (pip) and frontend (npm) dependencies
	@echo "$(GREEN)Installing backend dependencies...$(RESET)"
	cd backend && pip install -q -r requirements.txt
	@echo "$(GREEN)Installing frontend dependencies...$(RESET)"
	cd frontend && npm install --silent
	@echo "$(GREEN)All dependencies installed.$(RESET)"

# ── Development ───────────────────────────────────────────────────────────────

dev: ## Start backend (port 4402) and frontend (port 3000) concurrently
	@echo "$(GREEN)Starting x402 Guard (backend :4402  frontend :3000)...$(RESET)"
	@command -v concurrently >/dev/null 2>&1 || npm install -g concurrently --silent
	concurrently \
		--names "backend,frontend" \
		--prefix-colors "cyan,magenta" \
		"cd backend && PORT=4402 python3 main.py" \
		"cd frontend && npm run dev -- --port 3000"

# ── Testing ───────────────────────────────────────────────────────────────────

test: ## Run Python unit tests
	@echo "$(GREEN)Running backend unit tests...$(RESET)"
	cd backend && python3 -m unittest discover -s ../tests -p 'test_*.py' -v

# ── Demo ──────────────────────────────────────────────────────────────────────

demo: ## Run the offline demo agent simulation
	@echo "$(GREEN)Running demo agent (offline mode)...$(RESET)"
	python3 tests/demo_agent.py --offline

# ── Build ─────────────────────────────────────────────────────────────────────

build: ## Build the Next.js frontend for production
	@echo "$(GREEN)Building frontend...$(RESET)"
	cd frontend && npm run build

# ── Clean ─────────────────────────────────────────────────────────────────────

clean: ## Remove build artefacts: __pycache__, .next, data/*.json
	@echo "$(GREEN)Cleaning build artefacts...$(RESET)"
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete 2>/dev/null || true
	rm -rf frontend/.next
	rm -f backend/data/*.json
	@echo "$(GREEN)Clean complete.$(RESET)"
