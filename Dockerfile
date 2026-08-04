# Toolchain for the Starknet Coding Index.
#
# Two jobs. It is a base image for a Docker Sandbox template:
#
#   docker build -t <org>/sci-toolchain:v1 --push .
#   sbx run --template docker.io/<org>/sci-toolchain:v1 claude
#   # or, without a registry:
#   docker image save <org>/sci-toolchain:v1 | sbx template load
#
# And it is the answer to "what does this project actually need", which was
# previously only recorded in one sandbox's filesystem.
#
# What it deliberately does NOT contain: the repo (mounted as the workspace at
# run time), results/runs/main.full.jsonl, vendor/cairo-coder, and any
# credential. The sandbox proxy injects secrets at run time, and Docker's own
# docs warn that saving a sandbox as a template captures whatever is on disk.
FROM docker/sandbox-templates:claude-code

# ---------------------------------------------------------------- system layer
# Exactly the list bench/screenshot.py prints when Chromium fails to launch.
# Fonts first: without them Chromium renders boxes and the visual-QA screenshots
# are worthless even though the run "succeeds".
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
      fontconfig fonts-liberation fonts-dejavu-core fonts-noto-core \
      libnss3 libgbm1 libglib2.0-0t64 libatk1.0-0t64 libatspi2.0-0t64 \
      libx11-6 libxcomposite1 libxdamage1 libxext6 libxfixes3 libxrandr2 \
      libxcb1 libxkbcommon0 libasound2t64 \
 && rm -rf /var/lib/apt/lists/*

# uv drives every Python command in this repo. Pinned so a rebuild cannot pick
# up a resolver change that alters the lockfile's interpretation.
ARG UV_VERSION=0.9.26
RUN curl -LsSf https://astral.sh/uv/${UV_VERSION}/install.sh \
      | env UV_INSTALL_DIR=/usr/local/bin INSTALLER_NO_MODIFY_PATH=1 sh

# --------------------------------------------------------------- user-level
# Everything below writes to /home/agent, so it must run as agent or it lands in
# /root and is invisible at run time.
USER agent
ENV PATH="/home/agent/.local/bin:/home/agent/.asdf/shims:/home/agent/.bun/bin:${PATH}"

# --- Cairo toolchain. These two versions are part of the experiment, not
# incidental: scarb compiles every submitted contract and snforge runs the
# hidden tests, so changing either changes what the benchmark measures.
ARG ASDF_VERSION=v0.20.0
ARG SCARB_VERSION=2.19.4
ARG SNFORGE_VERSION=0.62.1
RUN set -eux; \
    arch="$(uname -m)"; case "$arch" in aarch64) a=arm64 ;; x86_64) a=amd64 ;; *) echo "unsupported $arch" >&2; exit 1 ;; esac; \
    mkdir -p /home/agent/.local/bin; \
    curl -fsSL "https://github.com/asdf-vm/asdf/releases/download/${ASDF_VERSION}/asdf-${ASDF_VERSION}-linux-${a}.tar.gz" \
      | tar -xz -C /home/agent/.local/bin asdf; \
    asdf plugin add scarb https://github.com/software-mansion/asdf-scarb.git; \
    asdf plugin add starknet-foundry https://github.com/foundry-rs/asdf-starknet-foundry.git; \
    asdf install scarb "${SCARB_VERSION}"; \
    asdf install starknet-foundry "${SNFORGE_VERSION}"; \
    asdf set -u scarb "${SCARB_VERSION}"; \
    asdf set -u starknet-foundry "${SNFORGE_VERSION}"

# --- Python. ONE interpreter for both projects, pinned by us rather than
# inherited from the base image, so a base bump cannot silently change the
# interpreter underneath the experiment. 3.12 rather than something newer
# because the vendored Cairo Coder service pins psycopg2==2.9.10, which ships no
# wheel for 3.13+; on 3.14 the image would need gcc and libpq-dev and would
# compile it from source on every environment rebuild. The benchmark itself
# declares requires-python >=3.11 and produces identical scores on 3.12,
# intervals included, because index_ci seeds random.Random(0).
ARG PYTHON_VERSION=3.12
RUN uv python install ${PYTHON_VERSION}

# The project environment lives OUTSIDE the workspace on purpose: results/ and
# the repo arrive as a bind mount at run time, and anything the image writes to
# <repo>/.venv would be masked by it. Keeping it in $HOME also means renaming
# the project no longer breaks the environment.
ENV UV_PROJECT_ENVIRONMENT=/home/agent/.venv-sci
COPY --chown=agent:agent pyproject.toml uv.lock /tmp/sci/
RUN cd /tmp/sci && uv sync --frozen --python ${PYTHON_VERSION} && rm -rf /tmp/sci

# --- Chromium for the visual-QA gate, installed THROUGH the baked environment
# so the browser build matches the playwright pin in uv.lock (1.61.0 ->
# chromium-1228). Installing it any other way risks a browser the pinned
# playwright refuses to drive.
RUN cd / && uv run --no-project --python /home/agent/.venv-sci/bin/python \
      python -m playwright install chromium

# --- Corpus ingestion, needed only to refresh the documentation the MCP
# condition searches. The ingester is a bun project; it shells out to `mdbook`
# (CairoBookIngester.ts, StarknetFoundryIngester.ts) and to `antora`
# (AsciiDocIngester.ts, for the OpenZeppelin docs), so both must be on PATH or
# ingestion aborts. mdbook is held at 0.4.x deliberately: 0.5 breaks the
# cairo-book theme.
ARG BUN_VERSION=1.3.14
ARG MDBOOK_VERSION=0.4.52
RUN set -eux; \
    curl -fsSL https://bun.sh/install | bash -s "bun-v${BUN_VERSION}"; \
    arch="$(uname -m)"; \
    curl -fsSL "https://github.com/rust-lang/mdBook/releases/download/v${MDBOOK_VERSION}/mdbook-v${MDBOOK_VERSION}-${arch}-unknown-linux-musl.tar.gz" \
      | tar -xz -C /home/agent/.local/bin mdbook; \
    bun install -g @antora/cli @antora/site-generator

WORKDIR /home/agent
