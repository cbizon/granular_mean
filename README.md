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
current configured model catalog: `low`, `medium`, `high`, `xhigh`, `max`,
and `ultra`.
Trial IDs are stable, so rerunning the same command resumes the existing
campaign state.

The campaign uses Brunner's Kubernetes backend on the current
`bizon@sterling` context. Each durable Job runs the candidate agent as an init
container and the trusted deterministic evaluator as the main container.
Only the agent receives the RENCI Azure credential and Brunner's managed
provider proxy. Only the evaluator mounts the validated reference PVC.

Build and publish both Linux/AMD64 images from the sibling Brunner checkout.
The agent image intentionally installs only the agent launcher and provider
wrapper from this repository; trusted evaluator, scoring, report, and reference
code must not be present in it.

```bash
docker buildx build \
  --build-context brunner=../brunner \
  --build-arg BRUNNER_REVISION="$(git -C ../brunner rev-parse HEAD)" \
  --platform linux/amd64 \
  -f containers/agent.Dockerfile \
  -t ghcr.io/cbizon/granular-mean-agent:brunner-0252441 \
  --push \
  .

docker buildx build \
  --build-context brunner=../brunner \
  --build-arg BRUNNER_REVISION="$(git -C ../brunner rev-parse HEAD)" \
  --platform linux/amd64 \
  -f containers/evaluator.Dockerfile \
  -t ghcr.io/cbizon/granular-mean-evaluator:brunner-0252441 \
  --push \
  .
```

Commit and clean the Brunner worktree before building. Both Dockerfiles require
an explicit Brunner revision and embed it in the resulting image.
The agent also contains Codex CLI `0.144.1` and candidate scientific tooling.
The smaller evaluator contains only Brunner, the benchmark package, and
deterministic scoring dependencies; it contains no provider CLI or
credentials.

Published immutable Linux/AMD64 images:

- Agent: `ghcr.io/cbizon/granular-mean-agent@sha256:487049af74c582eaf3af204af8d86a05fd57918ee6edfdae2409742c9699975d`
- Evaluator: `ghcr.io/cbizon/granular-mean-evaluator@sha256:77c4742436b703526c779565f8dc749156cc48cf661363241e93d24f8fad1b2d`

The campaign and reference-upload manifest pin these digests by default.
Campaign construction rejects the previous images because they predate the
restored isolation invariants.

The campaign defaults to the administrator-controlled personal `bizon`
namespace and Brunner's `controlled-egress` network isolation mode. This mode
accepts Sterling's baseline namespace-wide ingress policy while continuing to
reject any additive egress policy that selects Brunner pipeline, stager, or
artifact-reader Pods. Audit the namespace NetworkPolicies before each launch.

The reference manifests are namespace-neutral. Provision the trusted reference
once before launching a campaign:

```bash
scripts/provision-sterling-reference.sh
```

The script defaults to namespace `bizon` and requires Kubernetes context
`bizon@sterling`. Override those safeguards with
`GRANULAR_MEAN_STERLING_NAMESPACE` and
`GRANULAR_MEAN_STERLING_CONTEXT` only when intentionally targeting another
namespace or cluster. It applies and waits for the `ReadWriteMany` PVC, isolates
the temporary upload Pod, replaces the remote reference contents, validates
them inside the evaluator image, records and verifies the manifest digest, and
removes the temporary Pod and NetworkPolicy on success or failure.

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

The campaign defaults to the published digest-pinned builds above. Override
`GRANULAR_MEAN_AGENT_IMAGE` or `GRANULAR_MEAN_EVALUATOR_IMAGE` only to use
another immutable build. The evaluator requests
3 CPUs and 16 GiB of memory, with limits of 8 CPUs and 64 GiB, plus 1 GiB
requested and 3 GiB limited ephemeral storage. Together with Sterling's proxy
defaults, those values remain below the namespace CPU and ephemeral-storage
quotas. Override them with
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
`campaign-runs/sol-5-6-all-efforts-v2`.

The Sterling namespace defaults to `bizon` and can be overridden with
`GRANULAR_MEAN_STERLING_NAMESPACE`. Network isolation defaults to
`controlled-egress`; set `GRANULAR_MEAN_STERLING_NETWORK_ISOLATION_MODE=strict`
when using a dedicated namespace with exclusive ingress and egress policies.
Other Sterling settings can be overridden with
`GRANULAR_MEAN_STERLING_STORAGE_SIZE`,
`GRANULAR_MEAN_STERLING_STORAGE_CLASS`,
`GRANULAR_MEAN_STERLING_SERVICE_ACCOUNT`,
`GRANULAR_MEAN_STERLING_IMAGE_PULL_SECRET`, and
`GRANULAR_MEAN_STERLING_CODEX_SECRET`. The default reference claim is
`granular-mean-reference-v1`, the default GHCR pull credential is
`balls-bench-ghcr`, and the managed proxy is an immutable official Ubuntu Squid
image. Override those deployment inputs with
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
`gpt-5.6-sol` model, and the six effort levels above. Override
`GRANULAR_MEAN_CODEX_BASE_URL`, `GRANULAR_MEAN_CODEX_PROVIDER_ID`,
`GRANULAR_MEAN_CODEX_PROVIDER_NAME`, or
`GRANULAR_MEAN_CODEX_ENVIRONMENT_KEY` only when the Azure deployment
configuration changes. `granular-mean-codex` normalizes Brunner's generated
response schema to the strict subset accepted by the Azure deployment before
starting Codex.
