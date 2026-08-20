# syntax=docker/dockerfile:1.7

ARG BRUNNER_REVISION

FROM node:22-bookworm-slim AS node-runtime

ARG CODEX_VERSION

RUN test -n "${CODEX_VERSION}" \
    && npm install --global "@openai/codex@${CODEX_VERSION}" \
    && npm cache clean --force


FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.source="https://github.com/cbizon/granular_mean"
ARG BRUNNER_REVISION
ARG KUBECTL_VERSION
ARG TARGETARCH
LABEL org.opencontainers.image.brunner-revision="${BRUNNER_REVISION}"

RUN test -n "${BRUNNER_REVISION}" \
    && test -n "${KUBECTL_VERSION}" \
    && test -n "${TARGETARCH}"

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && curl --fail --location --silent --show-error \
       "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${TARGETARCH}/kubectl" \
       --output /usr/local/bin/kubectl \
    && chmod 0755 /usr/local/bin/kubectl \
    && apt-get purge -y --auto-remove curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 benchmark

COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/@openai/codex/bin/codex.js /usr/local/bin/codex

COPY --from=brunner pyproject.toml README.md /build/brunner/
COPY --from=brunner src/ /build/brunner/src/

RUN python -m venv /opt/venv

COPY pyproject.toml README.md /opt/granular-mean/
COPY src/ /opt/granular-mean/src/
COPY challenge/ /opt/granular-mean/challenge/
COPY reference/manifest.json /opt/granular-mean/reference/manifest.json
COPY reference/paper/ /opt/granular-mean/reference/paper/
COPY resources/ /opt/granular-mean/resources/
COPY output-contract.json /opt/granular-mean/output-contract.json

RUN --mount=type=cache,target=/root/.cache/pip \
    /opt/venv/bin/pip install --timeout 600 --retries 10 \
       /build/brunner \
    && /opt/venv/bin/pip install --timeout 600 --retries 10 \
       --editable /opt/granular-mean \
    && /opt/venv/bin/python -c \
       "import brunner, granular_mean.evaluator; print(brunner.__version__)"

ENV PATH=/opt/venv/bin:$PATH \
    CODEX_HOME=/tmp/codex \
    GRANULAR_MEAN_CODEX_BYPASS_NESTED_SANDBOX=true \
    HOME=/tmp/home \
    MPLCONFIGDIR=/tmp/matplotlib \
    NUMBA_CACHE_DIR=/tmp/numba \
    PIP_NO_INDEX=1 \
    PYTHONNOUSERSITE=1 \
    PYTHONSAFEPATH=1 \
    PYTHONUNBUFFERED=1 \
    XDG_CACHE_HOME=/tmp/cache

USER benchmark
WORKDIR /tmp

CMD ["brunner", "--help"]
