"""Matrix runner CLI: task x model x condition x rep, resumable, concurrent.

Usage:
  uv run python -m bench.runner --models qwen/qwen3-coder --conditions baseline,mcp --reps 1

Model specs may carry a per-model reasoning effort with `@`:
  z-ai/glm-5.2@high,z-ai/glm-5.2@low,moonshotai/kimi-k3
`@none` forces no reasoning param even when --reasoning is set. A bare spec
uses --reasoning as its default (or nothing). OpenRouter variant suffixes
(`:free`, `:nitro`, ...) are part of the model id and pass through untouched.
The full spec is what gets recorded, resumed on, and grouped in reports.

--adaptive-reps runs 2 reps per cell, then a tiebreaker third rep for cells
whose first two reps disagree on solved — the budget-friendly default for
new sweeps (~30% cheaper than --reps 3, no uninterpretable 1-1 ties).
"""

import argparse
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import agent, config


def slug(s):
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", s)


def parse_model_spec(spec, default_reasoning=None):
    """Split 'model@effort' into (api_model, reasoning_effort)."""
    if "@" in spec:
        api_model, effort = spec.rsplit("@", 1)
        return api_model, (None if effort == "none" else effort)
    return spec, default_reasoning


def load_done(path):
    done = set()
    if path.exists():
        with open(path) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("error") is None:
                    done.add((r["task"], r["model"], r["condition"], r["rep"]))
    return done


def load_solved(path):
    """(task, model, condition, rep) -> solved, for error-free records.
    Later records win, so a rerun of a previously errored cell counts."""
    solved = {}
    if path.exists():
        with open(path) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("error") is None:
                    solved[(r["task"], r["model"], r["condition"], r["rep"])] = r["solved"]
    return solved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", required=True, help="comma-separated OpenRouter model ids")
    ap.add_argument("--tasks", default=None, help="comma-separated task ids (default: all)")
    ap.add_argument("--conditions", default="baseline,mcp")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--adaptive-reps", action="store_true",
                    help="2 reps per cell, plus a tiebreaker third rep only for "
                         "cells where the first two disagree on solved (ignores --reps)")
    ap.add_argument("--rep-offset", type=int, default=0, help="start rep numbering here")
    ap.add_argument("--concurrency", type=int, default=20)
    ap.add_argument("--reasoning", default=None, help="reasoning effort (e.g. high) via OpenRouter")
    ap.add_argument("--temperature", type=float, default=None, help="default: provider default")
    ap.add_argument("--provider-sort", default=None, help="OpenRouter provider routing, e.g. throughput")
    ap.add_argument("--provider-order", default=None,
                    help="pin to specific provider(s), comma-separated, no fallbacks — "
                         "needed when thought signatures don't validate across providers")
    ap.add_argument("--out", default=str(config.RUNS_DIR / "runs.jsonl"))
    ap.add_argument("--fake", action="store_true", help="dry-run with scripted fake model")
    args = ap.parse_args()
    if args.adaptive_reps and args.rep_offset:
        ap.error("--adaptive-reps manages rep numbering itself; drop --rep-offset")
    if args.adaptive_reps and args.reps != 1:
        print("(--adaptive-reps set; ignoring --reps)")

    models_list = [m.strip() for m in args.models.split(",") if m.strip()]
    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]
    if args.tasks:
        tasks = [t.strip() for t in args.tasks.split(",")]
    else:
        tasks = sorted(
            d.name for d in config.TASKS_DIR.iterdir()
            if d.is_dir() and (d / "prompt.md").exists()
        )

    from pathlib import Path
    out_path = Path(args.out) if args.out.startswith("/") else config.REPO_ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = load_done(out_path)

    reps_range = (
        range(0, 2) if args.adaptive_reps
        else range(args.rep_offset, args.rep_offset + args.reps)
    )
    cells = [
        (t, m, c, r)
        for r in reps_range
        for t in tasks
        for m in models_list
        for c in conditions
        if (t, m, c, r) not in done
    ]
    print(f"{len(cells)} runs to do ({len(done)} already complete in {out_path})")

    chat_fn = None
    if args.fake:
        from .fake_model import fake_chat
        chat_fn = fake_chat

    lock = threading.Lock()

    base_opts = {}
    if args.temperature is not None:
        base_opts["temperature"] = args.temperature
    if args.provider_sort:
        base_opts["provider_sort"] = args.provider_sort
    if args.provider_order:
        base_opts["provider_order"] = [p.strip() for p in args.provider_order.split(",")]

    def one(cell):
        t, m, c, r = cell
        api_model, effort = parse_model_spec(m, default_reasoning=args.reasoning)
        llm_opts = dict(base_opts)
        if effort:
            llm_opts["reasoning_effort"] = effort
        run_id = f"{t}__{slug(m)}__{c}__rep{r}"
        rec = agent.run_agent(
            t, m, c, run_id, r, chat_fn=chat_fn, llm_opts=llm_opts, api_model=api_model
        )
        with lock:
            with open(out_path, "a") as f:
                f.write(json.dumps(rec) + "\n")
        return rec

    def run_cells(batch):
        with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
            futs = {ex.submit(one, cell): cell for cell in batch}
            for i, fut in enumerate(as_completed(futs), 1):
                t, m, c, r = futs[fut]
                try:
                    rec = fut.result()
                    status = "SOLVED" if rec["solved"] else (
                        "ERROR" if rec["error"] else
                        f"{rec['tests_passed']}p/{rec['tests_failed']}f"
                    )
                    cost = rec["cost_usd"]
                    print(
                        f"[{i}/{len(batch)}] {t} | {m} | {c} | rep{r} -> {status} "
                        f"({rec['turns']} turns, {rec['wall_time_s']:.0f}s"
                        f"{f', ${cost:.4f}' if cost is not None else ''})"
                        f"{' err=' + rec['error'] if rec['error'] else ''}",
                        flush=True,
                    )
                except Exception as e:
                    print(f"[{i}/{len(batch)}] {t} | {m} | {c} | rep{r} -> CRASH {e}", flush=True)

    started = time.monotonic()
    run_cells(cells)

    if args.adaptive_reps:
        # Third rep only where the first two disagree on solved. Read the out
        # file rather than in-memory results so ties from earlier (partial)
        # invocations of the same matrix are also picked up.
        solved = load_solved(out_path)
        tiebreak = [
            (t, m, c, 2)
            for t in tasks
            for m in models_list
            for c in conditions
            if (t, m, c, 0) in solved and (t, m, c, 1) in solved
            and solved[(t, m, c, 0)] != solved[(t, m, c, 1)]
            and (t, m, c, 2) not in solved
        ]
        print(f"tiebreaker pass: {len(tiebreak)} split cells")
        run_cells(tiebreak)

    print(f"done in {time.monotonic() - started:.0f}s")


if __name__ == "__main__":
    main()
