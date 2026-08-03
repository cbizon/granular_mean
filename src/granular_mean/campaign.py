from __future__ import annotations

import os
import sys
from dataclasses import replace
from pathlib import Path

from brunner import (
    BenchmarkDefinition,
    CampaignPlan,
    CampaignRunner,
    CampaignTrial,
)
from brunner.backends import LocalBackend, WorkloadSpec
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


def build_campaign_trials() -> tuple[CampaignTrial, ...]:
    environment_key = codex_environment_key()
    return tuple(
        CampaignTrial(
            test_id=f"codex-gpt-5-6-sol-{effort}-r01",
            provider="codex",
            model=CODEX_MODEL,
            effort=effort,
            environment_keys=(environment_key,),
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
    backend_trial = (
        trial if backend_name == "local" else Path("/brunner/trial")
    )
    python = sys.executable if backend_name == "local" else "python"
    return replace(
        workload,
        command=(
            python,
            "-m",
            "granular_mean.agent",
            str(backend_trial),
        ),
    )


def build_campaign(
    definition: BenchmarkDefinition,
    contract: OutputContract,
) -> CampaignRunner:
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
    )
    return CampaignRunner(
        definition,
        contract,
        plan,
        LocalBackend(max_parallel=max_parallel),
        workload_factory=campaign_workload_factory,
    )
