from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

from brunner import (
    BenchmarkDefinition,
    CampaignPlan,
    CampaignRunner,
    CampaignTrial,
)
from brunner.backends import (
    KubernetesBackend,
    KubernetesProfile,
    WorkloadSpec,
)
from brunner.campaign import default_workload_factory
from brunner.contract import OutputContract

from granular_mean.agent import (
    CODEX_EFFORTS,
    CODEX_MODEL,
    codex_environment_key,
)
from granular_mean.definition import ROOT


CAMPAIGN_VARIANT = "sol-5-6-all-efforts-v1"
CAMPAIGN_ID = f"granular-figure1-{CAMPAIGN_VARIANT}"
DEFAULT_MAX_PARALLEL = 1
DEFAULT_AGENT_IMAGE = (
    "ghcr.io/cbizon/granular-mean-agent@"
    "sha256:e704a69bbc003cf5f90db1613b65a51a826c73cd8b548a20c442531a4a0f985b"
)
DEFAULT_STERLING_NAMESPACE = "bizon"
DEFAULT_STERLING_STORAGE_SIZE = "20Gi"
DEFAULT_STERLING_CODEX_SECRET = "balls-bench-codex-azure"
DEFAULT_AGENT_CPU_REQUEST = "2"
DEFAULT_AGENT_CPU_LIMIT = "8"
DEFAULT_AGENT_MEMORY_REQUEST = "8Gi"
DEFAULT_AGENT_MEMORY_LIMIT = "32Gi"
NESTED_SANDBOX_BYPASS_ENVIRONMENT = (
    "GRANULAR_MEAN_CODEX_BYPASS_NESTED_SANDBOX"
)


def build_campaign_trials() -> tuple[CampaignTrial, ...]:
    return tuple(
        CampaignTrial(
            test_id=f"codex-gpt-5-6-sol-{effort}-r01",
            provider="codex",
            model=CODEX_MODEL,
            effort=effort,
        )
        for effort in CODEX_EFFORTS
    )


def _positive_integer_environment(name: str, default: int) -> int:
    raw_value = os.environ.get(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as error:
        raise RuntimeError(f"{name} must be an integer") from error
    if value < 1:
        raise RuntimeError(f"{name} must be positive")
    return value


def _resource_environment(name: str, default: str) -> str:
    value = os.environ.get(name, default).strip()
    if not value:
        raise RuntimeError(f"{name} must not be empty")
    return value


def campaign_workload_factory(
    trial: Path,
    campaign_trial: CampaignTrial,
    plan: CampaignPlan,
    definition: BenchmarkDefinition,
    backend_name: str,
) -> WorkloadSpec:
    workload = default_workload_factory(
        trial,
        campaign_trial,
        plan,
        definition,
        backend_name,
    )
    return replace(
        workload,
        command=(
            "python",
            "-m",
            "granular_mean.agent",
            "/brunner/trial",
        ),
    )


def _optional_environment(name: str) -> str | None:
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else None


def _sterling_profile(
    *,
    agent_image: str | None,
    max_parallel: int,
) -> KubernetesProfile:
    environment_key = codex_environment_key()
    pull_secret = _optional_environment(
        "GRANULAR_MEAN_STERLING_IMAGE_PULL_SECRET"
    )
    return KubernetesProfile(
        namespace=os.environ.get(
            "GRANULAR_MEAN_STERLING_NAMESPACE",
            DEFAULT_STERLING_NAMESPACE,
        ),
        agent_image=agent_image,
        artifact_reader_image=agent_image,
        storage_size=os.environ.get(
            "GRANULAR_MEAN_STERLING_STORAGE_SIZE",
            DEFAULT_STERLING_STORAGE_SIZE,
        ),
        storage_class_name=_optional_environment(
            "GRANULAR_MEAN_STERLING_STORAGE_CLASS"
        ),
        service_account_name=_optional_environment(
            "GRANULAR_MEAN_STERLING_SERVICE_ACCOUNT"
        ),
        image_pull_secrets=(pull_secret,) if pull_secret else (),
        secret_environment={
            environment_key: (
                os.environ.get(
                    "GRANULAR_MEAN_STERLING_CODEX_SECRET",
                    DEFAULT_STERLING_CODEX_SECRET,
                ),
                environment_key,
            )
        },
        nonsecret_environment={
            NESTED_SANDBOX_BYPASS_ENVIRONMENT: "true",
        },
        max_parallel=max_parallel,
    )


def build_campaign(
    definition: BenchmarkDefinition,
    contract: OutputContract,
) -> CampaignRunner:
    if definition.qualitative_review is None:
        raise RuntimeError(
            "granular campaigns require qualitative review; use "
            "granular_mean.definition:build_reviewed_definition"
        )
    root = Path(
        os.environ.get(
            "GRANULAR_MEAN_CAMPAIGN_ROOT",
            str(ROOT / "campaign-runs" / CAMPAIGN_VARIANT),
        )
    ).expanduser().resolve()
    max_parallel = _positive_integer_environment(
        "GRANULAR_MEAN_MAX_PARALLEL",
        DEFAULT_MAX_PARALLEL,
    )
    plan = CampaignPlan(
        campaign_id=CAMPAIGN_ID,
        root=root,
        trials=build_campaign_trials(),
        max_parallel=max_parallel,
        collection_retry_seconds=60,
        collection_max_attempts=5,
        max_pause_seconds=24 * 60 * 60,
        backend_image=(
            _optional_environment("GRANULAR_MEAN_AGENT_IMAGE")
            or DEFAULT_AGENT_IMAGE
        ),
        cpu_request=_resource_environment(
            "GRANULAR_MEAN_AGENT_CPU_REQUEST",
            DEFAULT_AGENT_CPU_REQUEST,
        ),
        cpu_limit=_resource_environment(
            "GRANULAR_MEAN_AGENT_CPU_LIMIT",
            DEFAULT_AGENT_CPU_LIMIT,
        ),
        memory_request=_resource_environment(
            "GRANULAR_MEAN_AGENT_MEMORY_REQUEST",
            DEFAULT_AGENT_MEMORY_REQUEST,
        ),
        memory_limit=_resource_environment(
            "GRANULAR_MEAN_AGENT_MEMORY_LIMIT",
            DEFAULT_AGENT_MEMORY_LIMIT,
        ),
    )
    profile = _sterling_profile(
        agent_image=plan.backend_image,
        max_parallel=max_parallel,
    )
    return CampaignRunner(
        definition,
        contract,
        plan,
        KubernetesBackend(profile),
        workload_factory=campaign_workload_factory,
    )
