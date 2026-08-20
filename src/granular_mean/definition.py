from __future__ import annotations

import os
import sys
from dataclasses import replace
from pathlib import Path

from brunner import (
    ArtifactPolicy,
    BenchmarkDefinition,
    ChallengeDefinition,
    EvaluationDefinition,
    ProviderSettings,
    QualitativeReviewDefinition,
    ReferenceDefinition,
    RuntimeDefaults,
)

from granular_mean.agent import (
    CODEX_MODEL,
    azure_codex_settings,
)
from granular_mean.images import (
    DEFAULT_EVALUATOR_IMAGE,
    RETIRED_EVALUATOR_IMAGE,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REVIEWER_MODEL = CODEX_MODEL
DEFAULT_REVIEWER_EFFORT = "xhigh"
DEFAULT_REVIEWER_TIMEOUT_SECONDS = 24 * 60 * 60
DEFAULT_REVIEWER_MAX_ATTEMPTS = 300
DEFAULT_REVIEWER_RETRY_INITIAL_SECONDS = 30
DEFAULT_REVIEWER_RETRY_MAX_SECONDS = 5 * 60
V2_CAMPAIGN_REVIEW_CONTRACT_SHA256 = (
    "29b75a2ecc9d4381e01b02fed97e11869c7f8c81ce3f27e742857ca2b3f03c6b"
)
DEFAULT_EVALUATOR_CPU_REQUEST = "3"
DEFAULT_EVALUATOR_CPU_LIMIT = "8"
DEFAULT_EVALUATOR_MEMORY_REQUEST = "16Gi"
DEFAULT_EVALUATOR_MEMORY_LIMIT = "64Gi"
DEFAULT_EVALUATOR_EPHEMERAL_STORAGE_REQUEST = "1Gi"
DEFAULT_EVALUATOR_EPHEMERAL_STORAGE_LIMIT = "3Gi"
REVIEW_EVIDENCE = (
    "workspace/PROMPT.md",
    "workspace/cases.json",
    "workspace/environment.json",
    "workspace/**/*.py",
    "workspace/submission/manifest.json",
    "workspace/submission/run-status.json",
    "evaluation/results.json",
    "evaluation/details.json",
    "transcript",
    "timing",
    "usage",
    "status.json",
)


def _required_environment(name: str, default: str) -> str:
    value = os.environ.get(name, default).strip()
    if not value:
        raise RuntimeError(f"{name} must not be empty")
    return value


def build_definition() -> BenchmarkDefinition:
    evaluator_image = _required_environment(
        "GRANULAR_MEAN_EVALUATOR_IMAGE",
        DEFAULT_EVALUATOR_IMAGE,
    )
    return BenchmarkDefinition(
        benchmark_id="granular-figure1",
        version="2.0.0",
        display_title="Granular Figure 1 benchmark",
        root=ROOT,
        contract_path=ROOT / "output-contract.json",
        challenge=ChallengeDefinition(
            root=ROOT / "challenge",
            forbidden_names=(
                "reference",
                "evaluator.py",
                "figure1-paper.json",
            ),
        ),
        evaluation=EvaluationDefinition(
            command=("granular-mean-evaluator",),
            primary_report="evaluation/comparison.html",
            timeout_seconds=12 * 60 * 60,
            image=evaluator_image,
            cpu_request=_required_environment(
                "GRANULAR_MEAN_EVALUATOR_CPU_REQUEST",
                DEFAULT_EVALUATOR_CPU_REQUEST,
            ),
            cpu_limit=_required_environment(
                "GRANULAR_MEAN_EVALUATOR_CPU_LIMIT",
                DEFAULT_EVALUATOR_CPU_LIMIT,
            ),
            memory_request=_required_environment(
                "GRANULAR_MEAN_EVALUATOR_MEMORY_REQUEST",
                DEFAULT_EVALUATOR_MEMORY_REQUEST,
            ),
            memory_limit=_required_environment(
                "GRANULAR_MEAN_EVALUATOR_MEMORY_LIMIT",
                DEFAULT_EVALUATOR_MEMORY_LIMIT,
            ),
            ephemeral_storage_request=_required_environment(
                "GRANULAR_MEAN_EVALUATOR_EPHEMERAL_STORAGE_REQUEST",
                DEFAULT_EVALUATOR_EPHEMERAL_STORAGE_REQUEST,
            ),
            ephemeral_storage_limit=_required_environment(
                "GRANULAR_MEAN_EVALUATOR_EPHEMERAL_STORAGE_LIMIT",
                DEFAULT_EVALUATOR_EPHEMERAL_STORAGE_LIMIT,
            ),
        ),
        reference=ReferenceDefinition(
            root=ROOT / "reference",
            validate_command=("granular-reference-validate",),
        ),
        runtime=RuntimeDefaults(
            timeout_seconds=48 * 60 * 60,
            finalization_seconds=30 * 60,
            retry_initial_seconds=30,
            retry_max_seconds=15 * 60,
            backend_shutdown_grace_seconds=2 * 60,
            max_attempts=50,
            max_activity_interval_seconds=48 * 60 * 60,
            submission_poll_seconds=2,
        ),
        artifacts=ArtifactPolicy(
            groups={
                "raw-trajectories": (
                    "workspace/submission/*.npz",
                    "workspace/submission/**/*.npz",
                ),
            },
            max_collection_bytes=1024 * 1024 * 1024,
            max_diagnostic_collection_bytes=512 * 1024 * 1024,
        ),
    )


def build_reviewed_definition() -> BenchmarkDefinition:
    reviewer_provider = os.environ.get(
        "GRANULAR_MEAN_REVIEWER_PROVIDER",
        "codex",
    )
    reviewer_model = os.environ.get(
        "GRANULAR_MEAN_REVIEWER_MODEL",
        DEFAULT_REVIEWER_MODEL,
    )
    reviewer_effort = os.environ.get(
        "GRANULAR_MEAN_REVIEWER_EFFORT",
        DEFAULT_REVIEWER_EFFORT,
    )
    reviewer = (
        azure_codex_settings(reviewer_model, reviewer_effort)
        if reviewer_provider == "codex"
        else ProviderSettings(
            provider=reviewer_provider,
            model=reviewer_model,
            effort=reviewer_effort,
        )
    )
    reviewer_executable = os.environ.get(
        "GRANULAR_MEAN_REVIEWER_EXECUTABLE"
    )
    if reviewer_executable is None and reviewer_provider == "codex":
        reviewer_executable = "granular-mean-codex"
    review = QualitativeReviewDefinition(
        reviewer=reviewer,
        reviewer_executable=reviewer_executable,
        required=True,
        run_if_evaluation_failed=True,
        trial_evidence_paths=REVIEW_EVIDENCE,
        timeout_seconds=DEFAULT_REVIEWER_TIMEOUT_SECONDS,
        max_attempts=DEFAULT_REVIEWER_MAX_ATTEMPTS,
        retry_initial_seconds=DEFAULT_REVIEWER_RETRY_INITIAL_SECONDS,
        retry_max_seconds=DEFAULT_REVIEWER_RETRY_MAX_SECONDS,
    )
    return replace(
        build_definition(),
        qualitative_review=review,
    )


def build_v2_campaign_recovery_definition() -> BenchmarkDefinition:
    definition = build_reviewed_definition()
    review = definition.qualitative_review
    if review is None:
        raise RuntimeError("qualitative review is not configured")
    recovered = replace(
        definition,
        qualitative_review=replace(
            review,
            reviewer_executable=str(
                Path(sys.executable).with_name("granular-mean-codex")
            ),
            required=False,
            timeout_seconds=60 * 60,
            max_attempts=3,
            retry_initial_seconds=10,
            retry_max_seconds=60,
        ),
    )
    contract_sha256 = recovered.resolved_assessments()[
        0
    ].contract_manifest()["contract_sha256"]
    if contract_sha256 != V2_CAMPAIGN_REVIEW_CONTRACT_SHA256:
        raise RuntimeError(
            "v2 campaign recovery assessment contract drifted: "
            f"{contract_sha256}"
        )
    return recovered
