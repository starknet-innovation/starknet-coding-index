# Cairo Coder MCP Benchmark

Measures whether the [Cairo Coder](https://www.cairo-coder.com/) MCP tool improves LLM
performance on Starknet smart-contract tasks, in **effectiveness** (hidden `snforge`
tests passing) and **efficiency** (wall time, tokens, dollar cost, repair iterations).

## Design

Each run = `task × model × condition × rep`. The model gets a task spec and must
produce `src/lib.cairo` for a fixed Scarb package. It iterates in an agentic repair
loop: submit code → harness runs `scarb build` + `snforge test` → model sees the
results → resubmits, up to a turn limit.

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
uv run python -m bench.runner --models <id,...> --conditions baseline,mcp --reps 1
uv run python -m bench.report
```

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

Then point the harness at it:

```bash
CAIRO_CODER_URL=http://localhost:3001/v1/chat/completions uv run python -m bench.runner ...
```

Ingestion status: 10/11 sources (3,160 chunks). `starknet_blog` requires
`www.starknet.io:443` on the sandbox network allowlist; rerun
`generate-embeddings:yes` after allowing it (reruns are incremental).
Gotchas encoded in the patch: langchain's `OpenAIEmbeddings` and litellm's
embedding path both mis-handle OpenRouter's embeddings route (positional
indexing / base64 encoding_format) — both sides use direct OpenAI-SDK/fetch
clients with `encoding_format: float` instead.
