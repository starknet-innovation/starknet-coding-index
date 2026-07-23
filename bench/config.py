"""Shared configuration for the benchmark harness."""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TASKS_DIR = REPO_ROOT / "tasks"
RESULTS_DIR = REPO_ROOT / "results"
RUNS_DIR = RESULTS_DIR / "runs"
WORKSPACES_DIR = RESULTS_DIR / "workspaces"

SCARB_VERSION = "2.19.4"
SNFORGE_VERSION = "0.62.1"

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# The sandbox proxy injects the real OpenRouter credentials at the network
# level; the placeholder only satisfies the SDK's non-empty check.
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY") or "proxy-injected"

# The self-hosted deployment (vendor/cairo-coder) is the only backend now:
# the hosted api.cairo-coder.com key is quota-dead and the service sunsets
# 2026-07-31. Env override kept for exceptional cases only.
CAIRO_CODER_URL = os.environ.get(
    "CAIRO_CODER_URL", "http://localhost:3001/v1/chat/completions"
)
CAIRO_CODER_API_KEY = os.environ.get("CAIRO_CODER_API_KEY", "")

MAX_ASSISTANT_TURNS = 10
# A run must deliver within this much MODEL time (LLM streaming + doc-tool
# wait) or it counts as a failure. Model time, not wall time: wall depends on
# how many tasks the harness runs concurrently. The agent stops starting new
# turns past the budget; scoring applies the same cap retroactively.
MODEL_TIME_BUDGET_S = 900
LLM_CALL_TIMEOUT_S = 600
CAIRO_CODER_TIMEOUT_S = 300
BUILD_TIMEOUT_S = 300
TEST_TIMEOUT_S = 300
TOOL_RESULT_MAX_CHARS = 8000
