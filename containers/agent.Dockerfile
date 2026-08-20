# syntax=docker/dockerfile:1.7

ARG BRUNNER_REVISION

FROM python:3.12-bookworm AS python-builder

RUN python -m venv /opt/venv

COPY --from=brunner pyproject.toml README.md /build/brunner/
COPY --from=brunner src/ /build/brunner/src/

RUN --mount=type=cache,target=/root/.cache/pip \
    /opt/venv/bin/pip install --timeout 600 --retries 10 \
       /build/brunner \
       "matplotlib==3.11.0" \
       "numba==0.66.0" \
       "numpy==2.2.6" \
       "pillow==12.3.0" \
       "psutil==7.2.2" \
       "pytest==9.1.1" \
       "scipy==1.18.0" \
       "uv==0.8.15" \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build/granular-mean
COPY containers/agent-pyproject.toml pyproject.toml
COPY src/granular_mean/__init__.py src/granular_mean/
COPY src/granular_mean/agent.py src/granular_mean/
COPY src/granular_mean/codex_wrapper.py src/granular_mean/
RUN --mount=type=cache,target=/root/.cache/pip \
    /opt/venv/bin/pip install \
      --no-deps --timeout 600 --retries 10 .


FROM node:22-bookworm-slim AS node-builder

ARG CODEX_VERSION
ARG CLAUDE_CODE_VERSION

RUN test -n "${CODEX_VERSION}" \
    && test -n "${CLAUDE_CODE_VERSION}" \
    && npm install -g \
       "@openai/codex@${CODEX_VERSION}" \
       "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
    && npm cache clean --force


FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.source="https://github.com/cbizon/granular_mean"
ARG BRUNNER_REVISION
LABEL org.opencontainers.image.brunner-revision="${BRUNNER_REVISION}"

RUN test -n "${BRUNNER_REVISION}"

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends \
       bubblewrap \
       build-essential \
       git \
       poppler-utils \
       socat \
       util-linux \
    && useradd --create-home --uid 1000 benchmark

COPY --from=python-builder /opt/venv /opt/venv
COPY --from=node-builder /usr/local/bin/node /usr/local/bin/node
COPY --from=node-builder /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s \
       ../lib/node_modules/@openai/codex/bin/codex.js \
       /usr/local/bin/codex-real \
    && ln -s /opt/venv/bin/granular-mean-codex /usr/local/bin/codex \
    && ln -s \
       ../lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe \
       /usr/local/bin/claude

ENV PATH=/opt/venv/bin:$PATH \
    GRANULAR_MEAN_CODEX_REAL_EXECUTABLE=codex-real \
    MPLCONFIGDIR=/tmp/matplotlib \
    NUMBA_CACHE_DIR=/tmp/numba \
    PIP_NO_INDEX=1 \
    PYTHONNOUSERSITE=1 \
    PYTHONSAFEPATH=1 \
    PYTHONUNBUFFERED=1 \
    UV_NO_SYNC=1 \
    XDG_CACHE_HOME=/tmp/cache

USER benchmark
WORKDIR /brunner/trial/workspace

CMD ["python", "-m", "brunner.agent_cli", "--help"]
