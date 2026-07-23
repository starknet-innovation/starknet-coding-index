# Cairo Coder MCP Benchmark

Measures whether the [Cairo Coder](https://www.cairo-coder.com/) MCP tool improves LLM
performance on Starknet smart-contract tasks, in **effectiveness** (hidden `snforge`
tests passing) and **efficiency** (wall time, tokens, dollar cost, repair iterations).

## Design

Each run = `task × model × condition × rep`. The model gets a task spec and must
produce `src/lib.cairo` for a fixed Scarb package. It iterates in an agentic repair
loop: submit code → harness runs `scarb build` + `snforge test` → model sees the
results → resubmits, within a budget of 10 turns AND 15 minutes of model time
(LLM streaming + doc-tool wait — not wall time, which depends on harness
concurrency). Over budget = failed, enforced live by the agent loop and
retroactively in scoring.

Two conditions, identical in every way except tool availability:

- **baseline** — tools: `submit(code)`
- **mcp** — tools: `submit(code)` + `assist_with_cairo(query, codeSnippets?, history?)`

`assist_with_cairo` replicates the `@kasarlabs/cairo-coder-mcp` package exactly
(same tool name/description/schema, same request template and headers against
`api.cairo-coder.com`), without the stdio process overhead.

## Layout

- `tasks/<id>/` — task package: `prompt.md` (spec shown to model), `Scarb.toml`,
  stub `src/lib.cairo`, hidden `tests/`, reference `solution/lib.cairo`
- `bench/` — Python harness (see `bench/README` docstrings): runner, agent loop,
  OpenRouter client, workspace executor, task validator, report generator
- `results/runs/*.jsonl` — one record per run, append-only, resumable
- `results/report.md` / `report.html` — aggregated results

## Toolchain (pinned)

Scarb 2.19.4 (Cairo 2.19.4), Starknet Foundry 0.62.1, universal-sierra-compiler 2.9.1
— installed via [starkup](https://github.com/software-mansion/starkup).

## Running

```bash
export OPENROUTER_API_KEY=... CAIRO_CODER_API_KEY=...
uv run python -m bench.validate_tasks            # gate: solutions pass, stubs fail
uv run python -m bench.runner --models <spec,...> --conditions baseline,mcp --reps 1
uv run python -m bench.report          # markdown tables -> results/report.md
uv run python -m bench.html_report     # visual report  -> results/report.html
```

`results/report.html` is self-contained (inline SVG charts, no JS/external
assets) and structured overview-first: hero verdict, difficulty-impact chart,
effort curve, efficiency frontier, then detail tables and methodology.
It is generated locally only — publishing it anywhere is a manual,
explicitly-requested step.

Model specs attach a per-model reasoning effort with `@` — mix efforts and
non-reasoning models freely in one matrix:

```bash
--models z-ai/glm-5.2@high,z-ai/glm-5.2@low,moonshotai/kimi-k3
```

A bare spec inherits `--reasoning` (if given) as its default; `@none` forces
no reasoning param. OpenRouter variant suffixes (`:free`, `:nitro`) are part
of the model id and pass through. The full spec is the identity used for
resume, results, and report grouping.

## Starknet Coding Index (SCI)

One composite score per model for "how good is this LLM at Starknet contracts":
`SCI = 0.50*Correctness + 0.15*OneShot + 0.15*Speed + 0.15*Cost + 0.05*TokenEff`,
computed by `bench/sci.py` (weights + fixed log anchors versioned in `SCI_SPEC`,
currently v2). Speed scores median **model latency** (`llm_time_s`, anchors
10s→1200s) — not wall time, which includes local compile/test that scales with
runner concurrency and says nothing about the model. Print the leaderboard with
`uv run python -m bench.sci`.

**Adding a model** (budget-aware protocol):

1. **Bracket sweep** — probe the effort ladder, then benchmark only the bracket
   tiers first: the lowest real mode (`@disabled` if honored, else `@minimal`),
   `@low`, and `@high`, with `--adaptive-reps` (2 reps per cell + a tiebreaker
   third only where they disagree on solved — ~30% cheaper than `--reps 3`,
   no uninterpretable 1–1 ties):
   `uv run python -m bench.runner --models <spec@tiers> --provider-sort throughput
   --conditions baseline --adaptive-reps`
2. **Extend toward the winner only** — if `@high` wins the bracket, add
   `@xhigh`/`@max`; if the bottom wins, stop. Pro-style serving modes only on
   explicit request (strictly dominated in every measurement so far).
3. Add one entry to `MODEL_REGISTRY` in `bench/sci.py` (specs, label, lab,
   open_weight), regenerate the report. Fixed anchors guarantee existing
   scores don't move.

Beware effort-ladder lies: probe before benchmarking (some models accept
`disabled` and think anyway; some bare specs map to an unnameable dynamic
level — never label a variant "default").

## Self-hosted Cairo Coder (hosted API sunset 2026-07-31)

The hosted api.cairo-coder.com is quota-limited and being sunset, so the MCP
backend can run entirely locally in `vendor/cairo-coder` (gitignored clone of
KasarLabs/cairo-coder; our modifications are tracked in
`vendor/patches/openrouter-routing.diff`). OpenRouter is the only external AI
dependency — same models as production: `google/gemini-embedding-001` for
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
indexing / base64 encoding_format) — both sides use direct OpenAI-SDK/fetch
clients with `encoding_format: float` instead.
