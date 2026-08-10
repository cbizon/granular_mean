# syntax=docker/dockerfile:1.7

ARG BRUNNER_REVISION

FROM python:3.12-bookworm AS python-builder

RUN python -m venv /opt/venv

COPY --from=brunner pyproject.toml README.md /build/brunner/
COPY --from=brunner src/ /build/brunner/src/

WORKDIR /build/granular-mean
COPY pyproject.toml README.md ./
COPY src/ src/

RUN /opt/venv/bin/pip install --no-cache-dir \
       /build/brunner \
       "numpy==2.2.6" \
       "pillow==12.3.0" \
       "scipy==1.18.0" \
    && /opt/venv/bin/pip install --no-cache-dir --no-deps . \
    && /opt/venv/bin/python -c \
       "import brunner, granular_mean.evaluator; print(brunner.__version__)"


FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.source="https://github.com/cbizon/granular_mean"
ARG BRUNNER_REVISION
LABEL org.opencontainers.image.brunner-revision="${BRUNNER_REVISION}"

RUN test -n "${BRUNNER_REVISION}"

RUN useradd --create-home --uid 1000 benchmark

COPY --from=python-builder /opt/venv /opt/venv

ENV PATH=/opt/venv/bin:$PATH \
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

ENTRYPOINT []
CMD ["python", "-m", "brunner.evaluation_cli", "--help"]
