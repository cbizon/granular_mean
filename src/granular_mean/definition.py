from __future__ import annotations

import os
import sys
from dataclasses import replace
from pathlib import Path

from brunner import (
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


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REVIEWER_MODEL = CODEX_MODEL
DEFAULT_REVIEWER_EFFORT = "xhigh"
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


def build_definition() -> BenchmarkDefinition:
    evaluator_image = os.environ.get(
        "GRANULAR_MEAN_EVALUATOR_IMAGE"
    )
    evaluator_command = (
        ("python", "-m", "granular_mean.evaluator")
        if evaluator_image
        else (sys.executable, "-m", "granular_mean.evaluator")
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
            command=evaluator_command,
            primary_report="evaluation/comparison.html",
            timeout_seconds=12 * 60 * 60,
            image=evaluator_image,
        ),
        reference=ReferenceDefinition(
            root=ROOT / "reference",
            validate_command=(
                sys.executable,
                "-m",
                "granular_mean.reference_validation",
            ),
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
        reviewer_executable = str(
            Path(sys.executable).with_name("granular-mean-codex")
        )
    review = QualitativeReviewDefinition(
        reviewer=reviewer,
        reviewer_executable=reviewer_executable,
        required=False,
        run_if_evaluation_failed=True,
        trial_evidence_paths=REVIEW_EVIDENCE,
        timeout_seconds=60 * 60,
        max_attempts=3,
    )
    return replace(
        build_definition(),
        qualitative_review=review,
    )
