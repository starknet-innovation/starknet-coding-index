# Working on this repo

The deliverable is the **Starknet Coding Index**: one composite score per LLM for how
well it writes Starknet smart contracts unaided, plus a per-model measurement of what
the Cairo Coder documentation tool adds. `README.md` tells that story for a reader.
This file is the operating manual for whoever edits the code.

Every number anyone sees comes from `results/runs/main.jsonl` through
`bench/sci.py`. Nothing is hand-maintained, and `bench/audit.py` exists to keep it
that way.

## Where things live

| Path | What it does |
|---|---|
| `bench/runner.py` | matrix CLI: `task × model × condition × rep`, concurrent, resumable |
| `bench/agent.py` | one run: the agentic repair loop, enforces the turn and time budgets live |
| `bench/workspace.py` | copies a task package, applies submitted code, runs `scarb build` + `snforge test` |
| `bench/models.py` | OpenRouter client: streaming, usage/cost accounting, reasoning round-trip, retry |
| `bench/cairo_coder.py` | the MCP condition's tool, replicating `@kasarlabs/cairo-coder-mcp` v0.2.5 |
| `bench/sci.py` | the index: `SCI_SPEC`, `MODEL_REGISTRY`, `leaderboard()`, `index_ci()` |
| `bench/html_report.py` | `results/report.html`, charts included, with build-time gates |
| `bench/report.py` | markdown tables, and `load_runs()`, which every consumer shares |
| `bench/audit.py` | re-checks every published figure against the data; exits non-zero on drift |
| `bench/status.py` | live progress of a sweep: runs done vs needed, intervals, spend |
| `bench/screenshot.py` | regenerates the report and shoots every section to `results/shots/` |
| `bench/validate_tasks.py` | gate for task packages: reference solution passes, stub fails |
| `tasks/<id>/` | `prompt.md`, `Scarb.toml`, stub `src/lib.cairo`, hidden `tests/`, `solution/lib.cairo` |
| `results/runs/main.jsonl` | the dataset, one JSON object per run, append-only |

## Commands

```bash
uv run python -m bench.html_report     # rebuild results/report.html
uv run python -m bench.audit           # release gate: every published figure, exit 1 on drift
uv run python -m bench.sci             # the leaderboard, per model and variant
uv run python -m bench.status          # per-model intervals vs the precision target (--watch)
uv run python -m bench.screenshot      # regen + screenshot every section (visual QA)
uv run python -m bench.validate_tasks  # solutions pass, stubs fail
uv run python -m bench.runner --models <spec,...> --conditions baseline,mcp --reps 1
```

Only `runner` spends money on model APIs. Everything else is local, and the first four
touch nothing but `results/`.

## The data model

A run is identified by `(task, model, condition, rep)`. That tuple is what
`runner.load_done()` resumes on, so re-running a command only fills the gaps.

`report.load_runs()` is the single loader; `sci`, `html_report`, `audit` and `status`
all go through it. It does three things worth knowing:

- **Drops records with a non-null `error`.** Transport failures are not results. The
  file holds more lines than the report counts, and that is correct.
- **Folds legacy effort into the model id.** Early records carried the effort only in
  `llm_opts`, so groups would split without this.
- **Applies the 900s model-time budget retroactively.** A run whose
  `llm_time_s + assist_time_s` exceeds `MODEL_TIME_BUDGET_S` is forced to
  `solved: False` at load, so every consumer agrees. `agent.py` also enforces it live
  by refusing to start a turn past the budget.

It defaults to `main.jsonl`. **Do not glob `results/runs/*.jsonl`**: the per-stream
sweep files were merged into main long ago and are gitignored, and globbing them made
the markdown reporter count 8,440 runs against 7,338 real ones.

## Invariants that must not drift

- **An attempt is a submission, not a turn.** Thinking, extra assistant turns and
  documentation lookups are free, because they never reach the user. Only code that
  arrives broken costs. Some models emit several `submit` calls in one turn, which a
  turn count would hide.
- **The anchors in `SCI_SPEC` are fixed constants**, not percentiles of the current
  field. That is what lets a new model join without moving anyone else's score. Never
  replace them with anything data-derived.
- **`sci.index_ci()` is the only interval estimator.** `html_report`, `status` and
  `audit` all call it. Two independent bootstraps once disagreed in the second digit
  for the same model, which is worse than publishing no interval at all.
- **`leaderboard()` picks a model's best variant by measurement.** Within
  `TIE_POINTS = 0.5` *and* overlapping intervals it prefers the variant with more runs.
  Loosening either half of that condition has been tried and broke things: overlap
  alone pulled five models down to deeper-but-worse cells.
- **`active_models()` is the gate for anything that selects models**, including ad-hoc
  sweep scripts, not just charts. A deprecated model must produce no report rows, no
  charts and **no new runs**. A report-only flag once left sweeps quietly spending
  money on models that had been dropped.
- **The local-inference class is derived, never hand-set.** `fits_locally()` asks
  whether a model's **published `Q4_K_M` file** fits `LOCAL_VRAM_GB` minus the reserve.
  Sizes come from the `gguf` block in `model_meta.json`, snapshotted from real repos;
  `LOCAL_FALLBACK_BITS` only covers models with no GGUF. Do not go back to computing
  from a bit width: it understated every large model by ~10% and was wrong by 2x for
  gpt-oss-120b, which ships native MXFP4 and weighs the same at every quant. Moving the
  constants moves models between report sections, so treat it as an editorial change
  and re-read the prose in the sections it feeds.
- **v2.1 and v3 scores are not comparable.** If the weights or the decay change again,
  bump the version in `SCI_SPEC` and say so in the report.

## Adding runs

Model specs carry the effort: `moonshotai/kimi-k3@high`. The full spec is the identity
used for resume, results and report grouping, so `x@low` and `x@high` are different
models as far as everything downstream is concerned. A bare spec inherits
`--reasoning`; `@none` sends no reasoning param at all.

```bash
uv run python -m bench.runner --models qwen/qwen3.6-27b@low,qwen/qwen3.6-27b@high \
  --conditions baseline --adaptive-reps --provider-sort throughput \
  --out results/runs/sweep-qwen.jsonl --rep-offset 3
```

- **Write each sweep to its own `--out` file.** The default is `runs.jsonl`, not
  `main.jsonl`, on purpose: a sweep that goes wrong should not touch the dataset.
- `--adaptive-reps` runs 2 reps per cell and a third only where those two disagree on
  `solved`, which costs about 30% less than `--reps 3` and leaves no 1-1 ties to
  interpret. Prefer it for exploratory sweeps; use explicit `--reps` when topping up a
  cell to a precision target.
- **Use `--rep-offset` past the highest existing rep** for a model already in
  `main.jsonl`. Rep numbering restarts per output file, so without it the merge
  collides on the identity tuple and you get two different runs claiming to be rep 1.
- **No merge tool ships here.** Append the sweep file into `main.jsonl`, dedupe on
  `(task, model, condition, rep)`, treat an identical row as already-merged and a
  same-key-different-content row as a collision to investigate, then run `bench.audit`.
- `--provider-order <slug>` pins routing. Needed where a model's encrypted reasoning
  blocks do not validate across a provider's two endpoints; a mid-run failover then
  produces errors that look like model failures.
- `--concurrency` defaults to 20. The suite is dominated by LLM latency, and
  `workspace` already caps concurrent builds at cores−2, so wide concurrency is close
  to free for baseline batches. **Lower it for MCP-condition batches**: documentation
  lookups queue on a single local backend, that wait counts toward the 900s model-time
  budget and toward the speed component, so a crowded backend manufactures both
  failures and a bad speed score.

## Effort ladders lie, in both directions

OpenRouter publishes `supported_efforts` per model. Treat it as a hint:

- **Optimistic**: a model can advertise a tier its provider rejects outright. One
  advertises six efforts, and two of them return a server error on every request while
  a neighbouring tier works in the same minute.
- **Incomplete**: requested tiers are silently coerced. Four of GLM 5.2's tiers all
  land within a few hundred median output tokens of each other, which means they are
  one effective level and the wiggle between them is sampling noise.

So probe before benchmarking, and compare median output tokens per tier to find out
which levels are real. **Never label a variant "default"** in any output: find the
effort the provider's default maps to and name that.

## The report gates its own build

`assert_output_is_portable()` runs before the file is written and raises on three
things, each of which shipped a broken report first:

- **No `<meta charset="utf-8">` in the first 1024 bytes.** A browser opening `file://`
  has no Content-Type to consult and guesses a codepage, so every multi-byte character
  becomes mojibake on the reader's machine while looking fine here.
- **Non-ASCII text inside chart SVG.** This machine's fonts are not the reader's, so a
  symbol that renders here can arrive as a box there. Symbols in charts are drawn as
  polygons or paths, never typed.
- **Angled labels running off the left edge**, via `angled_labels_overhanging()`. A
  label reaches `width * cos(LABEL_ANGLE)` left of its column centre.

Two helpers keep charts consistent rather than gating them:

- `rotated_label_pad()` derives bottom padding from the actual label set. Every
  hardcoded padding in that file has been wrong at least once, and because labels
  rotate anticlockwise the clipping eats the *first* characters, which reads like a
  font bug rather than a geometry bug.
- `LABEL_ANGLE = 55` and `AXIS_PAD_L = 64` are shared across charts deliberately, so
  they stay visually consistent. Change them in one place or not at all.

For anything visual, run `bench.screenshot` and **look at the PNGs** before committing.
Text and geometry checks have passed things that were plainly ugly on screen. The hook
that blocks a commit while the screenshots are stale lives in `.claude/settings.json`,
which is untracked, so a fresh clone gets the script but not the enforcement.

## Conventions

- `bench.audit` is the release gate. It checks the report *and* the top-5 table in
  `README.md`, so if a sweep moves a score, the README fails loudly instead of quietly
  contradicting the report.
- `results/report.html` is generated locally. Publishing it anywhere is a manual,
  explicitly-requested step, never a side effect of rebuilding.
- Report and README prose: no em dashes, and short paragraphs rather than walls.
- When a claim rests on a gap between two numbers, check the gap against the interval
  first. Adjacent scores here are usually closer together than their intervals, so an
  ordering that looks like a ranking is often a tie, and the prose should say so.

## Environment

Python via `uv` (`uv sync`), no package install needed. The Cairo toolchain is Scarb
2.19.4, Starknet Foundry 0.62.1 and universal-sierra-compiler 2.9.1, installed with
[starkup](https://github.com/software-mansion/starkup). `SCARB_VERSION` and
`SNFORGE_VERSION` in `bench/config.py` are not enforced against the installed
binaries: they are interpolated into the system prompt, so a model is told which
toolchain it is writing for. Changing the installed versions without changing those
constants silently lies to the model.

`OPENROUTER_API_KEY` is the credential for every model call; `bench/config.py` reads it
from the environment. `CAIRO_CODER_API_KEY` is sent as `x-api-key` by
`bench/cairo_coder.py` and only matters against the hosted documentation API, which is
sunset; a local backend ignores it.

MCP-condition runs need a Cairo Coder backend reachable at `CAIRO_CODER_URL`
(default `http://localhost:3001/v1/chat/completions`);
the README's self-hosted section has the bring-up. Check it is up before an MCP batch,
and allow a slow first response: a documentation round-trip takes 10 to 20 seconds, so
a short curl timeout makes a healthy backend look dead.
