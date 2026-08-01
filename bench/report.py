"""Aggregate run records into a markdown report (main.jsonl unless told otherwise).

  uv run python -m bench.report [runs.jsonl ...]
"""

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from . import config


def load_runs(paths):
    runs = []
    for p in paths:
        with open(p) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("error") is None:
                    # Older records carry effort only in llm_opts; fold it into
                    # the model label so groups stay distinct across runs.
                    effort = (r.get("llm_opts") or {}).get("reasoning_effort")
                    if effort and "@" not in r["model"]:
                        r["model"] = f"{r['model']}@{effort}"
                    # A run that needed more than the model-time budget is a
                    # failure, whatever its tests eventually said — applied
                    # here so every consumer (report, sci, charts) agrees.
                    mt = (r.get("llm_time_s") or 0) + (r.get("assist_time_s") or 0)
                    r["over_time_budget"] = mt > config.MODEL_TIME_BUDGET_S
                    if r["over_time_budget"]:
                        r["solved"] = False
                    runs.append(r)
    return runs


def _med(vals):
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else None


def _fmt(v, spec=".1f", dash="—"):
    return format(v, spec) if v is not None else dash


def aggregate(runs):
    # Imported here, not at module scope: sci imports load_runs from this module,
    # so a top-level import would be circular.
    from .sci import run_cost

    groups = defaultdict(list)
    for r in runs:
        groups[(r["model"], r["condition"])].append(r)
    rows = []
    for (model, cond), rs in sorted(groups.items()):
        n = len(rs)
        pct_tests = [
            r["tests_passed"] / (r["tests_passed"] + r["tests_failed"])
            for r in rs
            if (r["tests_passed"] + r["tests_failed"]) > 0
        ]
        rows.append({
            "model": model,
            "condition": cond,
            "n": n,
            "solve_rate": sum(r["solved"] for r in rs) / n,
            "compile_rate": sum(r["compiled"] for r in rs) / n,
            "mean_pct_tests": statistics.mean(pct_tests) if pct_tests else 0.0,
            # model time = LLM streaming + doc-tool wait; excludes local
            # compile/test, which scales with runner concurrency (noise)
            "med_model_s": _med([
                r["llm_time_s"] + (r.get("assist_time_s") or 0) for r in rs
            ]),
            "med_turns": _med([r["turns"] for r in rs]),
            "med_tokens": _med([
                (r["prompt_tokens"] or 0) + (r["completion_tokens"] or 0) for r in rs
            ]),
            # median is what a task costs at today's prices; the total is what we
            # actually paid, so it stays on the recorded figure
            "med_cost": _med([run_cost(r) for r in rs]),
            "total_cost": sum(r["cost_usd"] or 0 for r in rs),
            # one early record predates this field; absent means no lookups
            "mean_assist_calls": statistics.mean([r.get("n_assist_calls") or 0 for r in rs]),
        })
    return rows


def markdown(rows, runs):
    lines = [
        "# The Starknet Coding Index — results",
        "",
        f"Runs aggregated: {len(runs)}",
        "",
        "| Model | Condition | n | Solve rate | Compile rate | Mean % tests passed | Med. model time (s) | Med. turns | Med. tokens | Med. cost ($) | Total cost ($) | Mean assist calls |",
        "|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['model']} | {r['condition']} | {r['n']} "
            f"| {r['solve_rate']:.0%} | {r['compile_rate']:.0%} | {r['mean_pct_tests']:.0%} "
            f"| {_fmt(r['med_model_s'], '.0f')} | {_fmt(r['med_turns'], '.0f')} "
            f"| {_fmt(r['med_tokens'], '.0f')} | {_fmt(r['med_cost'], '.4f')} "
            f"| {r['total_cost']:.2f} | {r['mean_assist_calls']:.1f} |"
        )

    # per-task solve matrix
    tasks = sorted({r["task"] for r in runs})
    lines += ["", "## Per-task solve rate (fraction of runs solved)", ""]
    combos = sorted({(r["model"], r["condition"]) for r in runs})
    header = "| Task | " + " | ".join(f"{m}<br>{c}" for m, c in combos) + " |"
    lines += [header, "|---|" + "--:|" * len(combos)]
    for t in tasks:
        cells = []
        for m, c in combos:
            rs = [r for r in runs if r["task"] == t and r["model"] == m and r["condition"] == c]
            cells.append(f"{sum(r['solved'] for r in rs)}/{len(rs)}" if rs else "—")
        lines.append(f"| {t} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def main():
    # main.jsonl only, like html_report: globbing the directory counted every
    # per-stream file that had already been merged into it, which inflated this
    # report by 1,102 duplicate runs (8,440 against 7,338 real ones)
    paths = [Path(p) for p in sys.argv[1:]] or [config.RUNS_DIR / "main.jsonl"]
    runs = load_runs(paths)
    if not runs:
        print("no runs found")
        sys.exit(1)
    rows = aggregate(runs)
    md = markdown(rows, runs)
    out = config.RESULTS_DIR / "report.md"
    out.write_text(md)
    print(md)
    print(f"written to {out}")


if __name__ == "__main__":
    main()
