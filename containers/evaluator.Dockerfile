# syntax=docker/dockerfile:1.7

ARG BRUNNER_REVISION=f3e01c1913a49e7440fa455566200c97751b9655

FROM python:3.12-bookworm AS python-builder

RUN python -m venv /opt/venv

COPY --from=brunner pyproject.toml README.md /build/brunner/
COPY --from=brunner src/ /build/brunner/src/

WORKDIR /build/granular-mean
COPY pyproject.toml README.md ./
COPY src/ src/

RUN /opt/venv/bin/pip install --no-cache-dir \
       /build/brunner \
       . \
    && /opt/venv/bin/python -c \
       "import brunner, granular_mean.evaluator; print(brunner.__version__)"


FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.source="https://github.com/cbizon/granular_mean"
ARG BRUNNER_REVISION
LABEL org.opencontainers.image.brunner-revision="${BRUNNER_REVISION}"

RUN useradd --create-home --uid 1000 benchmark

COPY --from=python-builder /opt/venv /opt/venv

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1

USER benchmark
WORKDIR /brunner/trial/workspace

ENTRYPOINT []
CMD ["python", "-m", "brunner.evaluation_cli", "--help"]
