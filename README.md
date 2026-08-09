# Granular Mean

This repository is the Brunner-based second version of the granular Figure 1
benchmark. An agent receives Bizon et al. (1998), several cited simulation
references, the seven Figure 1 conditions, and a Python scientific-computing
environment. It must implement the simulation and submit phase-dense
trajectories for panels `a`, `b`, `cd`, `e`, `f`, `g`, and `h`.

Brunner owns challenge staging, provider execution, retries, transcripts,
usage and timing records, artifact validation and collection, evaluator
invocation, optional qualitative review, and run reporting. This package owns
only the granular challenge, output contract, trusted reference collection,
trajectory validation, physics metrics, and comparison report.

## Layout

```text
challenge/                  Candidate-visible prompt, papers, and case data
output-contract.json        Canonical manifest, artifact, and run-status rules
reference/                  Small paper metadata plus ignored external bundle
resources/                  Reference archive identity and checksum
containers/                 Separate candidate-agent and trusted-evaluator images
deploy/                     Sterling reference PVC and upload pod
src/granular_mean/          Benchmark definition and domain evaluator
tests/                      Contract, staging, trajectory, and integration tests
```

The original task framing is retained in `challenge/prompt.md`. Its output
section is rendered by Brunner from `output-contract.json`; output prose and
machine validation therefore remain one contract when the prompt is revised.

## Setup

```bash
UV_CACHE_DIR=.uv-cache uv sync --all-groups
UV_CACHE_DIR=.uv-cache uv run brunner \
  --benchmark granular_mean.definition \
  contract-check
UV_CACHE_DIR=.uv-cache uv run pytest
```

Inspect the exact candidate workspace with:

```bash
UV_CACHE_DIR=.uv-cache uv run brunner \
  --benchmark granular_mean.definition \
  stage staged/granular-mean
```

## Trusted Reference

The validated Updated-C reference archive is approximately 2.4 GiB compressed
and is not committed. Its SHA-256 is locked in
`resources/reference-bundle.json`. Materialize it before evaluation:

```bash
UV_CACHE_DIR=.uv-cache uv run granular-reference \
  --archive /path/to/granular-benchmark-reference-v1.zip

UV_CACHE_DIR=.uv-cache uv run brunner \
  --benchmark granular_mean.definition \
  reference-validate
```

When the sibling original benchmark is present, `granular-reference` finds
`../granular_benchmark/artifacts/granular-benchmark-reference-v1.zip`
automatically. Pass `--load-trajectories` for a full NPZ validation during
materialization. By default the command performs structural validation and
builds Brunner's checksum manifest; evaluation then verifies that manifest
before trusted scoring.

## Evaluator Development

The deterministic evaluator compares the final common whole cycles against
the Updated-C trajectories. It reports cycle alignment, height-field contrast,
dominant wavelength, orientational order (`q2`, `q4`, `q6`), scalar and
rotational dynamics, collision rates, optional overlap counts, and differences
from the published Figure 1 panels. Set
`GRANULAR_MEAN_INCLUDE_OVERLAPS=false` only when deliberately skipping the
expensive overlap diagnostic.

Brunner no longer runs trusted evaluation in a local orchestrator process.
Exercise the evaluator through its integration test while developing it:

```bash
PYTHONPATH=../brunner/src .venv/bin/python -m pytest tests/test_evaluator.py
```

Production campaigns run the deterministic evaluator inside its trusted
Sterling image. After selected evaluator outputs are collected, the local
orchestrator runs the configured qualitative assessment over the prompt,
manifests, deterministic results, transcript, timing, usage, and status. It
intentionally excludes the multi-gigabyte trajectory artifacts.

## Campaign

The campaign runs only `gpt-5.6-sol`, once at each effort supported by the
current configured model catalog: `low`, `medium`, `high`, and `xhigh`.
Trial IDs are stable, so rerunning the same command resumes the existing
campaign state.

The campaign uses Brunner's Kubernetes backend on the current
`bizon@sterling` context. Each durable Job runs the candidate agent as an init
container and the trusted deterministic evaluator as the main container.
Only the agent receives the RENCI Azure credential and Brunner's managed
provider proxy. Only the evaluator mounts the validated reference PVC.

Build and publish both Linux/AMD64 images from the sibling Brunner checkout:

```bash
docker buildx build \
  --build-context brunner=../brunner \
  --platform linux/amd64 \
  -f containers/agent.Dockerfile \
  -t ghcr.io/cbizon/granular-mean-agent:brunner-f3e01c1 \
  --push \
  .

docker buildx build \
  --build-context brunner=../brunner \
  --platform linux/amd64 \
  -f containers/evaluator.Dockerfile \
  -t ghcr.io/cbizon/granular-mean-evaluator:brunner-f3e01c1 \
  --push \
  .
```

Both images embed Brunner revision `f3e01c1`. The agent also contains Codex CLI
`0.144.1` and candidate scientific tooling. The smaller evaluator contains
only Brunner, the benchmark package, and deterministic scoring dependencies;
it contains no provider CLI or credentials.

Published immutable images:

- Agent: `ghcr.io/cbizon/granular-mean-agent@sha256:8b785dc13f0c52ad53ddd59088b210c64327dd1dfedd38df4b5d952f76c99868`
- Evaluator: `ghcr.io/cbizon/granular-mean-evaluator@sha256:6a2cdcb2a2e66ccbef8451f29dbdb246f3fa888052d24004f50b034457e19f05`

Provision the trusted reference once before launching a campaign:

```bash
kubectl apply -f deploy/sterling-reference-pvc.yaml
kubectl apply -f deploy/sterling-reference-upload.yaml
kubectl cp reference/. \
  bizon/granular-mean-reference-upload:/reference
kubectl exec -n bizon granular-mean-reference-upload -- \
  python -m granular_mean.reference_validation \
  --reference-root /reference
kubectl annotate pvc -n bizon granular-mean-reference-v1 \
  dev.brunner/reference-manifest-sha256="$(
    shasum -a 256 reference/manifest.json | awk '{print $1}'
  )" \
  --overwrite
kubectl delete pod -n bizon granular-mean-reference-upload
```

Do not annotate the claim until the upload and remote validation have
completed. Brunner requires `ReadWriteMany` and checks this exact manifest
digest before submitting a trial.

Initialize and run the campaign with:

```bash
UV_CACHE_DIR=.uv-cache uv run brunner \
  --benchmark granular_mean.definition:build_reviewed_definition \
  campaign-init granular_mean.campaign

UV_CACHE_DIR=.uv-cache uv run brunner \
  --benchmark granular_mean.definition:build_reviewed_definition \
  campaign-run granular_mean.campaign \
  --poll-seconds 30
```

Set `GRANULAR_MEAN_AGENT_IMAGE` or `GRANULAR_MEAN_EVALUATOR_IMAGE` only to
override the digest-pinned defaults. The evaluator requests 4 CPUs and 16 GiB
of memory, with limits of 8 CPUs and 32 GiB, plus 1 GiB requested and 4 GiB
limited ephemeral storage. Override those values with
`GRANULAR_MEAN_EVALUATOR_CPU_REQUEST`,
`GRANULAR_MEAN_EVALUATOR_CPU_LIMIT`,
`GRANULAR_MEAN_EVALUATOR_MEMORY_REQUEST`,
`GRANULAR_MEAN_EVALUATOR_MEMORY_LIMIT`,
`GRANULAR_MEAN_EVALUATOR_EPHEMERAL_STORAGE_REQUEST`, and
`GRANULAR_MEAN_EVALUATOR_EPHEMERAL_STORAGE_LIMIT`.

Runs are sequential by default because each simulation is CPU- and
storage-intensive. Each agent requests 2 CPUs and 8 GiB of memory, with limits
of 8 CPUs and 32 GiB. It also requests 1 GiB of ephemeral storage with a 3 GiB
limit for `/tmp`, provider caches, container logs, and other local writable
data. Override those benchmark requirements with
`GRANULAR_MEAN_AGENT_CPU_REQUEST`, `GRANULAR_MEAN_AGENT_CPU_LIMIT`,
`GRANULAR_MEAN_AGENT_MEMORY_REQUEST`, and
`GRANULAR_MEAN_AGENT_MEMORY_LIMIT`,
`GRANULAR_MEAN_AGENT_EPHEMERAL_STORAGE_REQUEST`, and
`GRANULAR_MEAN_AGENT_EPHEMERAL_STORAGE_LIMIT`. Set
`GRANULAR_MEAN_MAX_PARALLEL` to a positive integer to increase concurrency.
Set `GRANULAR_MEAN_CAMPAIGN_ROOT` to change the default state directory at
`campaign-runs/sol-5-6-all-efforts-v1`.

Sterling settings can be overridden with
`GRANULAR_MEAN_STERLING_NAMESPACE`,
`GRANULAR_MEAN_STERLING_STORAGE_SIZE`,
`GRANULAR_MEAN_STERLING_STORAGE_CLASS`,
`GRANULAR_MEAN_STERLING_SERVICE_ACCOUNT`,
`GRANULAR_MEAN_STERLING_IMAGE_PULL_SECRET`, and
`GRANULAR_MEAN_STERLING_CODEX_SECRET`. The default reference claim is
`granular-mean-reference-v1`, and the managed proxy is an immutable official
Ubuntu Squid image. Override those deployment inputs with
`GRANULAR_MEAN_STERLING_REFERENCE_CLAIM`,
`GRANULAR_MEAN_STERLING_PROXY_IMAGE`, or
`GRANULAR_MEAN_STERLING_ARTIFACT_READER_IMAGE`.

Artifact collection defaults to
1 MiB resumable chunks, 10 same-offset attempts per chunk, and a 600-second
timeout per `kubectl exec` call. Override those transfer settings with
`GRANULAR_MEAN_STERLING_ARTIFACT_CHUNK_BYTES` and
`GRANULAR_MEAN_STERLING_ARTIFACT_CHUNK_ATTEMPTS`, and
`GRANULAR_MEAN_STERLING_COMMAND_TIMEOUT_SECONDS`.

Campaign construction fails fast when the unreviewed definition is selected,
so newly added models or effort levels cannot silently skip qualitative
assessment.

The launcher pins the campaign to the `azure` Codex provider, the
`gpt-5.6-sol` model, and the four effort levels above. Override
`GRANULAR_MEAN_CODEX_BASE_URL`, `GRANULAR_MEAN_CODEX_PROVIDER_ID`,
`GRANULAR_MEAN_CODEX_PROVIDER_NAME`, or
`GRANULAR_MEAN_CODEX_ENVIRONMENT_KEY` only when the Azure deployment
configuration changes. `granular-mean-codex` normalizes Brunner's generated
response schema to the strict subset accepted by the Azure deployment before
starting Codex.
