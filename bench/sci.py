"""Starknet Coding Index (SCI): one composite score per model.

  uv run python -m bench.sci [runs.jsonl ...]

SCI v3 = 0.50*Effectiveness + 0.25*Correctness + 0.15*Cost + 0.10*Time
         (0-100, higher is better)

- Effectiveness: how often the model delivers working code WITHOUT sending the
  human back into the loop. Per run: 0 if unsolved or over budget, else
  100 * 0.4**(submissions-1), so 1/2/3/4 submissions score 100/40/16/6.
  An ATTEMPT IS A SUBMISSION, NOT A TURN: thinking, extra assistant turns and
  documentation lookups are invisible to the user and therefore free. Only
  delivering code that turns out to be broken costs, because in real use that
  is the moment a person has to read the output and re-prompt.
- Correctness: mean over tasks of mean over reps of hidden-test pass fraction.
  Partial credit on what was delivered: 90% of tests passing is still broken,
  but it is closer than nothing, and it separates the floor of the field.
- Cost/Time: median $ per task and median MODEL latency (llm_time_s), mapped
  to 0-100 on FIXED log anchors so adding a model never reshuffles old scores.
  Deliberately not wall time — wall includes local scarb/snforge compile+test,
  which scales with runner concurrency and says nothing about the model.
- Baseline condition; per-run budget: 10 turns AND 15 min of model time.

v1 -> v2 (2026-07-23): speed input wall_time_s -> llm_time_s; speed best
anchor 20s -> 10s (two models clamped at the old ceiling). One-time break
in score continuity; rankings unchanged.
v2 -> v2.1 (2026-07-23): 15-min model-time budget joins the 10-turn budget
in the run definition — a run over budget earns no correctness/solve credit
(load_runs flips solved; compute_sci zeroes the test fraction). The runner
also enforces it live (agent.py stops starting turns past the budget).
v2.1 -> v3 (2026-07-25): the index stopped measuring convergence under an
oracle. v2.1 gave correctness 50% and a binary one-shot bonus 15%, so a model
that ground out a fix across ten turns of privileged failing-test feedback
scored nearly as well as one that got it right immediately — feedback a real
user never has. v3 makes graded first-submission delivery the largest term,
keeps correctness at 25% as partial credit on the delivered code, and drops
the token-efficiency component (cost already prices verbosity). Scores are NOT
comparable across the v2.1 boundary.

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
    "version": "v3",
    "condition": "baseline",
    "turn_budget": 10,
    "model_time_budget_s": config.MODEL_TIME_BUDGET_S,  # over budget = failed
    "weights": {"effective": 0.50, "correct": 0.25, "cost": 0.15, "speed": 0.10},
    # per-submission decay: 1 submission = 100, then x0.4 each further attempt
    "attempt_decay": 0.4,
    # (best, worst): score 100 at <= best, 0 at >= worst, log-interpolated
    # speed anchors apply to llm_time_s (model latency), not wall time
    "anchors": {"speed": (10, 1200), "cost": (0.003, 0.60)},
}

# Candidate variants per model; the leaderboard scores every candidate with
# data and keeps the best (policy: "best foot forward", variant labeled on
# the chart). The extension point for future models.
MODEL_REGISTRY = [
    # weights_pending: Moonshot announced a weights release for 2026-07-27 but
    # has not published them as of 2026-07-25 — the report stars K3's open
    # classification until they ship; drop this flag when they do
    {"specs": ["moonshotai/kimi-k3"], "label": "Kimi K3", "lab": "Moonshot",
     "open_weight": True, "weights_pending": True},
    {"specs": ["xiaomi/mimo-v2.5-pro@max", "xiaomi/mimo-v2.5-pro@xhigh",
               "xiaomi/mimo-v2.5-pro@high", "xiaomi/mimo-v2.5-pro@medium",
               "xiaomi/mimo-v2.5-pro@low", "xiaomi/mimo-v2.5-pro@minimal",
               "xiaomi/mimo-v2.5-pro@disabled"],
     "label": "MiMo-V2.5-Pro", "lab": "Xiaomi", "open_weight": True},
    {"specs": ["deepseek/deepseek-v4-pro@xhigh", "deepseek/deepseek-v4-pro@high",
               "deepseek/deepseek-v4-pro@medium", "deepseek/deepseek-v4-pro@low",
               "deepseek/deepseek-v4-pro@minimal", "deepseek/deepseek-v4-pro@disabled"],
     "label": "DeepSeek V4-Pro", "lab": "DeepSeek", "open_weight": True},
    {"specs": ["tencent/hy3", "tencent/hy3@max", "tencent/hy3@xhigh", "tencent/hy3@high",
               "tencent/hy3@medium", "tencent/hy3@low", "tencent/hy3@minimal",
               "tencent/hy3@disabled"],
     "label": "Hy3", "lab": "Tencent", "open_weight": True},
    {"specs": ["z-ai/glm-5.2@max", "z-ai/glm-5.2@xhigh", "z-ai/glm-5.2@high",
               "z-ai/glm-5.2@medium", "z-ai/glm-5.2@low", "z-ai/glm-5.2@minimal",
               "z-ai/glm-5.2@disabled"],
     "label": "GLM 5.2", "lab": "Z.ai", "open_weight": True},
    {"specs": ["minimax/minimax-m3@max", "minimax/minimax-m3@xhigh", "minimax/minimax-m3@high",
               "minimax/minimax-m3@medium", "minimax/minimax-m3@low",
               "minimax/minimax-m3@minimal"],
     # @disabled deliberately absent: MiniMax accepts the param but thinks anyway
     "label": "MiniMax M3", "lab": "MiniMax", "open_weight": True},
    {"specs": ["qwen/qwen3.6-27b@max", "qwen/qwen3.6-27b@xhigh", "qwen/qwen3.6-27b@high"],
     # small: rendered in the report's small-models section, not the main charts
     "label": "Qwen3.6-27B", "lab": "Alibaba", "open_weight": True, "small": True},
    # Small open-weight batch 2026-07-24. gpt-oss: @disabled REJECTED
    # ("Reasoning is mandatory"), effort ladder low/medium/high; 0% correct at
    # every tier. coder-next: no reasoning params at all, bare only; 0% correct.
    # 35b-a3b: dial accepted (effort levels likely coerced; bare behaves
    # differently); gemma: dial accepted. All winning edges at surface floors.
    {"specs": ["openai/gpt-oss-120b@low", "openai/gpt-oss-120b@medium",
               "openai/gpt-oss-120b@high"],
     "label": "gpt-oss-120b", "lab": "OpenAI", "open_weight": True, "small": True},
    {"specs": ["qwen/qwen3.6-35b-a3b", "qwen/qwen3.6-35b-a3b@disabled",
               "qwen/qwen3.6-35b-a3b@low", "qwen/qwen3.6-35b-a3b@high"],
     "label": "Qwen3.6-35B-A3B", "lab": "Alibaba", "open_weight": True, "small": True},
    {"specs": ["google/gemma-4-31b-it@disabled", "google/gemma-4-31b-it@low",
               "google/gemma-4-31b-it@high"],
     "label": "Gemma 4 31B", "lab": "Google", "open_weight": True, "small": True},
    {"specs": ["qwen/qwen3-coder-next"],
     "label": "Qwen3 Coder Next", "lab": "Alibaba", "open_weight": True, "small": True},
    # Probe 2026-07-24: full surface honored incl. @disabled; real curve with
    # overshoot (correct 79 off -> 99 low -> 88 high); low = interior winner.
    {"specs": ["thinkingmachines/inkling@disabled", "thinkingmachines/inkling@low",
               "thinkingmachines/inkling@high"],
     "label": "Inkling", "lab": "Thinking Machines", "open_weight": True},
    # Probe 2026-07-24: adaptive-Anthropic signature (all variants identical on
    # the probe, @disabled honored). Bracket: 78/78 solved, 0 tiebreaks; low =
    # interior winner (91.5, 100% one-shot, speed 96). -fast serving tier
    # skipped per the Opus 4.8 precedent and pro-modes-dominated finding.
    {"specs": ["anthropic/claude-opus-5@disabled", "anthropic/claude-opus-5@low",
               "anthropic/claude-opus-5@high"],
     "label": "Opus 5", "lab": "Anthropic", "open_weight": False},
    # Probe 2026-07-24: full reasoning surface accepted incl. @disabled; output
    # and latency scale with the dial. Max: flat correctness, off wins on SCI
    # (edge = floor, ladder closed). Plus: real curve, high interior winner
    # (xhigh collapsed 92 -> 77 correctness).
    {"specs": ["qwen/qwen3.7-max@disabled", "qwen/qwen3.7-max@low", "qwen/qwen3.7-max@high"],
     # charted False: closed Qwen; the interesting Qwen models are the open ones (David)
     "label": "Qwen3.7 Max", "lab": "Alibaba", "open_weight": False, "deprecated": True},
    {"specs": ["qwen/qwen3.7-plus@disabled", "qwen/qwen3.7-plus@low", "qwen/qwen3.7-plus@high",
               "qwen/qwen3.7-plus@xhigh"],
     # charted False: one Qwen 3.7 bar is enough (David); Plus stays in the
     # roster table and prose but not in charts 1-2
     "label": "Qwen3.7 Plus", "lab": "Alibaba", "open_weight": False, "deprecated": True},
    {"specs": ["anthropic/claude-sonnet-5@high", "anthropic/claude-sonnet-5@medium",
               "anthropic/claude-sonnet-5@low", "anthropic/claude-sonnet-5@minimal",
               "anthropic/claude-sonnet-5"],
     "label": "Sonnet 5", "lab": "Anthropic", "open_weight": False},
    {"specs": ["google/gemini-3.6-flash@max", "google/gemini-3.6-flash@xhigh",
               "google/gemini-3.6-flash@high", "google/gemini-3.6-flash@medium",
               "google/gemini-3.6-flash@low", "google/gemini-3.6-flash@minimal"],
     "label": "Gemini 3.6 Flash", "lab": "Google", "open_weight": False},
    {"specs": ["openai/gpt-5.6-luna-pro", "openai/gpt-5.6-luna@max",
               "openai/gpt-5.6-luna@xhigh", "openai/gpt-5.6-luna@high",
               "openai/gpt-5.6-luna@medium", "openai/gpt-5.6-luna@low",
               "openai/gpt-5.6-luna@minimal", "openai/gpt-5.6-luna@disabled"],
     # charted False: budget tier, not a coding pick (David); data stays in the table
     "label": "GPT-5.6 Luna", "lab": "OpenAI", "open_weight": False, "deprecated": True},
    {"specs": ["x-ai/grok-4.5@max", "x-ai/grok-4.5@xhigh", "x-ai/grok-4.5@high",
               "x-ai/grok-4.5@low", "x-ai/grok-4.5@minimal"],
     # thinking mandatory (@disabled rejected); bare = dynamic, skipped
     "label": "Grok 4.5", "lab": "xAI", "open_weight": False},
    {"specs": ["anthropic/claude-fable-5@max", "anthropic/claude-fable-5@xhigh",
               "anthropic/claude-fable-5@high", "anthropic/claude-fable-5@low",
               "anthropic/claude-fable-5@minimal"],
     # thinking mandatory (no off tier); bare = adaptive/unnameable, skipped
     "label": "Fable 5", "lab": "Anthropic", "open_weight": False},
    {"specs": ["anthropic/claude-opus-4.8@max", "anthropic/claude-opus-4.8@xhigh",
               "anthropic/claude-opus-4.8@high", "anthropic/claude-opus-4.8@low",
               "anthropic/claude-opus-4.8@disabled"],
     # bare skipped: adaptive thinking at an unnameable level (probe 2026-07-24)
     # charted False: superseded by Opus 5; charts carry one bar per family's best (David)
     "label": "Opus 4.8", "lab": "Anthropic", "open_weight": False, "deprecated": True},
    {"specs": ["anthropic/claude-haiku-4.5@max", "anthropic/claude-haiku-4.5@xhigh",
               "anthropic/claude-haiku-4.5@high", "anthropic/claude-haiku-4.5@low",
               "anthropic/claude-haiku-4.5"],
     # charted False: budget tier, not a coding pick (David); data stays in the table
     "label": "Haiku 4.5", "lab": "Anthropic", "open_weight": False, "deprecated": True},
    {"specs": ["openai/gpt-5.6-sol@max", "openai/gpt-5.6-sol@xhigh",
               "openai/gpt-5.6-sol@high", "openai/gpt-5.6-sol@low",
               "openai/gpt-5.6-sol@disabled"],
     "label": "GPT-5.6 Sol", "lab": "OpenAI", "open_weight": False},
    {"specs": ["openai/gpt-5.6-terra-pro", "openai/gpt-5.6-terra@max",
               "openai/gpt-5.6-terra@xhigh", "openai/gpt-5.6-terra@high",
               "openai/gpt-5.6-terra@medium", "openai/gpt-5.6-terra@low",
               "openai/gpt-5.6-terra@minimal", "openai/gpt-5.6-terra@disabled"],
     "label": "GPT-5.6 Terra", "lab": "OpenAI", "open_weight": False},
]


# Bare specs (no @effort) map to a model-specific fixed thinking level —
# label that level explicitly; "default" means nothing to a reader.
BARE_VARIANT_LABELS = {
    "moonshotai/kimi-k3": "max",   # always-thinking; Moonshot maps default to max
    "tencent/hy3": "high",         # bare hy3 measured identical to its high tier
    "anthropic/claude-sonnet-5": "off",  # no reasoning param = thinking fully off
    "anthropic/claude-haiku-4.5": "off",  # same: bare = thinking off (probe-confirmed)
    "openai/gpt-5.6-luna-pro": "pro",    # same model as luna, reasoning.mode=pro
    "openai/gpt-5.6-terra-pro": "pro",   # same model as terra, reasoning.mode=pro
    "qwen/qwen3.6-35b-a3b": "dynamic",   # bare = hybrid auto-thinking, distinct from @disabled
    "qwen/qwen3-coder-next": "",         # no reasoning surface at all: no variant parenthetical
}


def variant_label(spec):
    """Human label for the thinking level encoded in a spec."""
    if "@" in spec:
        effort = spec.rsplit("@", 1)[1]
        return "off" if effort == "disabled" else effort
    return BARE_VARIANT_LABELS.get(spec, "unspecified")


def log_anchor(value, best, worst):
    """100 at <= best, 0 at >= worst, log-interpolated between."""
    if value is None:
        return 0.0
    value = max(best, min(worst, value))
    return 100 * (math.log(worst) - math.log(value)) / (math.log(worst) - math.log(best))


def attempts(run):
    """Delivery attempts the user would have lived through.

    Submissions, not turns: a lookup or extra thinking turn never reaches the
    user, while every submission after the first means broken code went out and
    somebody had to read it. Some models emit several submit calls inside one
    turn, which this counts correctly and a turn count would hide.
    """
    return max(1, run.get("n_submissions") or run["turns"])


def attempt_score(run):
    """0-100 for a single run: 100 for a one-submission solve, decaying fast."""
    if run.get("over_time_budget") or not run["solved"]:
        return 0.0
    return 100 * SCI_SPEC["attempt_decay"] ** (attempts(run) - 1)


def compute_sci(runs_for_model):
    """Composite SCI for one model's baseline runs. Returns dict with
    sci, per-component scores (0-100), and the raw medians behind them."""
    w, anchors = SCI_SPEC["weights"], SCI_SPEC["anchors"]
    per_task = defaultdict(list)
    for r in runs_for_model:
        if r.get("over_time_budget"):
            # delivered outside the model-time budget: no correctness credit
            per_task[r["task"]].append(0.0)
            continue
        total = r["tests_passed"] + r["tests_failed"]
        per_task[r["task"]].append(r["tests_passed"] / total if total else 0.0)
    correct = 100 * statistics.mean(statistics.mean(v) for v in per_task.values())
    effective = statistics.mean(attempt_score(r) for r in runs_for_model)

    def med(key):
        vals = [r[key] for r in runs_for_model if r.get(key) is not None]
        return statistics.median(vals) if vals else None

    # Speed = model latency incl. doc-tool wait: for baseline runs assist
    # time is zero, so this only matters when scoring the mcp condition.
    svc_times = [
        r["llm_time_s"] + (r.get("assist_time_s") or 0)
        for r in runs_for_model if r.get("llm_time_s") is not None
    ]
    solved = [r for r in runs_for_model if r["solved"]]
    raw = {"med_llm": statistics.median(svc_times) if svc_times else None,
           "med_cost": med("cost_usd"),
           "med_ctok": med("completion_tokens"),
           "med_attempts": statistics.median([attempts(r) for r in solved]) if solved else None,
           "one_sub_pct": 100 * statistics.mean(
               1 if (r["solved"] and attempts(r) == 1) else 0 for r in runs_for_model),
           "n_runs": len(runs_for_model)}
    components = {
        "effective": effective,
        "correct": correct,
        "cost": log_anchor(raw["med_cost"], *anchors["cost"]),
        "speed": log_anchor(raw["med_llm"], *anchors["speed"]),
    }
    sci = sum(w[k] * components[k] for k in w)
    return {"sci": sci, "components": components, "raw": raw}


def active_models():
    """Registry entries that are still part of the study.

    Deprecated entries are excluded EVERYWHERE, not just from the charts: no
    report rows, no leaderboard, and above all no new benchmark runs. The
    earlier "charted: False" flag only hid them in the report, so top-up sweeps
    kept spending money and hours on models David had already dropped. Anything
    that picks models to run must go through this function.
    """
    return [e for e in MODEL_REGISTRY if not e.get("deprecated")]


def leaderboard(all_runs, condition=None):
    """SCI rows for every active registry model present in the data, best first.

    Each model is scored at every benchmarked candidate variant; the row
    carries the best-scoring one (spec + variant fields say which)."""
    condition = condition or SCI_SPEC["condition"]
    by_model = defaultdict(list)
    for r in all_runs:
        if r["condition"] == condition:
            by_model[r["model"]].append(r)
    rows = []
    for entry in active_models():
        scored = [
            {"spec": spec, **compute_sci(by_model[spec])}
            for spec in entry["specs"]
            if by_model.get(spec)
        ]
        if not scored:
            continue
        best = max(scored, key=lambda s: s["sci"])
        rows.append({**entry, **best, "variant": variant_label(best["spec"])})
    return sorted(rows, key=lambda r: -r["sci"])


def main():
    paths = [Path(p) for p in sys.argv[1:]] or [config.RUNS_DIR / "main.jsonl"]
    rows = leaderboard(load_runs(paths))
    w = SCI_SPEC["weights"]
    print(f"Starknet Coding Index {SCI_SPEC['version']} — baseline, weights "
          + " ".join(f"{k}={v}" for k, v in w.items()))
    print(f"{'#':>2} {'Model':16} {'variant':>9} {'SCI':>6} | {'effec':>5} {'corr':>5} {'cost':>5} {'speed':>5} | "
          f"{'1sub%':>6} {'med.att':>7} | {'open':>6} {'n':>4}")
    for i, r in enumerate(rows, 1):
        c, raw = r["components"], r["raw"]
        print(f"{i:>2} {r['label']:16} {r['variant']:>9} {r['sci']:6.1f} | {c['effective']:5.1f} {c['correct']:5.1f} "
              f"{c['cost']:5.0f} {c['speed']:5.0f} | {raw['one_sub_pct']:5.0f}% "
              f"{(raw['med_attempts'] or 0):7.1f} | "
              f"{'open' if r['open_weight'] else 'closed':>6} {raw['n_runs']:>4}")


if __name__ == "__main__":
    main()
