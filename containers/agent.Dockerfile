FROM python:3.12-bookworm AS python-builder

ARG BRUNNER_REF=db9afcb1b18dd9283250bbea87730ce8dd4db56e

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir \
       "git+https://github.com/cbizon/brunner.git@${BRUNNER_REF}" \
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
COPY pyproject.toml README.md ./
COPY src/ src/
RUN /opt/venv/bin/pip install --no-cache-dir --no-deps .


FROM node:22-bookworm-slim AS node-builder

ARG CODEX_VERSION=0.144.1

RUN npm install -g "@openai/codex@${CODEX_VERSION}"


FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.source="https://github.com/cbizon/granular_mean"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       bubblewrap \
       build-essential \
       git \
       poppler-utils \
       socat \
       util-linux \
    && useradd --create-home --uid 1000 benchmark \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY --from=python-builder /opt/venv /opt/venv
COPY --from=node-builder /usr/local/bin/node /usr/local/bin/node
COPY --from=node-builder /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/@openai/codex/bin/codex.js /usr/local/bin/codex

ENV PATH=/opt/venv/bin:$PATH \
    MPLCONFIGDIR=/tmp/matplotlib \
    NUMBA_CACHE_DIR=/tmp/numba \
    PIP_NO_INDEX=1 \
    PYTHONUNBUFFERED=1 \
    UV_NO_SYNC=1 \
    XDG_CACHE_HOME=/tmp/cache

USER benchmark
WORKDIR /brunner/trial/workspace

CMD ["python", "-m", "brunner.agent_cli", "--help"]
