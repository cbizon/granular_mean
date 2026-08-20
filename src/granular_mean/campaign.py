from __future__ import annotations

import os

from brunner import (
    BenchmarkDefinition,
    CampaignPlan,
    CampaignTrial,
    ClusterCampaign,
    ControllerProfile,
)
from brunner.backends import KubernetesProfile
from brunner.contract import OutputContract

from granular_mean.agent import (
    CAMPAIGN_CLAUDE_MODEL,
    CAMPAIGN_CODEX_MODELS,
    CAMPAIGN_EFFORT,
    azure_codex_settings,
    codex_environment_key,
)
from granular_mean.images import (
    DEFAULT_AGENT_IMAGE,
    DEFAULT_CONTROLLER_IMAGE,
    DEFAULT_SQUID_IMAGE,
    RETIRED_AGENT_IMAGE,
    RETIRED_AGENT_IMAGES,
    RETIRED_CONTROLLER_IMAGES,
    RETIRED_EVALUATOR_IMAGE,
    RETIRED_EVALUATOR_IMAGES,
    is_unpublished_image,
)


CAMPAIGN_VARIANT = "luna-terra-sol-haiku-low-cluster-v1"
CAMPAIGN_ID = f"granular-figure1-{CAMPAIGN_VARIANT}"
DEFAULT_MAX_PARALLEL = 1
DEFAULT_STERLING_NAMESPACE = "bizon"
DEFAULT_STERLING_NETWORK_ISOLATION_MODE = "controlled-egress"
DEFAULT_STERLING_STORAGE_SIZE = "20Gi"
DEFAULT_STERLING_STORAGE_CLASS = "basic"
DEFAULT_STERLING_REFERENCE_CLAIM = "granular-mean-reference-v1"
DEFAULT_STERLING_CODEX_SECRET = "balls-bench-codex-azure"
DEFAULT_STERLING_CLAUDE_SECRET = "balls-bench-claude-oauth"
DEFAULT_STERLING_CLAUDE_SECRET_KEY = "CLAUDE_CODE_OAUTH_TOKEN"
DEFAULT_STERLING_IMAGE_PULL_SECRET = "balls-bench-ghcr"
DEFAULT_AGENT_CPU_REQUEST = "2"
DEFAULT_AGENT_CPU_LIMIT = "8"
DEFAULT_AGENT_MEMORY_REQUEST = "8Gi"
DEFAULT_AGENT_MEMORY_LIMIT = "32Gi"
DEFAULT_AGENT_EPHEMERAL_STORAGE_REQUEST = "1Gi"
DEFAULT_AGENT_EPHEMERAL_STORAGE_LIMIT = "3Gi"
DEFAULT_CONTROLLER_CONTROL_STORAGE_SIZE = "20Gi"
DEFAULT_CONTROLLER_RESULTS_STORAGE_SIZE = "20Gi"
DEFAULT_CONTROLLER_CPU_REQUEST = "500m"
DEFAULT_CONTROLLER_CPU_LIMIT = "2"
DEFAULT_CONTROLLER_MEMORY_REQUEST = "1Gi"
DEFAULT_CONTROLLER_MEMORY_LIMIT = "4Gi"
DEFAULT_PREPARATION_CPU_REQUEST = "1"
DEFAULT_PREPARATION_CPU_LIMIT = "4"
DEFAULT_PREPARATION_MEMORY_REQUEST = "2Gi"
DEFAULT_PREPARATION_MEMORY_LIMIT = "8Gi"
DEFAULT_ASSESSMENT_CPU_REQUEST = "1"
DEFAULT_ASSESSMENT_CPU_LIMIT = "4"
DEFAULT_ASSESSMENT_MEMORY_REQUEST = "2Gi"
DEFAULT_ASSESSMENT_MEMORY_LIMIT = "8Gi"
DEFAULT_STERLING_ARTIFACT_CHUNK_BYTES = 1024 * 1024
DEFAULT_STERLING_ARTIFACT_CHUNK_ATTEMPTS = 10
DEFAULT_STERLING_COMMAND_TIMEOUT_SECONDS = 10 * 60
DEFAULT_STERLING_STAGING_TIMEOUT_SECONDS = 30 * 60
DEFAULT_STERLING_READER_TIMEOUT_SECONDS = 30 * 60
DEFAULT_CONTROLLER_PREPARATION_TIMEOUT_SECONDS = 30 * 60
DEFAULT_CONTROLLER_MAX_PUBLISHED_TRIAL_BYTES = 1024 * 1024 * 1024
NESTED_SANDBOX_BYPASS_ENVIRONMENT = (
    "GRANULAR_MEAN_CODEX_BYPASS_NESTED_SANDBOX"
)


def build_campaign_trials() -> tuple[CampaignTrial, ...]:
    codex_trials = tuple(
        CampaignTrial(
            test_id=f"codex-{model.replace('.', '-')}-low-r01",
            provider="codex",
            model=model,
            effort=CAMPAIGN_EFFORT,
            provider_id=settings.provider_id,
            provider_name=settings.provider_name,
            base_url=settings.base_url,
            environment_key=settings.environment_key,
        )
        for model in CAMPAIGN_CODEX_MODELS
        for settings in (azure_codex_settings(model, CAMPAIGN_EFFORT),)
    )
    return (
        *codex_trials,
        CampaignTrial(
            test_id="claude-haiku-4-5-low-r01",
            provider="claude",
            model=CAMPAIGN_CLAUDE_MODEL,
            effort=CAMPAIGN_EFFORT,
        ),
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


def _optional_environment(
    name: str,
    default: str | None = None,
) -> str | None:
    value = os.environ.get(name, default)
    return value.strip() if value and value.strip() else None


def _published_image(name: str, default: str) -> str:
    image = _resource_environment(name, default)
    if is_unpublished_image(image):
        raise RuntimeError(
            f"{name} still uses the unpublished placeholder; build and "
            "publish the image, then configure its immutable digest"
        )
    return image


def _provider_secret_mapping(
    environment_key: str,
) -> dict[str, dict[str, tuple[str, str]]]:
    return {
        "codex": {
            environment_key: (
                _resource_environment(
                    "GRANULAR_MEAN_STERLING_CODEX_SECRET",
                    DEFAULT_STERLING_CODEX_SECRET,
                ),
                _resource_environment(
                    "GRANULAR_MEAN_STERLING_CODEX_SECRET_KEY",
                    environment_key,
                ),
            )
        },
        "claude": {
            DEFAULT_STERLING_CLAUDE_SECRET_KEY: (
                _resource_environment(
                    "GRANULAR_MEAN_STERLING_CLAUDE_SECRET",
                    DEFAULT_STERLING_CLAUDE_SECRET,
                ),
                _resource_environment(
                    "GRANULAR_MEAN_STERLING_CLAUDE_SECRET_KEY",
                    DEFAULT_STERLING_CLAUDE_SECRET_KEY,
                ),
            )
        }
    }


def _reviewer_secret_mapping(
    environment_key: str,
) -> dict[str, dict[str, tuple[str, str]]]:
    return {
        "codex": _provider_secret_mapping(environment_key)["codex"],
    }


def build_campaign(
    definition: BenchmarkDefinition,
    contract: OutputContract,
) -> ClusterCampaign:
    del contract
    if definition.qualitative_review is None:
        raise RuntimeError(
            "granular campaigns require qualitative review; use "
            "granular_mean.definition:build_reviewed_definition"
        )

    max_parallel = _positive_integer_environment(
        "GRANULAR_MEAN_MAX_PARALLEL",
        DEFAULT_MAX_PARALLEL,
    )
    agent_image = _published_image(
        "GRANULAR_MEAN_AGENT_IMAGE",
        DEFAULT_AGENT_IMAGE,
    )
    controller_image = _published_image(
        "GRANULAR_MEAN_CONTROLLER_IMAGE",
        DEFAULT_CONTROLLER_IMAGE,
    )
    evaluator_image = definition.evaluation.image
    if evaluator_image is None or is_unpublished_image(evaluator_image):
        raise RuntimeError(
            "GRANULAR_MEAN_EVALUATOR_IMAGE still uses the unpublished "
            "placeholder; configure the immutable controller/evaluator digest"
        )
    if (
        agent_image in RETIRED_AGENT_IMAGES
        or controller_image in RETIRED_CONTROLLER_IMAGES
        or evaluator_image
        in (*RETIRED_EVALUATOR_IMAGES, *RETIRED_CONTROLLER_IMAGES)
    ):
        raise RuntimeError(
            "campaign images predate the cluster-resident controller "
            "protocol; rebuild both images from the current Brunner revision"
        )

    environment_key = codex_environment_key()
    provider_secret_mapping = _provider_secret_mapping(environment_key)
    namespace = _resource_environment(
        "GRANULAR_MEAN_STERLING_NAMESPACE",
        DEFAULT_STERLING_NAMESPACE,
    )
    pull_secret = _resource_environment(
        "GRANULAR_MEAN_STERLING_IMAGE_PULL_SECRET",
        DEFAULT_STERLING_IMAGE_PULL_SECRET,
    )
    storage_class = _optional_environment(
        "GRANULAR_MEAN_STERLING_STORAGE_CLASS",
        DEFAULT_STERLING_STORAGE_CLASS,
    )
    plan = CampaignPlan(
        campaign_id=CAMPAIGN_ID,
        trials=build_campaign_trials(),
        max_parallel=max_parallel,
        backend_image=agent_image,
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
        ephemeral_storage_request=_resource_environment(
            "GRANULAR_MEAN_AGENT_EPHEMERAL_STORAGE_REQUEST",
            DEFAULT_AGENT_EPHEMERAL_STORAGE_REQUEST,
        ),
        ephemeral_storage_limit=_resource_environment(
            "GRANULAR_MEAN_AGENT_EPHEMERAL_STORAGE_LIMIT",
            DEFAULT_AGENT_EPHEMERAL_STORAGE_LIMIT,
        ),
        provider_secret_environment=provider_secret_mapping,
        submission_retry_seconds=60,
        submission_max_attempts=5,
        collection_retry_seconds=60,
        collection_max_attempts=5,
        cleanup_retry_seconds=60,
        publication_retry_seconds=60,
        publication_max_attempts=5,
        infrastructure_max_restarts=5,
        max_pause_seconds=None,
        evaluation_timeout_seconds=definition.evaluation.timeout_seconds,
    )
    backend = KubernetesProfile(
        namespace=namespace,
        network_isolation_mode=_resource_environment(
            "GRANULAR_MEAN_STERLING_NETWORK_ISOLATION_MODE",
            DEFAULT_STERLING_NETWORK_ISOLATION_MODE,
        ),
        agent_image=agent_image,
        artifact_reader_image=controller_image,
        reference_claim_name=_resource_environment(
            "GRANULAR_MEAN_STERLING_REFERENCE_CLAIM",
            DEFAULT_STERLING_REFERENCE_CLAIM,
        ),
        storage_size=_resource_environment(
            "GRANULAR_MEAN_STERLING_STORAGE_SIZE",
            DEFAULT_STERLING_STORAGE_SIZE,
        ),
        storage_class_name=storage_class,
        image_pull_secrets=(pull_secret,),
        nonsecret_environment={
            NESTED_SANDBOX_BYPASS_ENVIRONMENT: "true",
        },
        proxy_image=_resource_environment(
            "GRANULAR_MEAN_STERLING_PROXY_IMAGE",
            DEFAULT_SQUID_IMAGE,
        ),
        max_parallel=max_parallel,
        staging_timeout_seconds=_positive_integer_environment(
            "GRANULAR_MEAN_STERLING_STAGING_TIMEOUT_SECONDS",
            DEFAULT_STERLING_STAGING_TIMEOUT_SECONDS,
        ),
        reader_timeout_seconds=_positive_integer_environment(
            "GRANULAR_MEAN_STERLING_READER_TIMEOUT_SECONDS",
            DEFAULT_STERLING_READER_TIMEOUT_SECONDS,
        ),
        command_timeout_seconds=_positive_integer_environment(
            "GRANULAR_MEAN_STERLING_COMMAND_TIMEOUT_SECONDS",
            DEFAULT_STERLING_COMMAND_TIMEOUT_SECONDS,
        ),
        artifact_chunk_bytes=_positive_integer_environment(
            "GRANULAR_MEAN_STERLING_ARTIFACT_CHUNK_BYTES",
            DEFAULT_STERLING_ARTIFACT_CHUNK_BYTES,
        ),
        artifact_chunk_attempts=_positive_integer_environment(
            "GRANULAR_MEAN_STERLING_ARTIFACT_CHUNK_ATTEMPTS",
            DEFAULT_STERLING_ARTIFACT_CHUNK_ATTEMPTS,
        ),
    )
    controller = ControllerProfile(
        namespace=namespace,
        image=controller_image,
        control_storage_size=_resource_environment(
            "GRANULAR_MEAN_CONTROLLER_CONTROL_STORAGE_SIZE",
            DEFAULT_CONTROLLER_CONTROL_STORAGE_SIZE,
        ),
        results_storage_size=_resource_environment(
            "GRANULAR_MEAN_CONTROLLER_RESULTS_STORAGE_SIZE",
            DEFAULT_CONTROLLER_RESULTS_STORAGE_SIZE,
        ),
        storage_class_name=storage_class,
        image_pull_secrets=(pull_secret,),
        poll_seconds=5,
        preparation_timeout_seconds=_positive_integer_environment(
            "GRANULAR_MEAN_CONTROLLER_PREPARATION_TIMEOUT_SECONDS",
            DEFAULT_CONTROLLER_PREPARATION_TIMEOUT_SECONDS,
        ),
        command_timeout_seconds=_positive_integer_environment(
            "GRANULAR_MEAN_STERLING_COMMAND_TIMEOUT_SECONDS",
            DEFAULT_STERLING_COMMAND_TIMEOUT_SECONDS,
        ),
        max_published_trial_bytes=_positive_integer_environment(
            "GRANULAR_MEAN_CONTROLLER_MAX_PUBLISHED_TRIAL_BYTES",
            DEFAULT_CONTROLLER_MAX_PUBLISHED_TRIAL_BYTES,
        ),
        controller_cpu_request=_resource_environment(
            "GRANULAR_MEAN_CONTROLLER_CPU_REQUEST",
            DEFAULT_CONTROLLER_CPU_REQUEST,
        ),
        controller_cpu_limit=_resource_environment(
            "GRANULAR_MEAN_CONTROLLER_CPU_LIMIT",
            DEFAULT_CONTROLLER_CPU_LIMIT,
        ),
        controller_memory_request=_resource_environment(
            "GRANULAR_MEAN_CONTROLLER_MEMORY_REQUEST",
            DEFAULT_CONTROLLER_MEMORY_REQUEST,
        ),
        controller_memory_limit=_resource_environment(
            "GRANULAR_MEAN_CONTROLLER_MEMORY_LIMIT",
            DEFAULT_CONTROLLER_MEMORY_LIMIT,
        ),
        preparation_cpu_request=_resource_environment(
            "GRANULAR_MEAN_PREPARATION_CPU_REQUEST",
            DEFAULT_PREPARATION_CPU_REQUEST,
        ),
        preparation_cpu_limit=_resource_environment(
            "GRANULAR_MEAN_PREPARATION_CPU_LIMIT",
            DEFAULT_PREPARATION_CPU_LIMIT,
        ),
        preparation_memory_request=_resource_environment(
            "GRANULAR_MEAN_PREPARATION_MEMORY_REQUEST",
            DEFAULT_PREPARATION_MEMORY_REQUEST,
        ),
        preparation_memory_limit=_resource_environment(
            "GRANULAR_MEAN_PREPARATION_MEMORY_LIMIT",
            DEFAULT_PREPARATION_MEMORY_LIMIT,
        ),
        assessment_cpu_request=_resource_environment(
            "GRANULAR_MEAN_ASSESSMENT_CPU_REQUEST",
            DEFAULT_ASSESSMENT_CPU_REQUEST,
        ),
        assessment_cpu_limit=_resource_environment(
            "GRANULAR_MEAN_ASSESSMENT_CPU_LIMIT",
            DEFAULT_ASSESSMENT_CPU_LIMIT,
        ),
        assessment_memory_request=_resource_environment(
            "GRANULAR_MEAN_ASSESSMENT_MEMORY_REQUEST",
            DEFAULT_ASSESSMENT_MEMORY_REQUEST,
        ),
        assessment_memory_limit=_resource_environment(
            "GRANULAR_MEAN_ASSESSMENT_MEMORY_LIMIT",
            DEFAULT_ASSESSMENT_MEMORY_LIMIT,
        ),
        reviewer_secret_environment=_reviewer_secret_mapping(
            environment_key
        ),
    )
    campaign = ClusterCampaign(
        plan=plan,
        backend=backend,
        controller=controller,
    )
    campaign.validate()
    return campaign
