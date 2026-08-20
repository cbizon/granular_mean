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
containers/                 Candidate-agent and trusted-controller images
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

The self-contained `evaluation/comparison.html` report renders representative
height fields plus phase-conditioned scalar, rotational, collision-rate, and
overlap plots. Reports produced before those plots were restored can be
regenerated without trajectory NPZ files. The migration preserves the
checksum-verified archived report and writes `comparison-physical.html`,
updating the local Brunner run-report link:

```bash
.venv/bin/python scripts/regenerate-comparison-reports.py \
  campaign-runs/CAMPAIGN/collected/TRIAL/evaluation/comparison.html
```

Brunner no longer runs trusted evaluation in a local orchestrator process.
Exercise the evaluator through its integration test while developing it:

```bash
PYTHONPATH=../brunner/src .venv/bin/python -m pytest tests/test_evaluator.py
```

Production campaigns run the deterministic evaluator inside the trusted
Sterling controller image. The cluster controller then runs the configured
qualitative assessment over the prompt, manifests, deterministic results,
transcript, timing, usage, and status. It intentionally excludes the
multi-gigabyte trajectory artifacts.

## Campaign

The campaign runs `claude-haiku-4-5`, `gpt-5.6-luna`, `gpt-5.6-terra`, and
`gpt-5.6-sol`, in that order, once each at `low`. Trial IDs are stable within
campaign `granular-figure1-haiku-luna-terra-sol-low-cluster-v1`.

Brunner's orchestrator runs as a Kubernetes Deployment in namespace `bizon`.
Its append-only state and finalized results live on separate `ReadWriteMany`
PVCs. The laptop is only a client for submit, status, port-forwarded
monitoring, retrieval, and deletion. Closing the monitor, sleeping the laptop,
losing the VPN, or terminating the client command does not stop the campaign.

Each trial Job runs the candidate agent as an init container and the trusted
deterministic evaluator as the main container. Only the agent receives the
RENCI Azure credential and Brunner's managed provider proxy. Only the
evaluator mounts the validated reference PVC. Qualitative assessments run in
separate controller-image Jobs with their own Secret mapping and managed proxy.

### Images

Build and publish the Linux/AMD64 agent and controller images with the sibling
Brunner checkout as a named build context. The agent image contains Brunner,
Codex, Claude Code, the Azure Codex wrapper, and candidate scientific tooling,
but no trusted benchmark code. The controller contains Brunner, `kubectl`,
Codex, the
benchmark, evaluator, challenge, and tracked reference metadata. The 2.6 GiB
generated reference tree remains excluded and is mounted from the trusted PVC.

```bash
docker buildx build \
  --build-context brunner=../brunner \
  --build-arg BRUNNER_REVISION="$(git -C ../brunner rev-parse HEAD)" \
  --build-arg CODEX_VERSION=VERSION \
  --build-arg CLAUDE_CODE_VERSION=VERSION \
  --platform linux/amd64 \
  -f containers/agent.Dockerfile \
  -t ghcr.io/cbizon/granular-mean-agent:VERSION \
  --push \
  .

docker buildx build \
  --build-context brunner=../brunner \
  --build-arg BRUNNER_REVISION="$(git -C ../brunner rev-parse HEAD)" \
  --build-arg CODEX_VERSION=VERSION \
  --build-arg KUBECTL_VERSION=vX.Y.Z \
  --platform linux/amd64 \
  -f containers/controller.Dockerfile \
  -t ghcr.io/cbizon/granular-mean-controller:VERSION \
  --push \
  .
```

Both Dockerfiles require explicit Brunner and tool versions. The published
immutable images are:

```bash
ghcr.io/cbizon/granular-mean-agent@sha256:0d222e1700e49dcd24107c462c76500f0612811c6041227b66f29ac72f588537
ghcr.io/cbizon/granular-mean-controller@sha256:0795d16f7952c03b00ccaf98447b6cdb1aed31e3bf1423c73d90fdf7e0f659f0
```

They are pinned in `src/granular_mean/images.py`. Brunner injects the submitted
immutable image identities when the controller reloads the campaign and
definition, so the controller image does not need to contain its own final
digest.

### Cluster Prerequisites

The campaign defaults to the administrator-controlled `bizon` namespace and
Brunner's `controlled-egress` network isolation mode. The namespace must
contain:

- Secret `balls-bench-codex-azure`, key `AZURE_OPENAI_API_KEY`;
- Secret `balls-bench-claude-oauth`, key `CLAUDE_CODE_OAUTH_TOKEN`;
- Docker registry Secret `balls-bench-ghcr`;
- validated reference PVC `granular-mean-reference-v1`.

Audit the namespace NetworkPolicies before each launch. Provision the trusted
reference once before the first campaign:

```bash
scripts/provision-sterling-reference.sh
```

The script requires Kubernetes context `bizon@sterling`, applies the
namespace-neutral `ReadWriteMany` PVC, isolates the temporary upload Pod,
validates the uploaded reference in-cluster, records the manifest digest, and
removes temporary resources.

### Lifecycle

Submit the controller and inspect its status:

```bash
scripts/manage-campaign.sh submit
scripts/manage-campaign.sh status
```

Open the dashboard through a disposable local port-forward:

```bash
scripts/manage-campaign.sh monitor
```

The monitor is available at `http://127.0.0.1:8765/` by default. Terminating
the port-forward does not affect the controller.

Retrieve the checksum-verified finalized bundle:

```bash
scripts/manage-campaign.sh retrieve
# or
scripts/manage-campaign.sh retrieve /path/to/destination
```

Delete the controller and control-plane resources while preserving finalized
results, or explicitly delete the results PVC too:

```bash
scripts/manage-campaign.sh delete
scripts/manage-campaign.sh delete-results
```

The script requires context `bizon@sterling`; override
`GRANULAR_MEAN_STERLING_CONTEXT` only when deliberately targeting another
cluster.

### Resources And Overrides

Runs are sequential by default because each simulation is CPU- and
storage-intensive. Each agent requests 2 CPUs and 8 GiB of memory, with limits
of 8 CPUs and 32 GiB, plus 1 GiB requested and 3 GiB limited ephemeral
storage. The evaluator requests 3 CPUs and 16 GiB of memory, with limits of
8 CPUs and 64 GiB and the same ephemeral-storage values. Set
`GRANULAR_MEAN_MAX_PARALLEL` to increase concurrency.

The controller requests 500 millicores/1 GiB and is limited to 2 CPUs/4 GiB.
Preparation and assessment Jobs request 1 CPU/2 GiB and are limited to
4 CPUs/8 GiB. Control and result PVCs are 20 GiB each. Override these values
with the corresponding `GRANULAR_MEAN_AGENT_*`,
`GRANULAR_MEAN_EVALUATOR_*`, `GRANULAR_MEAN_CONTROLLER_*`,
`GRANULAR_MEAN_PREPARATION_*`, and `GRANULAR_MEAN_ASSESSMENT_*` variables.

The namespace, storage class, trial storage size, reference claim, pull
Secret, provider Secret, and Squid image remain configurable through the
corresponding `GRANULAR_MEAN_STERLING_*` variables.

Artifact collection uses 1 MiB resumable chunks, 10 same-offset attempts, and
a 600-second Kubernetes command timeout. Evaluator-consumed trajectory NPZ
files are excluded from publication; each published trial is capped at 1 GiB.

Campaign construction fails fast when the unreviewed definition is selected,
so newly added models or efforts cannot silently skip qualitative assessment.
The campaign pins the three Codex models to the `azure` provider and Haiku to
Claude Code, all at `low`. The agent image exposes provider-specific
executables so Brunner selects `codex` or `claude` for each trial.
`granular-mean-codex` normalizes Brunner's generated response schema to the
strict subset accepted by the Azure deployment before starting Codex.
