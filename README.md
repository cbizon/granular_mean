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

## Run

Run a local candidate with an installed provider CLI:

```bash
UV_CACHE_DIR=.uv-cache uv run brunner \
  --benchmark granular_mean.definition \
  local-run runs/ \
  --provider codex \
  --model MODEL \
  --effort EFFORT
```

The deterministic evaluator compares the final common whole cycles against
the Updated-C trajectories. It reports cycle alignment, height-field contrast,
dominant wavelength, orientational order (`q2`, `q4`, `q6`), scalar and
rotational dynamics, collision rates, optional overlap counts, and differences
from the published Figure 1 panels. Set
`GRANULAR_MEAN_INCLUDE_OVERLAPS=false` only when deliberately skipping the
expensive overlap diagnostic.

To add Brunner's standard qualitative review, select the reviewed definition
and provide an explicit reviewer model:

```bash
GRANULAR_MEAN_REVIEWER_MODEL=REVIEWER_MODEL \
UV_CACHE_DIR=.uv-cache uv run brunner \
  --benchmark granular_mean.definition:build_reviewed_definition \
  local-run runs/ \
  --provider codex \
  --model CANDIDATE_MODEL \
  --effort EFFORT
```

Review evidence includes the prompt, manifests, deterministic results,
transcript, timing, usage, and status. It intentionally excludes the
multi-gigabyte trajectory artifacts.

## Campaign

The campaign runs only `gpt-5.6-sol`, once at each effort supported by the
current configured model catalog: `low`, `medium`, `high`, and `xhigh`.
Trial IDs are stable, so rerunning the same command resumes the existing
campaign state.

The campaign uses Brunner's local backend and the RENCI Azure OpenAI provider.
Set the API key, initialize the campaign, and run it with:

```bash
export AZURE_OPENAI_API_KEY=...

UV_CACHE_DIR=.uv-cache uv run brunner \
  --benchmark granular_mean.definition \
  campaign-init granular_mean.campaign

UV_CACHE_DIR=.uv-cache uv run brunner \
  --benchmark granular_mean.definition \
  campaign-run granular_mean.campaign \
  --poll-seconds 30
```

Runs are sequential by default because each simulation is CPU- and
storage-intensive. Set `GRANULAR_MEAN_MAX_PARALLEL` to a positive integer to
increase concurrency. Set `GRANULAR_MEAN_CAMPAIGN_ROOT` to change the default
state directory at `campaign-runs/sol-5-6-all-efforts-v1`.

The launcher pins the campaign to the `azure` Codex provider, the
`gpt-5.6-sol` model, and the four effort levels above. Override
`GRANULAR_MEAN_CODEX_BASE_URL`, `GRANULAR_MEAN_CODEX_PROVIDER_ID`,
`GRANULAR_MEAN_CODEX_PROVIDER_NAME`, or
`GRANULAR_MEAN_CODEX_ENVIRONMENT_KEY` only when the Azure deployment
configuration changes. `granular-mean-codex` normalizes Brunner's generated
response schema to the strict subset accepted by the Azure deployment before
starting Codex.
