# The Starknet Coding Index

How good is each frontier LLM at writing Starknet smart contracts on its own, and which
models get better when you hand them a Cairo documentation tool?

This repository is the benchmark behind both answers: 22 models from 12 labs, **7,862
agentic runs** on 13 hand-written contract tasks, graded by 106 hidden `snforge` tests.
Every model ran the suite both ways, alone and with the
[Cairo Coder](https://www.cairo-coder.com/) MCP documentation tool.

The finished report is [`results/report.html`](results/report.html): self-contained,
no JavaScript, generated from the data in this repo.

## Results

The index scores the **baseline** condition, each model at its best setting, no
documentation tool:

| # | Model | Setting | SCI | Solved on first submission |
|---|-------|---------|-----|----------------------------|
| 1 | Opus 5 | low | 92.0 ±0.7 | 100% |
| 2 | Fable 5 | xhigh | 89.3 ±1.2 | 100% |
| 3 | Grok 4.5 | medium | 88.3 ±3.8 | 75% |
| 4 | Sonnet 5 | high | 83.4 ±4.3 | 67% |
| 5 | Kimi K3 | max | 83.1 ±3.0 | 87% |

Intervals are bootstrapped over each model's runs (1,000 resamples). Opus 5 separates
from every model below it except Grok 4.5; Fable 5 separates from ranks 4 and 5, while
Grok's wide interval overlaps the whole band. Read overlapping pairs as ties, not an order.

All 22 models, the difficulty breakdown and the documentation-tool deltas are in the
report. To print the full leaderboard yourself:

```bash
uv run python -m bench.sci
```

## The index

One composite score per model for "how good is this LLM at Starknet contracts":
`SCI = 0.50*Effectiveness + 0.25*Correctness + 0.15*Cost + 0.10*Time`,
computed by `bench/sci.py` (weights, decay and fixed log anchors versioned in
`SCI_SPEC`, currently **v3**).

- **Effectiveness** is the point of the index: does the model deliver working
  code without sending the human back into the loop? Per run, `0` if unsolved or
  over budget, else `100 * 0.4**(submissions-1)`, so 1/2/3/4 submissions score
  100/40/16/6. **An attempt is a submission, not a turn**: thinking, extra
  assistant turns and documentation lookups never reach the user and are free;
  only code that arrives broken costs, because that is when a person has to read
  the output and re-prompt. Some models emit several `submit` calls in one turn,
  which this counts correctly and a turn count would hide.
- **Correctness** is per-test partial credit on the delivered code. 90% of tests
  passing is still broken, but it separates "nearly worked" from "garbage".
- **Cost/Time** use median $ per task and median **model latency**
  (`llm_time_s`, anchors 10s to 1200s), not wall time, which includes local
  compile/test that scales with runner concurrency and says nothing about the
  model.

v2.1 to v3 (2026-07-25): v2.1 weighted correctness at 50% with a binary one-shot
bonus, so a model that ground out a fix over ten turns of privileged
failing-test feedback scored nearly as well as one that got it right first try.
Real users have no hidden test suite: they prompt, compile, and ship. Scores are
**not comparable across the v2.1 boundary**.

## How a run works

Each run = `task × model × condition × rep`. The model gets a task spec and must
produce `src/lib.cairo` for a fixed Scarb package. It iterates in an agentic repair
loop: submit code, the harness runs `scarb build` + `snforge test`, the model sees the
results (raw compiler errors and failing-test output, never the test code itself) and
resubmits, within a budget of 10 turns AND 15 minutes of model time (LLM streaming plus
doc-tool wait, not wall time, which depends on harness concurrency). Over budget counts
as failed, enforced live by the agent loop and retroactively in scoring.

## Does documentation access help?

That is the second question, and the answer differs sharply by model. Two conditions,
identical in every way except tool availability:

- **baseline** — tools: `submit(code)`
- **mcp** — tools: `submit(code)` + `assist_with_cairo(query, codeSnippets?, history?)`

`assist_with_cairo` replicates the `@kasarlabs/cairo-coder-mcp` package exactly
(same tool name/description/schema, same request template and headers), so the
comparison is against the tool developers actually install, not an idealised
version of it. Per-model deltas are charted in the report.

## Layout

- `tasks/<id>/` — task package: `prompt.md` (spec shown to model), `Scarb.toml`,
  stub `src/lib.cairo`, hidden `tests/`, reference `solution/lib.cairo`
- `bench/` — Python harness (each module's docstring says how to run it): runner, agent loop,
  OpenRouter client, workspace executor, task validator, report generator
- `results/runs/main.jsonl` — one record per run, append-only, resumable
- `results/report.html` — the report, charts included
- `bench/audit.py` — re-checks every number quoted in the report against the data

## Published data

`results/runs/main.jsonl` holds 7,910 records, the 7,862 analysed runs plus 48 that
hit a transport error and are dropped at load. It is the only input the report and the
audit need:

```
model condition task rep          what was run
solved compiled tests_passed      outcome
n_submissions turns               how many times code was delivered, and turns taken
llm_time_s assist_time_s          model latency, and doc-tool wait
cost_usd completion_tokens        OpenRouter-reported cost, output tokens
submissions[] llm_calls[]         per-submission results, per-call latency
assist_calls[] n_assist_calls     documentation lookups
over_time_budget error            budget breach, transport failure
```

Two fields are **not** published: `transcript` (the full conversation) and
`final_code` (the submitted Cairo). They were 88.7% and 7.4% of each record, 640 MB
of the original 655, and nothing in `bench/` reads either. Dropping them leaves every
published number reproducible bit-for-bit, which is checked below. If you need to see
what a model actually wrote, the harness records both, so re-running a cell locally
regenerates them.

Per-stream files from the sweeps (`gap-*`, `ladder-*`, `topup*`) are not tracked
either: they were merged into `main.jsonl` and keeping them would double-count.

## Reproducing the report

```bash
uv run python -m bench.html_report     # rebuilds results/report.html from main.jsonl
uv run python -m bench.audit           # every figure in the report, and this README's table
uv run python -m bench.sci             # the index, per model and variant
uv run python -m bench.status          # per-model confidence intervals vs the target
```

`bench.audit` exits non-zero if any published figure stops matching the data, so it
works as a release gate. `bench.html_report` also refuses to write a report whose
charts contain non-ASCII text or labels that would run off an edge.

Everything the project needs is in the root **`Dockerfile`**, which doubles as the
dependency list: Python 3.12, `scarb` 2.19.4 and `snforge` 0.62.1 (the toolchain that
compiles and tests every submission, so the versions are part of the experiment), and
Playwright's Chromium for the visual checks. `docker build` it to get a working
environment, or read it to see what to install by hand.

## Running the benchmark

```bash
export OPENROUTER_API_KEY=... CAIRO_CODER_API_KEY=...
uv run python -m bench.validate_tasks            # gate: solutions pass, stubs fail
uv run python -m bench.runner --models <spec,...> --conditions baseline,mcp --reps 1
uv run python -m bench.html_report     # the report -> results/report.html
```

`results/report.html` is structured overview-first: hero verdict, difficulty-impact
chart, efficiency frontier, then detail tables and methodology. It is
generated locally only; publishing it anywhere is a manual, explicitly-requested step.

Model specs attach a per-model reasoning effort with `@`, so efforts and
non-reasoning models mix freely in one matrix:

```bash
--models z-ai/glm-5.2@high,z-ai/glm-5.2@low,moonshotai/kimi-k3
```

A bare spec inherits `--reasoning` (if given) as its default; `@none` forces
no reasoning param. OpenRouter variant suffixes (`:free`, `:nitro`) are part
of the model id and pass through. The full spec is the identity used for
resume, results, and report grouping.

### Adding a model (budget-aware protocol)

1. **Bracket sweep** — probe the effort ladder, then benchmark only the bracket
   tiers first: the lowest real mode (`@disabled` if honored, else `@minimal`),
   `@low`, and `@high`, with `--adaptive-reps` (2 reps per cell plus a tiebreaker
   third only where they disagree on solved, about 30% cheaper than `--reps 3`,
   with no uninterpretable 1–1 ties):
   `uv run python -m bench.runner --models <spec@tiers> --provider-sort throughput
   --conditions baseline --adaptive-reps`
2. **Extend toward the winner only** — if `@high` wins the bracket, add
   `@xhigh`/`@max`; if the bottom wins, stop. Pro-style serving modes only on
   explicit request (strictly dominated in every measurement so far).
3. Add one entry to `MODEL_REGISTRY` in `bench/sci.py` (specs, label, lab,
   open_weight), regenerate the report. Fixed anchors guarantee existing
   scores don't move.

Beware effort-ladder lies: probe before benchmarking. Some models accept
`disabled` and think anyway, some advertise tiers their provider then rejects, and
some bare specs map to an unnameable dynamic level, so never label a variant
"default".

## A note on contamination

The hidden tests are in this repository, so they are public from the moment it is.
Any model trained after this release may have seen them, which makes those scores
untrustworthy for models newer than the snapshot date in the report footer. That is
the cost of an auditable benchmark, and the alternative, asking readers to trust
unpublished tests, is worse. If you want a clean comparison for a newer model,
write fresh tasks in the same shape; `bench.validate_tasks` gates them (reference
solution must pass, stub must fail).

## Toolchain (pinned)

Scarb 2.19.4 (Cairo 2.19.4), Starknet Foundry 0.62.1, universal-sierra-compiler 2.9.1,
installed via [starkup](https://github.com/software-mansion/starkup).

## Self-hosted Cairo Coder (hosted API sunset 2026-07-31)

The hosted api.cairo-coder.com is quota-limited and being sunset, so the MCP
backend can run entirely locally in `vendor/cairo-coder` (gitignored clone of
KasarLabs/cairo-coder; our modifications are tracked in
`vendor/patches/openrouter-routing.diff`). OpenRouter is the only external AI
dependency, and the models match production: `google/gemini-embedding-001` for
embeddings, `google/gemini-3-flash-preview` for generation.

Bring-up (from `vendor/cairo-coder`):

```bash
git apply ../patches/openrouter-routing.diff     # if starting from a fresh clone
docker compose up -d postgres                    # pgvector on :5455
cd ingesters && bun install && bun run generate-embeddings:yes   # needs mdbook 0.4.x + antora on PATH
cd ../python && uv sync --python 3.12
set -a && source ../.env && set +a && uv run cairo-coder         # serves :3001
```

The harness targets it by default (`bench/config.py` points at
`http://localhost:3001/v1/chat/completions`); just make sure the backend is
running before MCP-condition runs.

Ingestion status: **11/11 sources, 4,105 chunks** (complete corpus parity with
the hosted service). Reruns of `generate-embeddings:yes` are incremental
(hash-compared per chunk). Network note: `starknet_blog` crawls
`www.starknet.io`, which must be on the sandbox allowlist.
Gotchas encoded in the patch: langchain's `OpenAIEmbeddings` and litellm's
embedding path both mis-handle OpenRouter's embeddings route (positional
indexing / base64 encoding_format), so both sides use direct OpenAI-SDK/fetch
clients with `encoding_format: float` instead.
