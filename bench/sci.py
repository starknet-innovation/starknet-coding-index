"""Starknet Coding Index (SCI): one composite score per model.

  uv run python -m bench.sci [runs.jsonl ...]

SCI v1 = 0.50*Correctness + 0.15*OneShot + 0.15*Speed + 0.15*Cost
         + 0.05*TokenEfficiency        (0-100, higher is better)

- Correctness: mean over tasks of mean over reps of hidden-test pass fraction.
- OneShot: % of runs solved on the first submission.
- Speed/Cost/Tokens: medians mapped to 0-100 on FIXED log anchors, so adding
  a model later never reshuffles existing scores.
- Baseline condition, max-thinking config per model, 10-turn budget.

Adding a model to the leaderboard = benchmark it with the standard runner,
then add one MODEL_REGISTRY entry; the report picks it up on regeneration.
"""

import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from . import config
from .report import load_runs

SCI_SPEC = {
    "version": "v1",
    "condition": "baseline",
    "turn_budget": 10,
    "weights": {"correct": 0.50, "oneshot": 0.15, "speed": 0.15, "cost": 0.15, "tokens": 0.05},
    # (best, worst): score 100 at <= best, 0 at >= worst, log-interpolated
    "anchors": {"speed": (20, 1200), "cost": (0.003, 0.60), "tokens": (1000, 40000)},
}

# spec -> display metadata. The extension point for future models.
MODEL_REGISTRY = [
    {"spec": "moonshotai/kimi-k3", "label": "Kimi K3", "lab": "Moonshot", "open_weight": True},
    {"spec": "xiaomi/mimo-v2.5-pro@xhigh", "label": "MiMo-V2.5-Pro", "lab": "Xiaomi", "open_weight": True},
    {"spec": "deepseek/deepseek-v4-pro@xhigh", "label": "DeepSeek V4-Pro", "lab": "DeepSeek", "open_weight": True},
    {"spec": "tencent/hy3", "label": "Hy3", "lab": "Tencent", "open_weight": True},
    {"spec": "z-ai/glm-5.2@xhigh", "label": "GLM 5.2", "lab": "Z.ai", "open_weight": True},
    {"spec": "minimax/minimax-m3@xhigh", "label": "MiniMax M3", "lab": "MiniMax", "open_weight": True},
    {"spec": "qwen/qwen3.6-27b@xhigh", "label": "Qwen3.6-27B", "lab": "Alibaba", "open_weight": True},
]


def log_anchor(value, best, worst):
    """100 at <= best, 0 at >= worst, log-interpolated between."""
    if value is None:
        return 0.0
    value = max(best, min(worst, value))
    return 100 * (math.log(worst) - math.log(value)) / (math.log(worst) - math.log(best))


def compute_sci(runs_for_model):
    """Composite SCI for one model's baseline runs. Returns dict with
    sci, per-component scores (0-100), and the raw medians behind them."""
    w, anchors = SCI_SPEC["weights"], SCI_SPEC["anchors"]
    per_task = defaultdict(list)
    for r in runs_for_model:
        total = r["tests_passed"] + r["tests_failed"]
        per_task[r["task"]].append(r["tests_passed"] / total if total else 0.0)
    correct = 100 * statistics.mean(statistics.mean(v) for v in per_task.values())
    oneshot = 100 * statistics.mean(
        1 if (r["solved"] and r["turns"] == 1) else 0 for r in runs_for_model
    )

    def med(key):
        vals = [r[key] for r in runs_for_model if r.get(key) is not None]
        return statistics.median(vals) if vals else None

    raw = {"med_wall": med("wall_time_s"), "med_cost": med("cost_usd"),
           "med_ctok": med("completion_tokens"), "n_runs": len(runs_for_model)}
    components = {
        "correct": correct,
        "oneshot": oneshot,
        "speed": log_anchor(raw["med_wall"], *anchors["speed"]),
        "cost": log_anchor(raw["med_cost"], *anchors["cost"]),
        "tokens": log_anchor(raw["med_ctok"], *anchors["tokens"]),
    }
    sci = sum(w[k] * components[k] for k in w)
    return {"sci": sci, "components": components, "raw": raw}


def leaderboard(all_runs, condition=None):
    """SCI rows for every registry model present in the data, best first."""
    condition = condition or SCI_SPEC["condition"]
    by_model = defaultdict(list)
    for r in all_runs:
        if r["condition"] == condition:
            by_model[r["model"]].append(r)
    rows = []
    for entry in MODEL_REGISTRY:
        runs = by_model.get(entry["spec"])
        if not runs:
            continue
        rows.append({**entry, **compute_sci(runs)})
    return sorted(rows, key=lambda r: -r["sci"])


def main():
    paths = [Path(p) for p in sys.argv[1:]] or [config.RUNS_DIR / "main.jsonl"]
    rows = leaderboard(load_runs(paths))
    w = SCI_SPEC["weights"]
    print(f"Starknet Coding Index {SCI_SPEC['version']} — baseline, weights "
          + " ".join(f"{k}={v}" for k, v in w.items()))
    print(f"{'#':>2} {'Model':16} {'SCI':>6} | {'corr':>5} {'1shot':>5} {'speed':>5} {'cost':>5} {'tok':>5} | {'open':>6} {'n':>3}")
    for i, r in enumerate(rows, 1):
        c = r["components"]
        print(f"{i:>2} {r['label']:16} {r['sci']:6.1f} | {c['correct']:5.1f} {c['oneshot']:5.0f} "
              f"{c['speed']:5.0f} {c['cost']:5.0f} {c['tokens']:5.0f} | "
              f"{'open' if r['open_weight'] else 'closed':>6} {r['raw']['n_runs']:>3}")


if __name__ == "__main__":
    main()
