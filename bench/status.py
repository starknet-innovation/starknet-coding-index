"""Live progress of the benchmark: where every model stands right now.

  uv run python -m bench.status            # snapshot
  uv run python -m bench.status --watch     # refresh every 20s

Reads results/runs/main.jsonl, which the runner appends to as it goes, so this
is safe to run at any time against a running sweep. For each registry model it
shows the variant the index currently picks, how many runs it has, and the
bootstrapped confidence interval on its SCI: the number that decides whether
the model's rank is real or noise.
"""

import argparse
import random
import statistics as st
import sys
import time

from . import config
from .report import load_runs
from .sci import SCI_SPEC, active_models, compute_sci, variant_label

# Points of SCI. Not tighter than 5 on purpose: almost every adjacent pair in
# the ranking is under 2 points apart, so those models are ties at any budget we
# would spend. Going 5 -> 3 cost ~$47 and 1,300 runs to resolve one extra pair.
# 5 keeps each published score meaningful without buying false precision.
CI_TARGET = 5.0
BOOTSTRAP = 200        # resamples; enough for a stable half-width, fast to run


def boot_ci(rs, b=BOOTSTRAP, seed=0):
    """Half-width of the 95% interval on this model's SCI, by resampling runs."""
    if len(rs) < 4:
        return None
    rng = random.Random(seed)
    vals = [compute_sci(rng.choices(rs, k=len(rs)))["sci"] for _ in range(b)]
    q = st.quantiles(vals, n=40)
    return (q[-1] - q[0]) / 2


def bar(frac, width=14):
    filled = max(0, min(width, round(frac * width)))
    return "#" * filled + "." * (width - filled)


def snapshot(runs):
    n_tasks = len({r["task"] for r in runs if r["task"] != "fake"})
    rows, done, pending = [], 0, 0
    for e in active_models():   # never touch deprecated models
        scored = []
        for spec in e["specs"]:
            rs = [x for x in runs if x["model"] == spec and x["condition"] == "baseline"]
            if rs:
                scored.append((compute_sci(rs)["sci"], spec, rs))
        if not scored:
            continue
        sci, spec, rs = max(scored)
        ci = boot_ci(rs)
        met = ci is not None and ci <= CI_TARGET
        # runs needed for this CI to reach the target, assuming CI ~ 1/sqrt(n)
        need = len(rs) if met or ci is None else int(len(rs) * (ci / CI_TARGET) ** 2)
        need = -(-need // n_tasks) * n_tasks          # whole passes
        rows.append((sci, e["label"], variant_label(spec), len(rs), need, ci, met))
        done += min(len(rs), need)
        pending += max(0, need - len(rs))
    rows.sort(reverse=True)

    print(f"Starknet Coding Index {SCI_SPEC['version']}  |  "
          f"target: every model within +/-{CI_TARGET:.0f} SCI points")
    print(f"{'model':18s} {'variant':>8} {'SCI':>6} {'runs':>10} {'CI':>7}  progress")
    for sci, label, var, n, need, ci, met in rows:
        ci_txt = "n/a" if ci is None else f"+/-{ci:.1f}"
        mark = "ok " if met else "   "
        frac = 1.0 if met else (n / need if need else 1.0)
        print(f"{label:18s} {var:>8} {sci:6.1f} {n:>5}/{need:<4} {ci_txt:>7} {mark}{bar(frac)}")

    # runs added by the precision top-up are exactly those at rep >= 3:
    # every earlier sweep used reps 0-2 (2 plus an adaptive tiebreaker).
    new = [r for r in runs if r["condition"] == "baseline" and r["rep"] >= 3]
    spend = sum(r["cost_usd"] or 0 for r in new)
    total_spend = sum(r["cost_usd"] or 0 for r in runs)
    pct = 100 * done / (done + pending) if (done + pending) else 100
    print(f"\nprecision top-up: {len(new):,} runs added, ${spend:,.2f} spent, "
          f"{pending:,} runs still needed  ({pct:.0f}% there)")
    print(f"all runs on file: {len(runs):,}  |  total spend ${total_spend:,.2f}")
    return pending


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch", action="store_true", help="refresh until the target is met")
    ap.add_argument("--every", type=int, default=20, help="seconds between refreshes")
    args = ap.parse_args()
    path = config.RUNS_DIR / "main.jsonl"
    while True:
        runs = load_runs([path])
        if not args.watch:
            snapshot(runs)
            return
        print("\033[2J\033[H", end="")       # clear, home
        print(time.strftime("%H:%M:%S"), "  (ctrl-c to stop watching)\n")
        if snapshot(runs) == 0:
            print("\ntarget met for every model")
            return
        time.sleep(args.every)


if __name__ == "__main__":
    main()
