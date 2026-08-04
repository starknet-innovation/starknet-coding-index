# Standing up a new sandbox for this project

The operator's runbook: how to go from the committed `Dockerfile` to a working Docker
Sandbox, and how to carry over the one thing a recreate destroys. Written for the host
(your Mac); the last two sections run inside the new sandbox.

Provenance note: every command here except the `sbx …` ones was executed and verified
from inside a container built from this Dockerfile. The `sbx` commands are quoted from
Docker's published sandbox docs, because `sbx` is a host-side CLI that cannot run inside
a sandbox.

## 0. Before destroying the old sandbox (host + old sandbox)

The repo, the run archive, the embedded corpus and the `.claude/settings.json` hooks all
live in the workspace folder and survive anything. What does **not** survive is the
agent's memory: Claude Code keys it by project path under
`/home/agent/.claude/projects/<key>/memory/`, inside the container filesystem.

Check the staging copy exists in the repo:

```bash
ls .handoff/memory/          # expect 10 .md files, MEMORY.md among them
```

If it is missing or stale, ask the old agent to re-copy its memory directory into
`.handoff/memory/` before you tear anything down. Skipping this loses every working
preference established on the project.

## 1. Build the template image (host)

```bash
cd <repo>
docker build -t sci-toolchain:v1 .
```

About 5.3 GB, dominated by Chromium and the Cairo toolchain. The Dockerfile handles
arm64 and amd64. It extends `docker/sandbox-templates:claude-code-docker`; the `-docker`
suffix is required, because the MCP condition runs a pgvector container on the
in-sandbox Docker daemon that only this variant ships.

## 2. Load it into the sandbox runtime (host)

The sandbox runtime does not share your Docker daemon's image store, so a local build
must be handed over explicitly:

```bash
docker image save sci-toolchain:v1 -o sci-toolchain.tar
sbx template load sci-toolchain.tar
sbx template ls                     # confirm it is listed
```

(Alternative for later: `docker build -t <org>/sci-toolchain:v1 --push .` and reference
it as `sbx run --template docker.io/<org>/sci-toolchain:v1 …`.)

## 3. Create the sandbox (host)

```bash
sbx run -t sci-toolchain:v1 claude <new-repo-path> --name sci
```

Three details that are easy to get wrong:

- the agent argument is **`claude`** — it must match the base variant the template
  extends (`claude-code-docker`), and it is `claude` for both plain and `-docker`;
- the workspace path is **positional**, after the agent;
- `--name sci` is what `sbx run --name sci` re-attaches to later, and what
  `sbx secret set <name> …` scopes to. The global `openrouter` secret follows any
  sandbox name automatically.

## 4. First prompt for the new agent (in the new sandbox)

Paste something like:

> Restore your memory: copy `.handoff/memory/` from the repo into
> `/home/agent/.claude/projects/<key>/memory/`, where `<key>` is this repo's absolute
> path with every `/` replaced by `-`. Then read `AGENTS.md` and confirm the
> visual-QA hooks in `.claude/settings.json` are intact.

The memory files are working preferences (how progress is reported, git boundaries,
visual-QA judgement); `AGENTS.md` carries everything project-factual.

## 5. Restore the MCP stack (in the new sandbox)

The embedded corpus travels with the repo at `vendor/cairo-coder/data`; nothing needs
re-ingesting. Recreate the container and service around it:

```bash
docker run -d --name postgres -p 5455:5432 --env-file vendor/cairo-coder/.env \
  -v "$PWD/vendor/cairo-coder/data:/var/lib/postgresql/data" pgvector/pgvector:pg17

cd vendor/cairo-coder/python
UV_PROJECT_ENVIRONMENT=/home/agent/.venv-cairo-coder uv sync --python 3.12
nohup uv run cairo-coder > /tmp/cairo-coder.log 2>&1 &      # serves on :3001

curl -m 60 -X POST localhost:3001/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{"messages":[{"role":"user","content":"What is a Cairo component?"}]}'
```

Constraints: the image tag must stay **pg17** (a Postgres data directory is not readable
by another major version), the bind path must be that exact directory, and the health
check needs the 60-second timeout — a RAG round trip takes 6–20 s, and a short timeout
makes a healthy service look dead.

## 6. Verify (in the new sandbox)

Each command has a known-good output; anything else means the restore missed something.

| Command | Expect |
|---|---|
| `scarb --version && snforge --version` | `2.19.4`, `0.62.1` |
| `uv run python -m bench.html_report` | `results/report.html` unchanged (`git diff --stat` empty) |
| `uv run python -m bench.audit` | `ALL CLAIMS VERIFY` |
| `uv run python -m bench.validate_tasks` | `All 13 tasks valid.` |
| `uv run python -m bench.screenshot` | 26 shots; three `ok … stacks at 390px` lines |
| corpus: `docker exec postgres psql -U <user> -d <db> -tAc "select count(*), count(distinct metadata->>'source') from <table>"` (values from `vendor/cairo-coder/.env`) | `4105\|11` |

No `uv sync` is needed for the benchmark itself: the template bakes the environment at
`/home/agent/.venv-sci` (`UV_PROJECT_ENVIRONMENT`), outside the workspace, precisely so
the bind mount cannot mask it.
