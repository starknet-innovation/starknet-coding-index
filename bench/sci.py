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

import json
import math
import random
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

# Prices move after the runs are recorded. cost_usd in main.jsonl stays exactly
# as billed, because it is the audit trail and what bench.status reports as
# spend; scoring applies the revision here instead.
#
# Each entry is (price when the runs were billed, price listed now) per million
# tokens: input, output, cache read, cache write. A revision is only expressible
# as one multiplier when EVERY component moved by the same factor, since only
# then is the new cost of a recorded run independent of its mix of fresh, cached
# and output tokens. price_ratio() asserts that rather than trusting it, and
# both vectors are kept because refreshing model_meta.json to current prices
# erases the old ones and would leave the multiplier unverifiable.
#
# Not revisable, and deliberately absent: OpenAI cut gpt-5.6-luna and -terra
# uniformly, but qwen3.6-27b, gemma-4-31b and qwen3-coder-next moved their input
# and output prices by different factors. Their costs cannot be re-based from a
# list price at all, because prompt caching hides the read/write split and
# throughput routing sent them to providers charging well off the listing.
#
# Check prices programmatically, never from a web summary: urllib against
# https://openrouter.ai/api/v1/models returns every model, and
# /models/<id>/endpoints gives the per-provider prices, which differ a lot (Terra
# was $1/$6 direct, $2/$12 priority, $2.50/$15 on Azure, and the press quoted the
# priority tier). A summary of a pricing page has been wrong here before.
#
# Prices are the standard endpoint. Sol and Terra also publish a half-price
# "flex" tier, but that is a deferred-latency service class we did not benchmark,
# and pricing runs at flex while keeping the latency we measured on standard
# would corrupt the speed component.
PRICE_REVISIONS = {
    # OpenAI cut Terra 60% and Luna 90% on 2026-07-30 (Sol unchanged, verified
    # at the endpoint level). The -pro serving modes had no price of their own in
    # the 2026-07-24 snapshot and OpenRouter lists them today at exactly the base
    # price, so they inherit the base ratio, which keeps pro-vs-base comparisons
    # on a single basis.
    "openai/gpt-5.6-terra":     ((2.50, 15.00, 0.25, 3.125), (1.00, 6.00, 0.10, 1.250)),
    "openai/gpt-5.6-terra-pro": ((2.50, 15.00, 0.25, 3.125), (1.00, 6.00, 0.10, 1.250)),
    "openai/gpt-5.6-luna":      ((1.00,  6.00, 0.10, 1.250), (0.10, 0.60, 0.01, 0.125)),
    "openai/gpt-5.6-luna-pro":  ((1.00,  6.00, 0.10, 1.250), (0.10, 0.60, 0.01, 0.125)),
    # Z.ai cut GLM 5.2 ~10% in the same week, unrelated to OpenAI.
    "z-ai/glm-5.2":             ((0.7966, 2.5036, 0.14794, None), (0.7168, 2.2528, 0.13312, None)),
}


# Which models a person could actually run themselves. The threshold is memory,
# not parameter count: 128 GB of unified memory is where the machines you can
# buy today top out -- NVIDIA's DGX Spark, the AMD Strix Halo boxes and the M5
# Max MacBook Pro all cap there. (The 512 GB Mac Studio M3 Ultra that set the
# old bar is gone: Apple pulled the option in March 2026 during the DRAM
# shortage, and the line now stops at 96 GB.) TOTAL parameters, not active,
# because every weight has to be resident even when a sparse MoE only fires a
# few experts per token.
#
# The bar is Q4_K_M, the default 4-bit quant, and the size is the one the
# published GGUF actually weighs rather than one computed from a bit width. That
# matters: arithmetic at a nominal 4.5 bits/weight understated every large model
# by about 10% (GLM 5.2 is 466 GB on disk, not 424), and it is simply wrong for
# gpt-oss-120b, which ships native MXFP4 and weighs ~63 GB at EVERY quant level
# where the formula would claim 117 GB at 8-bit.
#
# LOCAL_FALLBACK_BITS covers the models with no published GGUF (Hy3, DeepSeek
# V4-Pro, Inkling). It is calibrated on the seven measured Q4_K_M files, which
# land at 4.77-5.05 bits/weight, mean 4.92; gpt-oss is excluded from that mean
# because its native 4-bit format makes it unrepresentative.
#
# The reserve covers the OS, the KV cache and activations, leaving 112 GB of
# weights. The boundary is comfortable: the largest member is gpt-oss-120b at
# ~63 GB and the nearest miss is Hy3 at ~181 GB (estimated; no published GGUF).
LOCAL_VRAM_GB = 128
LOCAL_QUANT = "Q4_K_M"
LOCAL_FALLBACK_BITS = 4.92
LOCAL_RESERVE_GB = 16
LOCAL_WEIGHT_BUDGET_GB = LOCAL_VRAM_GB - LOCAL_RESERVE_GB

# How many models the headline charts draw. Rank decides membership and nothing
# else: the charts used to show every model that did NOT fit the local class,
# which sorted the page by memory footprint rather than by how good the model is
# and left a 9th-place model off the leaderboard for being small enough to run.
# The local class keeps its own section below, so a model outside this cut is
# still measured; it is just not in the headline comparison.
#
# Lives here rather than in html_report because the audit checks chart
# membership and the two must not disagree about who is in.
CHART_TOP_N = 15

_META = None


def _model_meta():
    global _META
    if _META is None:
        path = config.RESULTS_DIR / "model_meta.json"
        _META = json.loads(path.read_text())["models"]
    return _META


def param_count(s):
    """'1.02T' / '753B' / '~40B' -> absolute count. None passes through."""
    if not s:
        return None
    return float(s.lstrip("~").rstrip("TB")) * (1e12 if s.endswith("T") else 1e9)


def weights_gb(params, bits=LOCAL_FALLBACK_BITS):
    """GB of weights at a given bit width. None passes through."""
    return None if params is None else params * bits / 8 / 1e9


def local_vram_gb(spec):
    """GB the weights need at Q4_K_M, and whether that figure was measured.

    Returns (gb, measured). gb is None for closed models and for any open model
    whose parameter count the lab has not disclosed: you cannot run what you
    cannot download, and you cannot size what nobody published.
    """
    mm = _model_meta().get(spec.partition("@")[0], {})
    measured = (mm.get("gguf") or {}).get(LOCAL_QUANT)
    if measured:
        return measured, True
    return weights_gb(param_count(mm.get("params_total"))), False


# The machines the open-weight table answers for, largest first, and what each
# has to keep back for the OS, the KV cache and activations. 128 GB is unified
# memory where the OS lives in the same pool, hence the larger reserve; the
# smaller tiers are dedicated cards, where only the KV cache and activations
# compete with the weights.
#
# 16 GB is deliberately absent: the smallest 4-bit file any of these models
# publishes is 15 to 18 GB, so every cell came out empty and the column only
# repeated what the prose says.
VRAM_BUDGETS = [128, 64, 32, 24]
BUDGET_RESERVE = {128: 16, 64: 8, 32: 4, 24: 4}

# The band a recommendation may sit in, in bits per weight. The ceiling is just
# above Q8_0: past that a bigger file is more container, not more quality, and
# nobody should be told to run BF16 to write Cairo. The floor is the same 4-bit
# line the local-inference class draws, so a cell is EMPTY rather than filled
# with a 2-bit quant the rest of this report says not to trust.
#
# Measured bits, not the name: K-quants keep some tensors wider than the label
# suggests, so Q3_K_L on a 30B model really is 4.0 bits/weight. On this roster a
# name floor and a measured floor pick identically, because the cell takes the
# largest fitting file and the floor only decides empty-vs-degraded.
QUANT_CEILING_BITS = 8.6
QUANT_FLOOR_BITS = 3.9

# Formats that are strictly worse than a K-quant of the same weight: legacy
# fixed-block layouts, kept in repos for compatibility. Only consulted to break
# a near-tie on size, never to exclude a file outright.
LEGACY_QUANTS = ("Q4_0", "Q4_1", "Q5_0", "Q5_1")


def best_quant_for(spec, vram_gb):
    """(quant name, GB) of the best published file that runs on a vram_gb machine.

    None when the model publishes nothing 4-bit or better that fits, which is the
    honest answer for most of the field: a 466 GB floor does not become runnable
    by naming a smaller file.

    Reads the whole published ladder rather than the canonical five, because the
    answer is usually a rung the five skip (Muse Glimmer at 32 GB is Q6_K_L, which
    is not one of them). That ladder is what `files` in model_meta.json is for.
    """
    mm = _model_meta().get(spec.partition("@")[0], {})
    gg = mm.get("gguf") or {}
    files = gg.get("files") or {}
    params = param_count(mm.get("params_total"))
    if not files or not params:
        return None
    budget = vram_gb - BUDGET_RESERVE[vram_gb]
    q4 = gg.get(LOCAL_QUANT)
    ok = {}
    for name, gb in files.items():
        if gb > budget:
            continue
        bits = gb * 8e9 / params
        if not QUANT_FLOOR_BITS <= bits <= QUANT_CEILING_BITS:
            continue
        # Same guard the size grid used to carry: a native-4-bit release
        # (gpt-oss ships MXFP4) repacks to within a few percent at every level,
        # so its heavier rungs are bigger containers holding identical weights.
        # Without this, picking by size recommends gpt-oss's "F16" at 65 GB.
        if q4 and gb > q4 and gb < q4 * 1.10:
            continue
        ok[name] = gb
    if not ok:
        return None
    best = max(ok.values())
    # Among files within 5% of the largest, prefer a modern K or IQ quant: at
    # equal weight a legacy layout is worse, and picking on size alone printed
    # Gemma's Q4_1 over a K-quant of the same size.
    near = [n for n, gb in ok.items() if gb >= best * 0.95]
    modern = [n for n in near if not any(l in n for l in LEGACY_QUANTS)]
    pool = modern or near
    # On an exact size tie prefer Q4_K_M, the name the rest of the report uses:
    # gpt-oss publishes Q4_K_S and Q4_K_M at the same 62.8 GB, and picking
    # between them on size alone is a coin toss the reader has to interpret.
    winner = max(pool, key=lambda n: (ok[n], n == LOCAL_QUANT))
    return winner, ok[winner]


def fits_locally(entry):
    """True when this model's Q4_K_M weights fit one 128 GB machine.

    Scans the entry's specs rather than trusting specs[0], which for some models
    is a pro serving mode with an id of its own and no metadata row.
    """
    if not entry.get("open_weight"):
        return False
    for spec in entry["specs"]:
        gb, _ = local_vram_gb(spec)
        if gb is not None:
            return gb <= LOCAL_WEIGHT_BUDGET_GB
    return False


def price_ratio(spec):
    """Multiplier taking a recorded cost to what the same run would cost now.

    1.0 when the model has no revision. Raises when a revision's components
    disagree, because a non-uniform change cannot be applied to a recorded total
    at all: it needs the token mix, which caching hides.
    """
    rev = PRICE_REVISIONS.get(spec.partition("@")[0])
    if rev is None:
        return 1.0
    was, now = rev
    ratios = [n / w for w, n in zip(was, now) if w and n]
    if max(ratios) - min(ratios) > 1e-9:
        raise ValueError(f"{spec}: non-uniform price revision {ratios}, "
                         "cannot be applied as a single multiplier")
    return ratios[0]


def run_cost(run):
    """Recorded cost of a run at current prices. None stays None."""
    c = run.get("cost_usd")
    return None if c is None else c * price_ratio(run["model"])


# Candidate variants per model; the leaderboard scores every candidate with
# data and keeps the best (policy: "best foot forward", variant labeled on
# the chart). The extension point for future models.
MODEL_REGISTRY = [
    # weights published 2026-07-27 as moonshotai/Kimi-K3 (96 safetensors shards,
    # public and ungated), so the weights_pending star this entry used to carry
    # is gone; OpenRouter now points this id at that repo
    # bare = provider default (max); @high/@low added 2026-07-25 after OpenRouter
    # showed K3 accepts them and we had only ever measured one configuration
    {"specs": ["moonshotai/kimi-k3", "moonshotai/kimi-k3@high", "moonshotai/kimi-k3@low",
               "moonshotai/kimi-k3@disabled"],
     "label": "Kimi K3", "lab": "Moonshot", "open_weight": True},
    {"specs": ["xiaomi/mimo-v2.5-pro@max", "xiaomi/mimo-v2.5-pro@xhigh",
               "xiaomi/mimo-v2.5-pro@high", "xiaomi/mimo-v2.5-pro@medium",
               "xiaomi/mimo-v2.5-pro@low", "xiaomi/mimo-v2.5-pro@minimal",
               "xiaomi/mimo-v2.5-pro@disabled"],
     "label": "MiMo-V2.5-Pro", "lab": "Xiaomi", "open_weight": True},
    {"specs": ["deepseek/deepseek-v4-pro@xhigh", "deepseek/deepseek-v4-pro@high",
               "deepseek/deepseek-v4-pro@medium", "deepseek/deepseek-v4-pro@low",
               "deepseek/deepseek-v4-pro@minimal", "deepseek/deepseek-v4-pro@disabled"],
     "label": "DeepSeek V4-Pro", "lab": "DeepSeek", "open_weight": True},
    # the 0731 release, not the preview: DeepSeek calls it the official one, and
    # the two expose different ladders (preview xhigh/high, release max/high/low)
    {"specs": ["deepseek/deepseek-v4-flash-0731@max",
               "deepseek/deepseek-v4-flash-0731@high",
               "deepseek/deepseek-v4-flash-0731@low",
               "deepseek/deepseek-v4-flash-0731@disabled"],
     "label": "DeepSeek V4 Flash", "lab": "DeepSeek", "open_weight": True},
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
    # Benchmarked 2026-08-03. Weights ANNOUNCED for the week of 2026-08-10 via
    # Alibaba Model Studio, the first Max-class Qwen to be opened, so this entry
    # carries weights_pending exactly as Kimi K3's did until 2026-07-27. 2.4T
    # total / ~95B active, which estimates to ~1.5 TB at Q4_K_M: open, but not
    # anyone's local machine.
    #
    # Probe: @disabled REJECTED ("Reasoning is mandatory for this endpoint"), so
    # @minimal is the floor. The ladder is two bands, not a gradient: minimal /
    # low / medium answer a one-line function in 8-11s, while high / xhigh / max
    # spend 2-5 MINUTES and 6-12k tokens on the same prompt, and the bare default
    # is the most expensive setting of all. @low was left unswept because the
    # probe put it inside @minimal's band (333 vs 381 tokens).
    #
    # @medium is an interior winner, so the ladder closed without @max. @high is
    # the worst tier on every axis at once and lost h1_component at 930s, past
    # the model-time budget, on a run it had actually solved.
    {"specs": ["qwen/qwen3.8-max@high", "qwen/qwen3.8-max@medium",
               "qwen/qwen3.8-max@minimal"],
     "label": "Qwen3.8 Max", "lab": "Alibaba", "open_weight": True,
     "weights_pending": True},
    # Full ladder swept 2026-07-25 for the effort-curve section (both conditions).
    {"specs": ["qwen/qwen3.6-27b@max", "qwen/qwen3.6-27b@xhigh", "qwen/qwen3.6-27b@high",
               "qwen/qwen3.6-27b@medium", "qwen/qwen3.6-27b@low",
               "qwen/qwen3.6-27b@minimal", "qwen/qwen3.6-27b@disabled"],
      "label": "Qwen3.6-27B", "lab": "Alibaba", "open_weight": True},
    # Small open-weight batch 2026-07-24. gpt-oss: @disabled REJECTED
    # ("Reasoning is mandatory"), effort ladder low/medium/high; 0% correct at
    # every tier. coder-next: no reasoning params at all, bare only; 0% correct.
    # 35b-a3b: dial accepted (effort levels likely coerced; bare behaves
    # differently); gemma: dial accepted. All winning edges at surface floors.
    {"specs": ["openai/gpt-oss-120b@low", "openai/gpt-oss-120b@medium",
               "openai/gpt-oss-120b@high"],
     "label": "gpt-oss-120b", "lab": "OpenAI", "open_weight": True},
    {"specs": ["qwen/qwen3.6-35b-a3b", "qwen/qwen3.6-35b-a3b@disabled",
               "qwen/qwen3.6-35b-a3b@minimal", "qwen/qwen3.6-35b-a3b@low",
               "qwen/qwen3.6-35b-a3b@medium", "qwen/qwen3.6-35b-a3b@high",
               "qwen/qwen3.6-35b-a3b@xhigh", "qwen/qwen3.6-35b-a3b@max"],
     "label": "Qwen3.6-35B-A3B", "lab": "Alibaba", "open_weight": True},
    {"specs": ["google/gemma-4-31b-it@disabled", "google/gemma-4-31b-it@low",
               "google/gemma-4-31b-it@high"],
     "label": "Gemma 4 31B", "lab": "Google", "open_weight": True},
    {"specs": ["qwen/qwen3-coder-next"],
     "label": "Qwen3 Coder Next", "lab": "Alibaba", "open_weight": True},
    # Published 2026-08-09, benchmarked 2026-08-11. Dense 29.8B, Apache 2.0,
    # multimodal; Q4_K_M is 17.3 GB, so it runs on one machine comfortably.
    #
    # Probe: @disabled REJECTED ("Reasoning is mandatory for this endpoint and
    # cannot be disabled"). @minimal is ACCEPTED even though it is absent from
    # OpenRouter's supported_efforts, and it is coerced: paired against @low on
    # first-call output tokens across four tasks it moves +18%, +17%, -6%, -1%,
    # mixed signs around one effective level, so it is left unswept. The four
    # real tiers are cleanly monotone (median first-call output tokens: low 724,
    # medium 1448, high 3605, xhigh 7197) and medium is the documented default.
    #
    # The curve is INVERTED end to end: the floor wins on every axis at once.
    # @low solves 87% where @xhigh solves 47%, at a sixth of the latency and
    # cost. The failure is a compile that never lands, not a wrong answer:
    # unsolved runs sit at 0 tests passed and 0 failed after exhausting the
    # 10-turn budget, which happens in 13% of @low runs and 56% of @xhigh ones.
    # So the ladder is closed downward with nothing left below @low to try.
    {"specs": ["meta/muse-glimmer-30b@low", "meta/muse-glimmer-30b@medium",
               "meta/muse-glimmer-30b@high", "meta/muse-glimmer-30b@xhigh"],
     "label": "Muse Glimmer 30B", "lab": "Meta", "open_weight": True},
    # Probe 2026-07-24: full surface honored incl. @disabled; real curve with
    # overshoot (correct 79 off -> 99 low -> 88 high); low = interior winner.
    # @medium and @max are listed in OpenRouter's supported_efforts but return
    # "Internal server error" on every request (11/11 on 2026-07-25, while @high
    # solved in the same minute), so the ladder really is three tiers wide.
    {"specs": ["thinkingmachines/inkling@disabled", "thinkingmachines/inkling@low",
               "thinkingmachines/inkling@high"],
     "label": "Inkling", "lab": "Thinking Machines", "open_weight": True},
    # Probe 2026-07-24: adaptive-Anthropic signature (all variants identical on
    # the probe, @disabled honored). Bracket: 78/78 solved, 0 tiebreaks; low =
    # interior winner (91.5, 100% one-shot, speed 96). -fast serving tier
    # skipped per the Opus 4.8 precedent and pro-modes-dominated finding.
    {"specs": ["anthropic/claude-opus-5@disabled", "anthropic/claude-opus-5@low",
               "anthropic/claude-opus-5@high", "anthropic/claude-opus-5@xhigh",
               "anthropic/claude-opus-5@max"],
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
    {"specs": ["anthropic/claude-sonnet-5@max", "anthropic/claude-sonnet-5@xhigh",
               "anthropic/claude-sonnet-5@high", "anthropic/claude-sonnet-5@medium",
               "anthropic/claude-sonnet-5@low", "anthropic/claude-sonnet-5@minimal",
               "anthropic/claude-sonnet-5@disabled", "anthropic/claude-sonnet-5"],
     "label": "Sonnet 5", "lab": "Anthropic", "open_weight": False},
    {"specs": ["google/gemini-3.6-flash@max", "google/gemini-3.6-flash@xhigh",
               "google/gemini-3.6-flash@high", "google/gemini-3.6-flash@medium",
               "google/gemini-3.6-flash@low", "google/gemini-3.6-flash@minimal"],
     "label": "Gemini 3.6 Flash", "lab": "Google", "open_weight": False},
    {"specs": ["openai/gpt-5.6-luna-pro", "openai/gpt-5.6-luna@max",
               "openai/gpt-5.6-luna@xhigh", "openai/gpt-5.6-luna@high",
               "openai/gpt-5.6-luna@medium", "openai/gpt-5.6-luna@low",
               "openai/gpt-5.6-luna@minimal", "openai/gpt-5.6-luna@disabled"],
     # dropped 2026-07-25 as a budget tier that was not a coding pick, reinstated
     # 2026-08-01: OpenAI cut its price 90%, which is exactly the kind of change
     # that reopens a value-based drop, and the full ladder was already measured
     "label": "GPT-5.6 Luna", "lab": "OpenAI", "open_weight": False},
    {"specs": ["meta/muse-spark-1.2@xhigh", "meta/muse-spark-1.2@high",
               "meta/muse-spark-1.2@medium", "meta/muse-spark-1.2@low",
               "meta/muse-spark-1.2@minimal"],
     # reasoning mandatory, ladder minimal..xhigh, default medium (OpenRouter
     # reasoning block, 2026-08-06); weights closed per Meta's launch coverage
     "label": "Muse Spark 1.2", "lab": "Meta", "open_weight": False},
    {"specs": ["x-ai/grok-4.5@max", "x-ai/grok-4.5@xhigh", "x-ai/grok-4.5@high",
               "x-ai/grok-4.5@medium", "x-ai/grok-4.5@low", "x-ai/grok-4.5@minimal"],
     # thinking mandatory (@disabled rejected); bare = dynamic, skipped
     "label": "Grok 4.5", "lab": "xAI", "open_weight": False},
    {"specs": ["anthropic/claude-fable-5@max", "anthropic/claude-fable-5@xhigh",
               "anthropic/claude-fable-5@high", "anthropic/claude-fable-5@medium",
               "anthropic/claude-fable-5@low", "anthropic/claude-fable-5@minimal"],
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


# Bare specs (no @effort) run at whatever the provider defaults to. Where
# OpenRouter documents that default, label the level; where it documents thinking
# as ON by default, "off" would be a lie.
#
# Checked against OpenRouter's per-model `reasoning` block on 2026-07-25:
#   kimi-k3        default_effort max   -> "max" stands
#   hy3            default_effort high  -> "high" stands
#   claude-sonnet-5 default_enabled TRUE, default_effort high -> was labelled
#     "off", which was wrong: we never sent a reasoning param, so these runs are
#     the default, not disabled (we never ran sonnet@disabled at all). Our own
#     data agrees, twice over: the dial is inert rather than off (bare and
#     @minimal/@low/@medium/@high all land at 1.73-1.82k output tokens, 13-15s,
#     100% solved), and the explicit @disabled cell we later ran scores 80.5,
#     BELOW the default's 83.4.
#
# Label the effort the default maps to, not the word "default", which tells a
# reader nothing: every value here is the level OpenRouter documents as that
# model's default_effort, so "high" for a bare Sonnet run is a claim about the
# provider's behaviour and not our own shorthand.
BARE_VARIANT_LABELS = {
    "moonshotai/kimi-k3": "max",   # documented default_effort: max
    "tencent/hy3": "high",         # documented default_effort: high, and bare
                                   # measured identical to its explicit high tier
    "anthropic/claude-sonnet-5": "high",   # documented default_effort: high
    "anthropic/claude-haiku-4.5": "high",  # deprecated; OpenRouter documents no
                                           # default_effort for it, high assumed
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
    costs = [c for c in (run_cost(r) for r in runs_for_model) if c is not None]
    raw = {"med_llm": statistics.median(svc_times) if svc_times else None,
           "med_cost": statistics.median(costs) if costs else None,
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


def index_ci(runs_for_model, resamples=1000, seed=0):
    """Half-width of the 95% interval on this model's SCI, resampling its runs.

    The published number, so it lives here rather than in the report or the
    status tool: those two disagreed in the second digit while each rolled its
    own bootstrap, and a precision figure that changes per caller is worse than
    none. 1000 resamples is what it takes for the printed digit to hold still.
    """
    if len(runs_for_model) < 4:
        return None
    rng = random.Random(seed)
    vals = sorted(compute_sci(rng.choices(runs_for_model, k=len(runs_for_model)))["sci"]
                  for _ in range(resamples))
    lo, hi = int(resamples * 0.025), int(resamples * 0.975) - 1
    return (vals[hi] - vals[lo]) / 2


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

    Each model is scored at every benchmarked candidate variant; the row carries
    the best one (spec + variant fields say which).

    "Best" is the highest SCI, full stop -- a 2026-08-05 decision that replaced
    a tie rule (variants within 0.5 with overlapping intervals went to the
    deepest-measured cell). The tradeoff was discussed and accepted: a winner
    label can now flip on noise between data refreshes when adjacent cells sit
    hundredths apart (Kimi K3 low vs default was the live case), and the
    published intervals, not the selection rule, tell readers how seriously to
    take any such ordering.
    """
    condition = condition or SCI_SPEC["condition"]
    by_model = defaultdict(list)
    for r in all_runs:
        if r["condition"] == condition:
            by_model[r["model"]].append(r)
    rows = []
    for entry in active_models():
        scored = [
            {"spec": spec, **compute_sci(by_model[spec]), "n": len(by_model[spec]),
             "ci": index_ci(by_model[spec])}
            for spec in entry["specs"]
            if by_model.get(spec)
        ]
        if not scored:
            continue
        best = max(scored, key=lambda s: s["sci"])
        gb, measured = local_vram_gb(best["spec"])
        rows.append({**entry, **best, "variant": variant_label(best["spec"]),
                     # derived, never hand-set: see fits_locally
                     "local": fits_locally(entry),
                     "vram_gb": gb, "vram_measured": measured})
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
