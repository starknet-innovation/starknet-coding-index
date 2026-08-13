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
| `bench/report.py` | `load_runs()`, the single loader every consumer shares |
| `bench/audit.py` | re-checks every published figure against the data; exits non-zero on drift |
| `bench/status.py` | live progress of a sweep: runs done vs needed, intervals, spend |
| `bench/screenshot.py` | regenerates the report and shoots every section at two widths to `results/shots/` |
| `bench/validate_tasks.py` | gate for task packages: reference solution passes, stub fails |
| `tasks/<id>/` | `prompt.md`, `Scarb.toml`, stub `src/lib.cairo`, hidden `tests/`, `solution/lib.cairo` |
| `results/runs/main.jsonl` | the dataset, one JSON object per run, append-only, **no transcripts** |
| `results/runs/main.full.jsonl` | local-only archive: the same runs WITH transcripts and submitted code |
| `results/runs/sweeps.json` | which sweep file produced which runs; the only thing pruning destroys |
| `results/runs/unmerged.jsonl` | local-only: attempts the dataset never took (transport errors, probes) |

The constants most changes start from, because none of them live where you would look
for them first:

| Constant | Where | Moves |
|---|---|---|
| `CHART_TOP_N` | `bench/sci.py` | how many models the headline charts draw |
| `LABEL_ANGLE`, `AXIS_PAD_L` | `bench/html_report.py` | angled axis labels, every chart at once |
| `LOCAL_VRAM_GB`, `LOCAL_RESERVE_GB`, `LOCAL_QUANT` | `bench/sci.py` | who is in the local-inference class |
| `SCI_SPEC` | `bench/sci.py` | the index itself |
| `MODEL_TIME_BUDGET_S` | `bench/config.py` | the run budget, enforced live and at load |

A `leaderboard()` row is the registry entry merged with the winning variant's scores, so
it already carries what a caller usually recomputes: `label`, `lab`, `spec`, `variant`,
`sci`, `n`, `ci`, `open_weight`, `weights_pending`, `local`, `vram_gb`. Read the row
before reaching for `fits_locally()` or `model_meta.json`.

## Toolchain

`Dockerfile` at the repo root is both a Docker Sandbox template base and the dependency
list; `SANDBOX.md` is the operator runbook for standing up a sandbox from it. Build it, then either push and `sbx run --template <ref> claude`, or
`docker image save … | sbx template load`.

It extends `docker/sandbox-templates:claude-code-docker`, and the `-docker` suffix is
load-bearing: that variant ships the in-sandbox Docker daemon, which the MCP condition
needs to run the pgvector container holding the embedded corpus. The plain `claude-code`
variant has the CLI but no daemon, so a sandbox built on it passes every benchmark gate
and then fails at the `docker run` in the MCP restore. The `sbx run` agent argument is
`claude` for both.

| Tool | Pin | Why it is pinned |
|---|---|---|
| `scarb` | 2.19.4 | compiles every submitted contract. A different compiler is a different benchmark |
| `snforge` | 0.62.1 | runs the hidden tests, same reasoning |
| Python | 3.12 | one interpreter for the benchmark AND the vendored service, which pins `psycopg2==2.9.10` (no wheel above 3.12). Pinned by us so a base-image bump cannot change the interpreter under the experiment. Verified identical scores and intervals against 3.14, since `index_ci` seeds `random.Random(0)` |
| `playwright` | 1.61.0 | ties to browser build chromium-1228, which every screenshot was taken with |
| `bun`, `mdbook`, `antora` | 1.3.14, 0.4.52, 3.1.15 | corpus ingestion only. The ingester shells out to `mdbook` and to `antora`; mdbook is held at 0.4.x because 0.5 breaks the cairo-book theme |

**The Python environment lives outside the repo**, at `/home/agent/.venv-sci` via
`UV_PROJECT_ENVIRONMENT`. The workspace is a bind mount, so anything the image writes to
`<repo>/.venv` is masked at run time; keeping it in `$HOME` also means renaming the
project no longer breaks it. `uv run …` picks it up with no `uv sync` step.

### Restoring the MCP condition after a rebuild

The embedded corpus is **not** in the image. It is a PostgreSQL data directory inside the
workspace, so it travels with the project:

```bash
docker run -d --name postgres -p 5455:5432 --env-file vendor/cairo-coder/.env \
  -v "$PWD/vendor/cairo-coder/data:/var/lib/postgresql/data" pgvector/pgvector:pg17
cd vendor/cairo-coder/python && uv sync --python 3.12 && uv run cairo-coder   # detached
curl -m 60 -X POST localhost:3001/v1/chat/completions -d '{"messages":[{"role":"user","content":"ping"}]}'
```

The tag must stay **pg17** (a data directory is not readable by another major version) and
the bind path must be the same directory. The health check keeps a 60s timeout: a RAG
round trip takes 6 to 20 seconds and a short timeout makes a healthy service look dead.

`docker compose up -d postgres` from `vendor/cairo-coder` does the same thing, since the
compose file already declares that bind mount. Four traps, each of which cost time:

- **Bring up `postgres` only, never `postgres backend`.** The backend service builds from
  `backend.dockerfile`, whose `apt-get` step cannot reach the network from inside a docker
  build here, so the build fails and takes the whole `up` down with it. The backend runs
  natively instead, which is what the commands above do.
- **An empty `docker volume ls` is not a missing corpus.** The data is a bind mount at
  `vendor/cairo-coder/data` (~196 MB), not a named volume, so it never appears in the
  volume list. Check the corpus itself instead, which should say 4,105:
  `docker exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select count(*) from documents;"'`
- **Give the backend its own venv.** If `UV_PROJECT_ENVIRONMENT` is set, both projects
  resolve to that one directory and `uv sync` here silently downgrades the bench project's
  `openai`, which then fails mid-run with `cannot import name 'path_template'`. Run the
  backend under `UV_PROJECT_ENVIRONMENT=~/.venv-cairo-coder` and leave the bench venv alone.
- **`pkill -f` and `pgrep -f` match the command doing the matching.** Its own command line
  contains the pattern, so `pkill -f cairo-coder` kills the shell running it (exit 144)
  while the backend keeps serving, and `until ! pgrep -f bench.runner; do sleep 10; done`
  never exits because the waiter matches itself, leaking a shell for the session. Bracket a
  character so the pattern cannot match literally (`pgrep -f "[b]ench.runner"`), or watch a
  pid or port instead of a name.

To refresh the corpus with newer documentation:

```bash
cd vendor/cairo-coder/ingesters && bun install && bun run generate-embeddings:yes
```

The full corpus is 4,105 chunks across 11 sources, roughly $0.42 of embedding spend
through OpenRouter, which needs `encoding_format: "float"` because its base64 default
returns empty vectors.

## Commands

```bash
uv run python -m bench.html_report     # rebuild results/report.html
uv run python -m bench.audit           # release gate: every published figure, exit 1 on drift
uv run python -m bench.sci             # the leaderboard, per model and variant
uv run python -m bench.status          # per-model intervals vs the precision target (--watch)
uv run python -m bench.screenshot      # regen + shoot every section, desktop and phone (visual QA)
uv run python -m bench.validate_tasks  # solutions pass, stubs fail
uv run python -m bench.prune_runs      # delete merged sweep files (dry run; --apply to act)
uv run python -m bench.runner --models <spec,...> --conditions baseline,mcp --reps 1
```

Only `runner` spends money on model APIs. Everything else is local, and the first four
touch nothing but `results/`.

## Try the change before making it

`html_report.build(runs)` is pure. It returns the HTML string and writes nothing; only
`main()` writes `results/report.html`. So anything that moves the roster or the chart
geometry can be tested against the real data before a single file is edited:

```python
import bench.html_report as H
from bench import config
runs = H.load_runs([config.RUNS_DIR / "main.jsonl"])
H.CHART_TOP_N = 15                         # the module-level name build() reads
html = H.build(runs)                       # nothing written
print(H.angled_labels_overhanging(html))   # [] means the label guard passes
H.assert_output_is_portable(html)          # and the rest of the build gates
```

Counting labels or grepping prose out of that string answers, up front, which models a
wider cut would draw, what the derived sentences would then say, and which audit claims
would go stale, none of which is obvious from reading the code. Raising `CHART_TOP_N`
from 12 to 15 was verified this way before anything was touched: three entrants, the
label guard still clearing, and one audit check with a typed count that would fail.

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
- **`leaderboard()` picks a model's highest-SCI variant, no tie rule.** Decided
  2026-08-05, replacing the TIE_POINTS rule: a winner label can flip on noise
  between refreshes when adjacent cells sit hundredths apart; the published
  intervals carry the uncertainty story.
- **`active_models()` is the gate for anything that selects models**, including ad-hoc
  sweep scripts, not just charts. A deprecated model must produce no report rows, no
  charts and **no new runs**. A report-only flag once left sweeps quietly spending
  money on models that had been dropped.
- **Deprecation is total: it reaches the counts too, via `active_runs()`.** A retired model
  contributes nothing a reader can see, including the run total. `html_report.main()` and
  `audit.py` both wrap the loader in `active_runs()` so `build()` never sees a retired run
  and no single figure can leak one; the archive parity check is the one deliberate
  exception, because it counts raw lines in `main.jsonl` against `main.full.jsonl` and the
  records stay in both. `bench.status` also stays raw: money spent on a since-retired model
  was still spent. The audit pins the whole arithmetic in one equation, published + errors
  + retired == lines in the file, and separately asserts no retired label appears anywhere
  in the report.
- **Retiring a model can strand prose that never named it.** Deprecating Grok 4.5 left the
  Sol FAQ card claiming "nine times Grok's bill", a multiple computed from 4.5 that no
  remaining model produced, and the dial's "five tiers land within 3 points" pointing at a
  chart that no longer drew it. Neither failed: their checks read `main.jsonl`, where the
  runs still exist. **After deprecating anything, grep the shipped report for the label AND
  for claims derived from it**, and prefer deriving such prose from the leaderboard so the
  next retirement fixes itself.
- **The headline charts draw the top `CHART_TOP_N` (15) by index.** The index chart, the
  three in "Behind the score" and the dial all take `chart_rows = sci_rows[:CHART_TOP_N]`,
  ranked on the **baseline** score, because they answer "how good is this model on its
  own". `bench.audit` reads the shipped SVG back and checks that each drew exactly those
  models, because a chart built from the wrong row set still renders perfectly. Models
  below the cut keep their table rows and their findings; the ones that also run locally
  are charted in the local-inference section. Moving the cut moves label geometry with it
  (see `AXIS_PAD_L`) and changes which models are charted only in the local section, which
  the audit reads back out of that section's own sentence rather than holding a count of
  its own.
- **The MCP lift chart is the one exception, and ranks by `max(baseline, mcp)`.** Its
  membership is `lift_rows`, not `chart_rows`. Selecting it on the baseline score meant the
  chart about the documentation tool cut the models the tool transforms: DeepSeek V4 Pro
  0813 sits 17th alone and 13th with the tool, and being closed it had no local-inference
  chart to fall back on, so a +12.8 lift appeared nowhere but a table cell. Its own audit
  check recomputes the best-of-either set and reads the shipped SVG back.
  **`build_lift_pairs` must still receive rows in baseline order.** It takes each model's
  rank from the order it is given, re-sorts by `max(base, mcp)` internally, and prints the
  difference as the green rank-delta arrows; pass it rows already sorted by best-of-either
  and every delta is zero and the arrows disappear with nothing failing.
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
- **No merge tool ships here, and a merge has TWO destinations.** Append the sweep file
  into **`main.full.jsonl` in full**, and into **`main.jsonl` with `transcript` and
  `final_code` removed**. Dedupe both on `(task, model, condition, rep)`, treat an
  identical row as already-merged and a same-key-different-content row as a collision to
  investigate, then run `bench.audit`.
  **Appending a sweep file verbatim to `main.jsonl` publishes the transcripts.** It
  happened twice (DeepSeek V4 Flash, Qwen3.8 Max), put 20.8 MB of transcripts and
  submitted code into the tracked dataset and then into git history, and needed a
  history rewrite to undo. `bench.audit` now fails if any tracked record carries either
  field, and if the two files hold different numbers of records.
- **Then delete the sweep file: `uv run python -m bench.prune_runs --apply`.** Once merged
  it is pure duplication; 27 of them had reached 195 MB. The tool accounts for every
  record before removing anything, refuses to delete a file it cannot explain, records
  which sweep produced which runs in `results/runs/sweeps.json` (the only thing deletion
  destroys), and rescues records the dataset never took into `unmerged.jsonl` (transport
  errors, which `load_runs` drops, and probe runs). Harness dry-runs against `fake/model`
  are discarded, being regenerable.
- `--provider-order <slug>` pins routing. Needed where a model's encrypted reasoning
  blocks do not validate across a provider's two endpoints; a mid-run failover then
  produces errors that look like model failures.
- `--concurrency` defaults to 20. The suite is dominated by LLM latency, and
  `workspace` already caps concurrent builds at cores−2 (`MAX_CONCURRENT_BUILDS`), so wide
  concurrency is close to free for baseline batches. 32 is fine and 89 runs at that width
  drew zero retries; past roughly one wave of work it buys nothing, since the first
  adaptive pass is only tasks × tiers × 2 cells.
- **Why width cannot corrupt a baseline batch, which is the part worth knowing.** Driving a
  single endpoint hard risks 429s, and `RETRIABLE_STATUS` retries them five times with
  `min(60, 2**attempt)` backoff. That backoff never reaches the score: `models.py` resets
  `start = time.monotonic()` **inside** the retry loop and takes `latency_s` on the
  succeeding attempt, so a throttled call costs wall clock and nothing else. It cannot push
  a run past the 900s budget. The measured cost is only throughput: 84 tok/s per call at 32
  wide against 95 tok/s at 1-2 wide, about 12%, checked by comparing the same task and tier
  across a probe and a sweep.
- **Lower it for MCP-condition batches**, 6 to 8: documentation lookups queue on a single
  local backend, and unlike retry backoff that wait **is** counted, because `load_runs()`
  applies the budget to `llm_time_s + assist_time_s`. A crowded backend manufactures both
  failures and a bad speed score. At 6 the assist share held at 10-11% of model time across
  82 runs, so it never came close to deciding an outcome; `assist_time_s` is in every record,
  so check it rather than assuming.

## Authoring a task package

`bench.validate_tasks` is the gate: every reference solution must pass its hidden tests
and every stub must fail. Three Cairo 2.19 details cost real debugging time when the
suite was written, and none of them are obvious from the compiler message:

- **An `Array` derefs to `Span`.** Call `.span()` before `.at()` or `.len()` in tests.
- **`get_events` needs the `EventSpyTrait` import**, or the spy returns nothing and the
  assertion fails in a way that reads like the contract never emitted.
- **`#[derive(starknet::Store)]`** is required on any struct written to storage; without
  it the error points at the storage member rather than the type.

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

`assert_output_is_portable()` runs before the file is written and raises on five
things, each of which shipped a broken report first:

- **No `<meta charset="utf-8">` in the first 1024 bytes.** A browser opening `file://`
  has no Content-Type to consult and guesses a codepage, so every multi-byte character
  becomes mojibake on the reader's machine while looking fine here.
- **No `<meta name="viewport">`.** Without it a phone lays the page out at 980px and
  scales the whole thing down, which also means every `max-width` media query in the
  stylesheet never fires. The report shipped that way for weeks because visual QA only
  ever ran at 1100px.
- **A chart SVG outside a `.chartwrap`.** Charts scroll on narrow screens rather than
  shrinking: an SVG at `width:100%` will render a 760px chart at 290px, where an 11px
  axis label arrives at 4px. Every chart call site goes through `chart()`.
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
- `audit.section_html()` and `audit.chart_labels()` read the shipped SVG back. Reuse them
  rather than writing a regex: axis labels come in two shapes, a bare rotated `<text>`
  and a rotated `<g>` wrapping the label plus a rank-delta arrow, and a parser that knows
  only the first reports the MCP chart drawing four fewer models than it drew.
- `LABEL_ANGLE = 55` and `AXIS_PAD_L = 98` are shared across charts deliberately, so
  they stay visually consistent. Change them in one place or not at all. `AXIS_PAD_L`
  tracks `CHART_TOP_N` **and the longest label**: more columns are narrower columns, which
  pulls column 0's centre left and eats the clearance an angled label needs, and a longer
  name spills further into it. Renaming a model can therefore break the build, which is
  what raised this from 80 (see the arithmetic above the constant). The one documented
  exception is `sci_bar_chart`, which keeps `pad_l = 64` because it alone draws in rank
  order, so its first label is always the leader's and always short.
- **`pad_l=AXIS_PAD_L` is a default argument**, bound when the module is imported. Setting
  `html_report.AXIS_PAD_L` at runtime changes nothing, so a dry run that tries to test a
  new pad that way silently measures the old one. Patch `fn.__defaults__`, or just edit the
  constant.

For anything visual, run `bench.screenshot` and **look at the PNGs** before committing.
Text and geometry checks have passed things that were plainly ugly on screen. Every
section is shot twice, `NN-*.png` at 1100px and `m-NN-*.png` at 390px, and **both are
the gate**: shooting one width is how a report with no viewport tag at all survived
weeks of visual QA. The hook that blocks a commit while the screenshots are stale lives
in `.claude/settings.json`, which is **tracked** (a `.gitignore` exception), so a clone
gets the enforcement and not just the script. It cannot check that anyone LOOKED at the
PNGs, only that they are newer than the UI files: the mobile layout bug shipped with a
fresh screenshot that showed it.

## Conventions

- `bench.audit` is the release gate. It checks the report *and* the top-5 table in
  `README.md`, so if a sweep moves a score, the README fails loudly instead of quietly
  contradicting the report.
- **Never type a roster count into a check.** `len(only_local) == 6` was true only while
  the roster held still, and moving the cut to 15 broke it, which is not the drift the
  gate exists to catch. Derive the number, or, where the report already derives it, read
  it back out of the shipped sentence and compare that to the data: the local section's
  count works this way, so the prose and the check cannot disagree. Confirm a new check
  fails on a tampered report before trusting it.
- **Prose that counts things has to read at one and at zero.** Counts go through
  `word(len(...))`, and a list that shrinks to one leaves "One of the eight switchers
  *rank* below the cut" while an empty one leaves a parenthetical wrapped around nothing.
  The first of those surfaced in a dry run of the top fifteen and the second is one
  roster change further out. Pluralize off the length, and drop the clause when the list
  is empty rather than printing "Zero of the eight".
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
