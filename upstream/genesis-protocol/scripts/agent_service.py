#!/usr/bin/env python3
"""Genesis Protocol - Persistent Agent Service

Continuously runs the 5-layer AI cognitive engine with:
- Configurable cycle intervals (default: 60s perception, 300s analysis)
- Health check HTTP endpoint on port 8402
- State persistence to ~/.genesis/agent_state.json
- Graceful shutdown with state save
- Structured logging to console and file

Usage:
    python3 scripts/agent_service.py                    # Run with defaults
    python3 scripts/agent_service.py --interval 30      # 30s perception cycle
    python3 scripts/agent_service.py --port 8402        # Custom health port
    python3 scripts/agent_service.py --daemon            # Background mode
"""

import argparse
import json
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from skills.genesis.scripts import config
from skills.genesis.scripts.genesis_engine import GenesisEngine

# --- Configuration -----------------------------------------------------------

STATE_DIR = Path.home() / ".genesis"
STATE_FILE = STATE_DIR / "agent_state.json"
LOG_FILE = STATE_DIR / "agent.log"
PID_FILE = STATE_DIR / "agent.pid"

DEFAULT_PERCEPTION_INTERVAL = 60   # seconds
DEFAULT_HEALTH_PORT = 8402

# --- Logging Setup -----------------------------------------------------------

def setup_logging(log_level: str = "INFO"):
    """Configure logging to both console and file."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    # File handler (rotating-like: truncate if > 10MB)
    if LOG_FILE.exists() and LOG_FILE.stat().st_size > 10 * 1024 * 1024:
        LOG_FILE.write_text("")  # Simple rotation
    fh = logging.FileHandler(str(LOG_FILE), mode="a")
    fh.setFormatter(fmt)
    root.addHandler(fh)

    return logging.getLogger("genesis.service")


# --- State Persistence -------------------------------------------------------

def save_state(engine: GenesisEngine, extra: dict = None):
    """Persist engine state to disk for restart recovery."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state = {
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "cycle_count": engine._cycle_count,
        "preferences": engine._preferences,
        "prediction_accuracy": engine._prediction_accuracy,
        "predictions_count": len(engine._predictions),
        "last_perception": engine._last_perception,
        "last_analysis": engine._last_analysis,
        "last_evolution": engine._last_evolution,
    }
    # Include ML model state if available
    if hasattr(engine, '_ml_model'):
        ml = engine._ml_model
        state["ml_state"] = {
            "ema_fast": ml._ema_fast,
            "ema_slow": ml._ema_slow,
            "momentum_score": ml._momentum_score,
            "bayesian_prior": ml._bayesian_prior,
            "price_history_len": len(ml._price_history),
            "action_outcomes_len": len(ml._action_outcomes),
        }
    if extra:
        state.update(extra)
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))


def load_state() -> dict:
    """Load previous state from disk."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def restore_engine_state(engine: GenesisEngine, state: dict):
    """Restore engine preferences and counters from saved state."""
    if "preferences" in state:
        engine._preferences.update(state["preferences"])
    if "prediction_accuracy" in state:
        engine._prediction_accuracy = state["prediction_accuracy"]
    if "cycle_count" in state:
        engine._cycle_count = state["cycle_count"]


# --- Health Check HTTP Server ------------------------------------------------

class HealthHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler for health checks and status queries."""

    engine = None  # Set by AgentService
    service = None

    def do_GET(self):
        if self.path == "/health":
            self._respond(200, {"status": "healthy", "uptime_sec": self.service.uptime()})
        elif self.path == "/status":
            status = self.engine.get_status() if self.engine else {}
            status["service"] = {
                "uptime_sec": round(self.service.uptime(), 1),
                "total_cycles": self.service.total_cycles,
                "last_cycle_at": self.service.last_cycle_time,
                "errors": self.service.error_count,
            }
            self._respond(200, status)
        elif self.path == "/metrics":
            metrics = {
                "cycles_total": self.service.total_cycles,
                "errors_total": self.service.error_count,
                "uptime_seconds": round(self.service.uptime(), 1),
                "prediction_accuracy": self.engine._prediction_accuracy if self.engine else 0,
                "active_preferences": self.engine._preferences if self.engine else {},
            }
            self._respond(200, metrics)
        else:
            self._respond(404, {"error": "not found", "endpoints": ["/health", "/status", "/metrics"]})

    def _respond(self, code: int, body: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(body, indent=2, default=str).encode())

    def log_message(self, format, *args):
        pass  # Suppress default HTTP logging


# --- Agent Service -----------------------------------------------------------

class AgentService:
    """Main service orchestrating the Genesis cognitive engine."""

    def __init__(self, interval: int = DEFAULT_PERCEPTION_INTERVAL,
                 health_port: int = DEFAULT_HEALTH_PORT):
        self.interval = interval
        self.health_port = health_port
        self.engine = GenesisEngine()
        self.logger = logging.getLogger("genesis.service")
        self._running = False
        self._start_time = 0.0
        self.total_cycles = 0
        self.error_count = 0
        self.last_cycle_time = None
        self._http_server = None
        self._http_thread = None

    def uptime(self) -> float:
        return time.time() - self._start_time if self._start_time else 0

    def _start_health_server(self):
        """Start the health check HTTP server in a background thread."""
        HealthHandler.engine = self.engine
        HealthHandler.service = self
        try:
            self._http_server = HTTPServer(("0.0.0.0", self.health_port), HealthHandler)
            self._http_thread = threading.Thread(target=self._http_server.serve_forever, daemon=True)
            self._http_thread.start()
            self.logger.info("Health endpoint: http://0.0.0.0:%d/health", self.health_port)
        except OSError as e:
            self.logger.warning("Could not start health server on port %d: %s", self.health_port, e)

    def _stop_health_server(self):
        if self._http_server:
            self._http_server.shutdown()

    def _write_pid(self):
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(os.getpid()))

    def _remove_pid(self):
        if PID_FILE.exists():
            PID_FILE.unlink(missing_ok=True)

    def start(self):
        """Main entry point - runs the cognitive loop."""
        self._running = True
        self._start_time = time.time()
        self._write_pid()

        # Restore previous state
        prev_state = load_state()
        if prev_state:
            restore_engine_state(self.engine, prev_state)
            self.logger.info(
                "Restored state: %d previous cycles, accuracy=%.2f%%",
                prev_state.get("cycle_count", 0),
                prev_state.get("prediction_accuracy", 0.5) * 100
            )

        # Register signal handlers
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        # Start health server
        self._start_health_server()

        self.logger.info("=" * 60)
        self.logger.info("  Genesis Protocol - Agent Service Started")
        self.logger.info("  Perception interval: %ds", self.interval)
        self.logger.info("  Mode: %s | Paused: %s | DryRun: %s",
                        config.MODE, config.PAUSED, config.DRY_RUN)
        self.logger.info("  PID: %d", os.getpid())
        self.logger.info("=" * 60)

        try:
            while self._running:
                cycle_start = time.time()
                try:
                    result = self.engine.run_cycle()
                    self.total_cycles += 1
                    self.last_cycle_time = datetime.now(timezone.utc).isoformat()

                    self.logger.info(
                        "Cycle #%d: %d actions planned, %d executed, accuracy=%.1f%% (%.2fs)",
                        result["cycle"],
                        result["actions_planned"],
                        result["actions_executed"],
                        (result.get("prediction_accuracy", 0.5) or 0.5) * 100,
                        result["elapsed_sec"]
                    )

                    # Save state every cycle
                    save_state(self.engine, {
                        "last_cycle_result": result,
                        "service_uptime": round(self.uptime(), 1),
                    })

                except Exception as exc:
                    self.error_count += 1
                    self.logger.error("Cycle error (#%d): %s", self.error_count, exc)
                    if self.error_count > 50:
                        self.logger.critical("Too many errors (>50), shutting down")
                        break

                # Sleep for remainder of interval
                elapsed = time.time() - cycle_start
                sleep_time = max(1, self.interval - elapsed)

                # Interruptible sleep
                end_time = time.time() + sleep_time
                while self._running and time.time() < end_time:
                    time.sleep(min(1, end_time - time.time()))

        finally:
            self._shutdown()

    def _handle_signal(self, signum, frame):
        """Handle SIGTERM/SIGINT gracefully."""
        sig_name = signal.Signals(signum).name
        self.logger.info("Received %s, initiating graceful shutdown...", sig_name)
        self._running = False

    def _shutdown(self):
        """Clean shutdown: save state, stop server, remove PID."""
        self.logger.info("Shutting down...")
        save_state(self.engine, {
            "shutdown_at": datetime.now(timezone.utc).isoformat(),
            "total_cycles_this_session": self.total_cycles,
            "total_errors": self.error_count,
        })
        self._stop_health_server()
        self._remove_pid()
        self.logger.info("Agent service stopped. Total cycles: %d, Errors: %d",
                        self.total_cycles, self.error_count)


# --- CLI ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Genesis Protocol - Persistent Agent Service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/agent_service.py                  # Default: 60s cycles
  python3 scripts/agent_service.py --interval 30    # Faster cycles
  python3 scripts/agent_service.py --log-level DEBUG # Verbose logging

Health check:
  curl http://localhost:8402/health
  curl http://localhost:8402/status
  curl http://localhost:8402/metrics
        """
    )
    parser.add_argument("--interval", type=int, default=DEFAULT_PERCEPTION_INTERVAL,
                       help=f"Perception cycle interval in seconds (default: {DEFAULT_PERCEPTION_INTERVAL})")
    parser.add_argument("--port", type=int, default=DEFAULT_HEALTH_PORT,
                       help=f"Health check HTTP port (default: {DEFAULT_HEALTH_PORT})")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                       help="Logging level (default: INFO)")

    args = parser.parse_args()

    logger = setup_logging(args.log_level)

    service = AgentService(interval=args.interval, health_port=args.port)
    service.start()


if __name__ == "__main__":
    main()
