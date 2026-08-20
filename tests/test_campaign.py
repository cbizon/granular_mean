from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from brunner import ClusterCampaign
from brunner.backends.kubernetes import render_job
from brunner.campaign import default_workload_factory
from brunner.cluster import render_cluster_resources
from brunner.contract import load_output_contract
from brunner.trial import TrialIdentity

from granular_mean import agent as agent_module
from granular_mean.agent import (
    CAMPAIGN_CLAUDE_MODEL,
    CAMPAIGN_CODEX_MODELS,
    CAMPAIGN_EFFORT,
    CAMPAIGN_EFFORTS,
    CODEX_MODEL,
    DEFAULT_CODEX_BASE_URL,
    azure_codex_settings,
    provider_settings,
)
from granular_mean.campaign import (
    CAMPAIGN_ID,
    DEFAULT_AGENT_CPU_LIMIT,
    DEFAULT_AGENT_CPU_REQUEST,
    DEFAULT_AGENT_EPHEMERAL_STORAGE_LIMIT,
    DEFAULT_AGENT_EPHEMERAL_STORAGE_REQUEST,
    DEFAULT_AGENT_MEMORY_LIMIT,
    DEFAULT_AGENT_MEMORY_REQUEST,
    DEFAULT_ASSESSMENT_CPU_LIMIT,
    DEFAULT_ASSESSMENT_CPU_REQUEST,
    DEFAULT_ASSESSMENT_MEMORY_LIMIT,
    DEFAULT_ASSESSMENT_MEMORY_REQUEST,
    DEFAULT_CONTROLLER_CONTROL_STORAGE_SIZE,
    DEFAULT_CONTROLLER_RESULTS_STORAGE_SIZE,
    DEFAULT_MAX_PARALLEL,
    DEFAULT_STERLING_ARTIFACT_CHUNK_ATTEMPTS,
    DEFAULT_STERLING_ARTIFACT_CHUNK_BYTES,
    DEFAULT_STERLING_CLAUDE_SECRET,
    DEFAULT_STERLING_CLAUDE_SECRET_KEY,
    DEFAULT_STERLING_CODEX_SECRET,
    DEFAULT_STERLING_COMMAND_TIMEOUT_SECONDS,
    DEFAULT_STERLING_IMAGE_PULL_SECRET,
    DEFAULT_STERLING_NAMESPACE,
    DEFAULT_STERLING_NETWORK_ISOLATION_MODE,
    DEFAULT_STERLING_REFERENCE_CLAIM,
    DEFAULT_STERLING_STORAGE_CLASS,
    NESTED_SANDBOX_BYPASS_ENVIRONMENT,
    build_campaign,
    build_campaign_trials,
)
from granular_mean.codex_wrapper import (
    prepare_arguments,
    strict_output_schema,
)
from granular_mean.definition import (
    DEFAULT_EVALUATOR_CPU_LIMIT,
    DEFAULT_EVALUATOR_CPU_REQUEST,
    DEFAULT_EVALUATOR_EPHEMERAL_STORAGE_LIMIT,
    DEFAULT_EVALUATOR_EPHEMERAL_STORAGE_REQUEST,
    DEFAULT_EVALUATOR_MEMORY_LIMIT,
    DEFAULT_EVALUATOR_MEMORY_REQUEST,
    DEFAULT_REVIEWER_EFFORT,
    DEFAULT_REVIEWER_MAX_ATTEMPTS,
    DEFAULT_REVIEWER_MODEL,
    DEFAULT_REVIEWER_RETRY_INITIAL_SECONDS,
    DEFAULT_REVIEWER_RETRY_MAX_SECONDS,
    DEFAULT_REVIEWER_TIMEOUT_SECONDS,
    V2_CAMPAIGN_REVIEW_CONTRACT_SHA256,
    build_definition,
    build_reviewed_definition,
    build_v2_campaign_recovery_definition,
)
from granular_mean.images import (
    DEFAULT_AGENT_IMAGE,
    DEFAULT_CONTROLLER_IMAGE,
    DEFAULT_EVALUATOR_IMAGE,
    DEFAULT_REFERENCE_UPLOAD_IMAGE,
    DEFAULT_SQUID_IMAGE,
    RETIRED_AGENT_IMAGE,
    RETIRED_AGENT_IMAGES,
    RETIRED_EVALUATOR_IMAGE,
    RETIRED_EVALUATOR_IMAGES,
    is_unpublished_image,
)


AZURE_CODEX_ARGUMENTS = [
    "-c",
    'model_provider="azure"',
    "-c",
    'model_providers.azure.name="Azure OpenAI"',
    "-c",
    (
        "model_providers.azure.base_url="
        '"https://renci-analytics.openai.azure.com/openai/v1/"'
    ),
    "-c",
    'model_providers.azure.env_key="AZURE_OPENAI_API_KEY"',
    "-c",
    "model_providers.azure.supports_websockets=false",
]
TEST_AGENT_IMAGE = "ghcr.io/example/agent@sha256:" + "a" * 64
TEST_CONTROLLER_IMAGE = "ghcr.io/example/controller@sha256:" + "b" * 64


def _set_published_images(monkeypatch) -> None:
    monkeypatch.setenv("GRANULAR_MEAN_AGENT_IMAGE", TEST_AGENT_IMAGE)
    monkeypatch.setenv(
        "GRANULAR_MEAN_CONTROLLER_IMAGE",
        TEST_CONTROLLER_IMAGE,
    )
    monkeypatch.setenv(
        "GRANULAR_MEAN_EVALUATOR_IMAGE",
        TEST_CONTROLLER_IMAGE,
    )


def _campaign(monkeypatch) -> ClusterCampaign:
    _set_published_images(monkeypatch)
    definition = build_reviewed_definition()
    contract = load_output_contract(definition.contract_path)
    return build_campaign(definition, contract)


def test_campaign_runs_selected_models_at_low_effort() -> None:
    trials = build_campaign_trials()

    assert tuple(trial.model for trial in trials) == (
        *CAMPAIGN_CODEX_MODELS,
        CAMPAIGN_CLAUDE_MODEL,
    )
    assert {trial.effort for trial in trials} == {CAMPAIGN_EFFORT}
    assert tuple(trial.provider for trial in trials) == (
        "codex",
        "codex",
        "codex",
        "claude",
    )
    codex_trials = trials[:3]
    assert {trial.provider_id for trial in codex_trials} == {"azure"}
    assert {trial.base_url for trial in codex_trials} == {
        DEFAULT_CODEX_BASE_URL
    }
    assert {trial.environment_key for trial in codex_trials} == {
        "AZURE_OPENAI_API_KEY"
    }
    assert trials[3].provider_id is None
    assert len({trial.test_id for trial in trials}) == 4


def test_remote_agent_delegates_to_brunner_protocol(
    monkeypatch,
    tmp_path,
) -> None:
    called = False

    def fake_brunner_agent_main() -> None:
        nonlocal called
        called = True
        assert sys.argv == [
            "granular-mean-agent",
            str(tmp_path),
        ]

    monkeypatch.setattr(
        agent_module,
        "brunner_agent_main",
        fake_brunner_agent_main,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["granular-mean-agent", str(tmp_path)],
    )

    assert agent_module.main() == 0
    assert called is True


def test_campaign_uses_sterling_backend_and_configured_parallelism(
    monkeypatch,
) -> None:
    monkeypatch.setenv("GRANULAR_MEAN_MAX_PARALLEL", "2")
    campaign = _campaign(monkeypatch)

    assert campaign.plan.campaign_id == CAMPAIGN_ID
    assert campaign.plan.max_parallel == 2
    assert campaign.plan.backend_image == TEST_AGENT_IMAGE
    assert campaign.plan.provider_executable is None
    assert campaign.plan.max_pause_seconds is None
    assert campaign.backend.namespace == DEFAULT_STERLING_NAMESPACE
    assert (
        campaign.backend.network_isolation_mode
        == DEFAULT_STERLING_NETWORK_ISOLATION_MODE
    )
    assert campaign.backend.agent_image == TEST_AGENT_IMAGE
    assert campaign.backend.artifact_reader_image == TEST_CONTROLLER_IMAGE
    assert (
        campaign.backend.reference_claim_name
        == DEFAULT_STERLING_REFERENCE_CLAIM
    )
    assert campaign.backend.proxy_image == DEFAULT_SQUID_IMAGE
    assert campaign.backend.storage_class_name == DEFAULT_STERLING_STORAGE_CLASS
    assert campaign.backend.image_pull_secrets == (
        DEFAULT_STERLING_IMAGE_PULL_SECRET,
    )
    assert campaign.backend.max_parallel == 2
    assert campaign.backend.secret_environment == {}
    assert campaign.backend.nonsecret_environment == {
        NESTED_SANDBOX_BYPASS_ENVIRONMENT: "true",
    }
    assert campaign.controller.namespace == DEFAULT_STERLING_NAMESPACE
    assert campaign.controller.image == TEST_CONTROLLER_IMAGE
    assert (
        campaign.controller.control_storage_size
        == DEFAULT_CONTROLLER_CONTROL_STORAGE_SIZE
    )
    assert (
        campaign.controller.results_storage_size
        == DEFAULT_CONTROLLER_RESULTS_STORAGE_SIZE
    )
    expected_secret = {
        "codex": {
            "AZURE_OPENAI_API_KEY": (
                DEFAULT_STERLING_CODEX_SECRET,
                "AZURE_OPENAI_API_KEY",
            )
        },
        "claude": {
            DEFAULT_STERLING_CLAUDE_SECRET_KEY: (
                DEFAULT_STERLING_CLAUDE_SECRET,
                DEFAULT_STERLING_CLAUDE_SECRET_KEY,
            )
        },
    }
    assert campaign.plan.provider_secret_environment == expected_secret
    assert campaign.controller.reviewer_secret_environment == {
        "codex": expected_secret["codex"],
    }


def test_campaign_accepts_artifact_stream_overrides(
    monkeypatch,
) -> None:
    _set_published_images(monkeypatch)
    monkeypatch.setenv(
        "GRANULAR_MEAN_STERLING_ARTIFACT_CHUNK_BYTES",
        str(512 * 1024),
    )
    monkeypatch.setenv(
        "GRANULAR_MEAN_STERLING_ARTIFACT_CHUNK_ATTEMPTS",
        "7",
    )
    monkeypatch.setenv(
        "GRANULAR_MEAN_STERLING_COMMAND_TIMEOUT_SECONDS",
        "900",
    )
    definition = build_reviewed_definition()
    contract = load_output_contract(definition.contract_path)

    campaign = build_campaign(definition, contract)

    assert campaign.backend.artifact_chunk_bytes == 512 * 1024
    assert campaign.backend.artifact_chunk_attempts == 7
    assert campaign.backend.command_timeout_seconds == 900
    assert campaign.controller.command_timeout_seconds == 900


def test_campaign_workload_uses_containerized_azure_launcher(
    monkeypatch,
    tmp_path,
) -> None:
    campaign = _campaign(monkeypatch)
    definition = build_reviewed_definition()
    campaign_trial = campaign.plan.trials[0]
    trial = tmp_path / campaign_trial.test_id

    workload = default_workload_factory(
        trial,
        campaign_trial,
        campaign.plan,
        definition,
        "kubernetes",
    )

    assert workload.command == (
        "python",
        "-m",
        "brunner.agent_cli",
        "/brunner/trial",
        "--provider-id",
        "azure",
        "--provider-name",
        "Azure OpenAI",
        "--environment-key",
        "AZURE_OPENAI_API_KEY",
        "--base-url",
        DEFAULT_CODEX_BASE_URL,
    )
    assert workload.image == TEST_AGENT_IMAGE
    assert workload.secret_environment == {
        "AZURE_OPENAI_API_KEY": (
            DEFAULT_STERLING_CODEX_SECRET,
            "AZURE_OPENAI_API_KEY",
        )
    }
    assert workload.evaluation is not None
    assert workload.evaluation.image == TEST_CONTROLLER_IMAGE
    assert workload.evaluation.command == ("granular-mean-evaluator",)
    assert workload.cpu_request == DEFAULT_AGENT_CPU_REQUEST
    assert workload.cpu_limit == DEFAULT_AGENT_CPU_LIMIT
    assert workload.memory_request == DEFAULT_AGENT_MEMORY_REQUEST
    assert workload.memory_limit == DEFAULT_AGENT_MEMORY_LIMIT
    assert (
        workload.ephemeral_storage_request
        == DEFAULT_AGENT_EPHEMERAL_STORAGE_REQUEST
    )
    assert (
        workload.ephemeral_storage_limit
        == DEFAULT_AGENT_EPHEMERAL_STORAGE_LIMIT
    )

    job = render_job(
        "granular-test",
        "granular-test-data",
        workload,
        campaign.backend,
        {},
        proxy_url="http://10.96.4.12:3128",
    )
    assert job["metadata"]["annotations"][
        "dev.brunner/network-isolation-mode"
    ] == DEFAULT_STERLING_NETWORK_ISOLATION_MODE
    pod = job["spec"]["template"]["spec"]
    agent = pod["initContainers"][0]
    evaluator = pod["containers"][0]
    assert agent["resources"]["requests"] == {
        "cpu": DEFAULT_AGENT_CPU_REQUEST,
        "memory": DEFAULT_AGENT_MEMORY_REQUEST,
        "ephemeral-storage": DEFAULT_AGENT_EPHEMERAL_STORAGE_REQUEST,
    }
    assert evaluator["resources"]["requests"] == {
        "cpu": DEFAULT_EVALUATOR_CPU_REQUEST,
        "memory": DEFAULT_EVALUATOR_MEMORY_REQUEST,
        "ephemeral-storage": DEFAULT_EVALUATOR_EPHEMERAL_STORAGE_REQUEST,
    }
    assert evaluator["resources"]["limits"] == {
        "cpu": DEFAULT_EVALUATOR_CPU_LIMIT,
        "memory": DEFAULT_EVALUATOR_MEMORY_LIMIT,
        "ephemeral-storage": DEFAULT_EVALUATOR_EPHEMERAL_STORAGE_LIMIT,
    }
    agent_environment = {item["name"] for item in agent["env"]}
    evaluator_environment = {item["name"] for item in evaluator["env"]}
    assert "AZURE_OPENAI_API_KEY" in agent_environment
    assert "HTTPS_PROXY" in agent_environment
    assert "AZURE_OPENAI_API_KEY" not in evaluator_environment
    assert "HTTPS_PROXY" not in evaluator_environment
    assert all(
        mount["name"] != "reference"
        for mount in agent["volumeMounts"]
    )
    reference_mount = next(
        mount
        for mount in evaluator["volumeMounts"]
        if mount["name"] == "reference"
    )
    assert reference_mount["readOnly"] is True


def test_haiku_workload_uses_claude_and_only_its_secret(
    monkeypatch,
    tmp_path,
) -> None:
    campaign = _campaign(monkeypatch)
    definition = build_reviewed_definition()
    campaign_trial = campaign.plan.trials[-1]

    workload = default_workload_factory(
        tmp_path / campaign_trial.test_id,
        campaign_trial,
        campaign.plan,
        definition,
        "kubernetes",
    )

    assert campaign_trial.provider == "claude"
    assert workload.command == (
        "python",
        "-m",
        "brunner.agent_cli",
        "/brunner/trial",
    )
    assert workload.secret_environment == {
        DEFAULT_STERLING_CLAUDE_SECRET_KEY: (
            DEFAULT_STERLING_CLAUDE_SECRET,
            DEFAULT_STERLING_CLAUDE_SECRET_KEY,
        )
    }


def test_cluster_resources_run_the_orchestrator_in_kubernetes(
    monkeypatch,
) -> None:
    campaign = _campaign(monkeypatch)
    definition = build_reviewed_definition()

    rendered = render_cluster_resources(
        definition,
        campaign,
        benchmark_ref="granular_mean.definition:build_reviewed_definition",
        campaign_ref="granular_mean.campaign",
    )
    by_kind: dict[str, list[dict]] = {}
    for resource in rendered:
        by_kind.setdefault(resource["kind"], []).append(resource)

    assert len(by_kind["PersistentVolumeClaim"]) == 2
    assert all(
        item["spec"]["accessModes"] == ["ReadWriteMany"]
        for item in by_kind["PersistentVolumeClaim"]
    )
    preparation = by_kind["Job"][0]["spec"]["template"]["spec"]
    deployment = by_kind["Deployment"][0]["spec"]["template"]["spec"]
    assert preparation["automountServiceAccountToken"] is False
    assert deployment["automountServiceAccountToken"] is True
    assert preparation["containers"][0]["image"] == TEST_CONTROLLER_IMAGE
    assert deployment["containers"][0]["image"] == TEST_CONTROLLER_IMAGE
    assert deployment["containers"][0]["resources"]["requests"] == {
        "cpu": "500m",
        "memory": "1Gi",
    }
    assert campaign.controller.assessment_cpu_request == (
        DEFAULT_ASSESSMENT_CPU_REQUEST
    )
    assert campaign.controller.assessment_cpu_limit == (
        DEFAULT_ASSESSMENT_CPU_LIMIT
    )
    assert campaign.controller.assessment_memory_request == (
        DEFAULT_ASSESSMENT_MEMORY_REQUEST
    )
    assert campaign.controller.assessment_memory_limit == (
        DEFAULT_ASSESSMENT_MEMORY_LIMIT
    )


def test_campaign_workload_accepts_resource_overrides(
    monkeypatch,
) -> None:
    _set_published_images(monkeypatch)
    monkeypatch.setenv("GRANULAR_MEAN_AGENT_CPU_REQUEST", "1500m")
    monkeypatch.setenv("GRANULAR_MEAN_AGENT_CPU_LIMIT", "6")
    monkeypatch.setenv("GRANULAR_MEAN_AGENT_MEMORY_REQUEST", "12Gi")
    monkeypatch.setenv("GRANULAR_MEAN_AGENT_MEMORY_LIMIT", "24Gi")
    monkeypatch.setenv(
        "GRANULAR_MEAN_AGENT_EPHEMERAL_STORAGE_REQUEST",
        "750Mi",
    )
    monkeypatch.setenv(
        "GRANULAR_MEAN_AGENT_EPHEMERAL_STORAGE_LIMIT",
        "2Gi",
    )
    monkeypatch.setenv(
        "GRANULAR_MEAN_STERLING_IMAGE_PULL_SECRET",
        "custom-pull-secret",
    )
    definition = build_reviewed_definition()
    contract = load_output_contract(definition.contract_path)

    campaign = build_campaign(definition, contract)

    assert campaign.plan.cpu_request == "1500m"
    assert campaign.plan.cpu_limit == "6"
    assert campaign.plan.memory_request == "12Gi"
    assert campaign.plan.memory_limit == "24Gi"
    assert campaign.plan.ephemeral_storage_request == "750Mi"
    assert campaign.plan.ephemeral_storage_limit == "2Gi"
    assert campaign.backend.image_pull_secrets == ("custom-pull-secret",)
    assert campaign.controller.image_pull_secrets == ("custom-pull-secret",)


def test_campaign_rejects_retired_published_images(
    monkeypatch,
) -> None:
    monkeypatch.setenv("GRANULAR_MEAN_AGENT_IMAGE", RETIRED_AGENT_IMAGE)
    monkeypatch.setenv(
        "GRANULAR_MEAN_CONTROLLER_IMAGE",
        TEST_CONTROLLER_IMAGE,
    )
    monkeypatch.setenv(
        "GRANULAR_MEAN_EVALUATOR_IMAGE",
        RETIRED_EVALUATOR_IMAGE,
    )
    definition = build_reviewed_definition()
    contract = load_output_contract(definition.contract_path)

    with pytest.raises(RuntimeError, match="predate the cluster-resident"):
        build_campaign(definition, contract)


def test_campaign_rejects_previous_broken_agent_image(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "GRANULAR_MEAN_AGENT_IMAGE",
        RETIRED_AGENT_IMAGES[1],
    )
    monkeypatch.setenv(
        "GRANULAR_MEAN_CONTROLLER_IMAGE",
        TEST_CONTROLLER_IMAGE,
    )
    monkeypatch.setenv(
        "GRANULAR_MEAN_EVALUATOR_IMAGE",
        TEST_CONTROLLER_IMAGE,
    )
    definition = build_reviewed_definition()
    contract = load_output_contract(definition.contract_path)

    with pytest.raises(RuntimeError, match="predate the cluster-resident"):
        build_campaign(definition, contract)


def test_campaign_rejects_pre_controller_evaluator_image(
    monkeypatch,
) -> None:
    monkeypatch.setenv("GRANULAR_MEAN_AGENT_IMAGE", TEST_AGENT_IMAGE)
    monkeypatch.setenv(
        "GRANULAR_MEAN_CONTROLLER_IMAGE",
        RETIRED_EVALUATOR_IMAGES[1],
    )
    monkeypatch.setenv(
        "GRANULAR_MEAN_EVALUATOR_IMAGE",
        RETIRED_EVALUATOR_IMAGES[1],
    )
    definition = build_reviewed_definition()
    contract = load_output_contract(definition.contract_path)

    with pytest.raises(RuntimeError, match="predate the cluster-resident"):
        build_campaign(definition, contract)


def test_campaign_defaults_to_published_images(
    monkeypatch,
) -> None:
    monkeypatch.delenv("GRANULAR_MEAN_AGENT_IMAGE", raising=False)
    monkeypatch.delenv("GRANULAR_MEAN_CONTROLLER_IMAGE", raising=False)
    monkeypatch.delenv("GRANULAR_MEAN_EVALUATOR_IMAGE", raising=False)
    definition = build_reviewed_definition()
    contract = load_output_contract(definition.contract_path)

    campaign = build_campaign(definition, contract)

    assert campaign.plan.backend_image == DEFAULT_AGENT_IMAGE
    assert campaign.backend.agent_image == DEFAULT_AGENT_IMAGE
    assert campaign.backend.artifact_reader_image == DEFAULT_CONTROLLER_IMAGE
    assert campaign.controller.image == DEFAULT_CONTROLLER_IMAGE
    assert definition.evaluation.image == DEFAULT_EVALUATOR_IMAGE


def test_campaign_accepts_strict_dedicated_namespace(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "GRANULAR_MEAN_STERLING_NAMESPACE",
        "benchmark-test",
    )
    monkeypatch.setenv(
        "GRANULAR_MEAN_STERLING_NETWORK_ISOLATION_MODE",
        "strict",
    )
    campaign = _campaign(monkeypatch)

    assert campaign.backend.namespace == "benchmark-test"
    assert campaign.controller.namespace == "benchmark-test"
    assert campaign.backend.network_isolation_mode == "strict"


def test_images_pin_current_brunner_build() -> None:
    root = Path(__file__).parents[1]
    agent = (root / "containers" / "agent.Dockerfile").read_text()
    controller = (
        root / "containers" / "controller.Dockerfile"
    ).read_text()
    dockerignore = (root / ".dockerignore").read_text().splitlines()

    assert "ARG BRUNNER_REVISION\n" in agent
    assert "ARG BRUNNER_REVISION\n" in controller
    assert "ARG CODEX_VERSION\n" in agent
    assert "ARG CLAUDE_CODE_VERSION\n" in agent
    assert "ARG CODEX_VERSION\n" in controller
    assert "ARG KUBECTL_VERSION\n" in controller
    assert 'RUN test -n "${BRUNNER_REVISION}"' in agent
    assert 'RUN test -n "${BRUNNER_REVISION}"' in controller
    assert "COPY --from=brunner" in agent
    assert "COPY --from=brunner" in controller
    assert "COPY challenge/" not in agent
    assert "granular_mean/evaluator.py" not in agent
    assert "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" in agent
    assert "/usr/local/bin/claude" in agent
    assert "COPY challenge/" in controller
    assert "COPY reference/manifest.json" in controller
    assert "COPY reference/paper/" in controller
    assert "/bin/linux/${TARGETARCH}/kubectl" in controller
    assert "GRANULAR_MEAN_CODEX_BYPASS_NESTED_SANDBOX=true" in controller
    assert "reference/generated" in dockerignore
    assert "challenge" not in dockerignore
    assert "reference" not in dockerignore
    assert not is_unpublished_image(DEFAULT_AGENT_IMAGE)
    assert not is_unpublished_image(DEFAULT_CONTROLLER_IMAGE)
    assert DEFAULT_EVALUATOR_IMAGE == DEFAULT_CONTROLLER_IMAGE


def test_reference_upload_is_network_isolated() -> None:
    root = Path(__file__).parents[1]
    pvc = (root / "deploy" / "sterling-reference-pvc.yaml").read_text()
    policy = (
        root / "deploy" / "sterling-reference-network-policy.yaml"
    ).read_text()
    upload = (root / "deploy" / "sterling-reference-upload.yaml").read_text()

    assert "policyTypes:\n    - Ingress\n    - Egress" in policy
    assert "ingress: []" in policy
    assert "egress: []" in policy
    assert "automountServiceAccountToken: false" in upload
    assert f"image: {DEFAULT_REFERENCE_UPLOAD_IMAGE}" in upload
    assert "imagePullSecrets:\n    - name: balls-bench-ghcr" in upload
    assert "namespace:" not in pvc
    assert "namespace:" not in policy
    assert "namespace:" not in upload


def test_campaign_launcher_only_supervises_brunner() -> None:
    root = Path(__file__).parents[1]
    launcher = (root / "scripts" / "manage-campaign.sh").read_text()

    assert "campaign-submit" in launcher
    assert "campaign-status" in launcher
    assert "campaign-monitor" in launcher
    assert "campaign-retrieve" in launcher
    assert "campaign-delete" in launcher
    assert "launchctl" not in launcher
    assert "campaign-run" not in launcher
    assert "campaign-init" not in launcher
    assert "trial-assess" not in launcher
    assert "campaign-step" not in launcher


def test_definition_requires_image_backed_sterling_evaluation() -> None:
    definition = build_definition()

    assert definition.evaluation.image == DEFAULT_EVALUATOR_IMAGE
    assert definition.evaluation.command == ("granular-mean-evaluator",)
    assert definition.evaluation.cpu_request == DEFAULT_EVALUATOR_CPU_REQUEST
    assert definition.evaluation.cpu_limit == DEFAULT_EVALUATOR_CPU_LIMIT
    assert (
        definition.evaluation.memory_request
        == DEFAULT_EVALUATOR_MEMORY_REQUEST
    )
    assert definition.evaluation.memory_limit == DEFAULT_EVALUATOR_MEMORY_LIMIT
    assert definition.reference is not None
    assert definition.reference.validate_command == (
        "granular-reference-validate",
    )


def test_definition_excludes_raw_submission_trajectories() -> None:
    definition = build_definition()

    assert definition.artifacts.collect_evaluated_artifacts is False
    assert definition.artifacts.groups["raw-trajectories"] == (
        "workspace/submission/*.npz",
        "workspace/submission/**/*.npz",
    )
    assert definition.artifacts.max_collection_bytes == 1024 * 1024 * 1024


def test_prompt_states_the_full_execution_allowance() -> None:
    root = Path(__file__).parents[1]
    prompt = (root / "challenge" / "PROMPT.md").read_text()

    assert "up to 48 hours of wall-clock time" in prompt


@pytest.mark.parametrize("model", CAMPAIGN_CODEX_MODELS)
def test_provider_settings_pin_codex_models_to_low_and_azure(
    model: str,
) -> None:
    settings = provider_settings(
        TrialIdentity(
            test_id=f"{model}-low",
            provider="codex",
            model=model,
            effort=CAMPAIGN_EFFORT,
        )
    )

    assert settings.allowed_efforts == CAMPAIGN_EFFORTS
    assert settings.provider_id == "azure"
    assert settings.base_url == DEFAULT_CODEX_BASE_URL
    assert settings.environment_key == "AZURE_OPENAI_API_KEY"


def test_provider_settings_accept_haiku_at_low() -> None:
    settings = provider_settings(
        TrialIdentity(
            test_id="haiku-low",
            provider="claude",
            model=CAMPAIGN_CLAUDE_MODEL,
            effort=CAMPAIGN_EFFORT,
        )
    )

    assert settings.provider == "claude"
    assert settings.allowed_efforts == CAMPAIGN_EFFORTS
    assert settings.provider_id is None


def test_codex_wrapper_bypasses_initial_nested_sandbox(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        NESTED_SANDBOX_BYPASS_ENVIRONMENT,
        "true",
    )

    arguments = prepare_arguments(
        [
            "exec",
            "--json",
            "--sandbox",
            "workspace-write",
            "--model",
            CODEX_MODEL,
        ]
    )

    assert arguments == [
        "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "--json",
        *AZURE_CODEX_ARGUMENTS,
        "--model",
        CODEX_MODEL,
    ]


def test_codex_wrapper_bypasses_resumed_nested_sandbox(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        NESTED_SANDBOX_BYPASS_ENVIRONMENT,
        "true",
    )

    arguments = prepare_arguments(
        [
            "exec",
            "resume",
            "--json",
            "--last",
            "-",
        ]
    )

    assert arguments == [
        "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "resume",
        "--json",
        "--last",
        *AZURE_CODEX_ARGUMENTS,
        "-",
    ]


def test_codex_wrapper_keeps_local_review_sandbox(
    monkeypatch,
) -> None:
    monkeypatch.delenv(
        NESTED_SANDBOX_BYPASS_ENVIRONMENT,
        raising=False,
    )

    arguments = prepare_arguments(
        [
            "exec",
            "--json",
            "--sandbox",
            "read-only",
            "--model",
            CODEX_MODEL,
        ]
    )

    assert arguments == [
        "exec",
        "--json",
        "--sandbox",
        "read-only",
        *AZURE_CODEX_ARGUMENTS,
        "--model",
        CODEX_MODEL,
    ]


def test_codex_wrapper_bypasses_initial_command_without_sandbox(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        NESTED_SANDBOX_BYPASS_ENVIRONMENT,
        "true",
    )

    arguments = prepare_arguments(["exec", "--json"])

    assert arguments == [
        "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "--json",
        *AZURE_CODEX_ARGUMENTS,
    ]


def test_codex_wrapper_accepts_brunner_bypass_flag(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        NESTED_SANDBOX_BYPASS_ENVIRONMENT,
        "true",
    )

    arguments = prepare_arguments(
        [
            "exec",
            "--json",
            "--dangerously-bypass-approvals-and-sandbox",
            "--model",
            CODEX_MODEL,
        ]
    )

    assert arguments == [
        "exec",
        "--json",
        "--dangerously-bypass-approvals-and-sandbox",
        *AZURE_CODEX_ARGUMENTS,
        "--model",
        CODEX_MODEL,
    ]


def test_reviewed_definition_defaults_to_azure_sol_xhigh() -> None:
    definition = build_reviewed_definition()
    review = definition.qualitative_review

    assert review is not None
    assert review.reviewer == azure_codex_settings(
        DEFAULT_REVIEWER_MODEL,
        DEFAULT_REVIEWER_EFFORT,
    )
    assert review.reviewer_executable == "granular-mean-codex"
    assert review.required is True
    assert review.timeout_seconds == DEFAULT_REVIEWER_TIMEOUT_SECONDS
    assert review.max_attempts == DEFAULT_REVIEWER_MAX_ATTEMPTS
    assert (
        review.retry_initial_seconds
        == DEFAULT_REVIEWER_RETRY_INITIAL_SECONDS
    )
    assert review.retry_max_seconds == DEFAULT_REVIEWER_RETRY_MAX_SECONDS
    assert "workspace/**/*.py" in review.trial_evidence_paths


def test_v2_campaign_recovery_definition_preserves_review_contract() -> None:
    with pytest.raises(
        RuntimeError,
        match="v2 campaign recovery assessment contract drifted",
    ):
        build_v2_campaign_recovery_definition()

    assert V2_CAMPAIGN_REVIEW_CONTRACT_SHA256 == (
        "29b75a2ecc9d4381e01b02fed97e11869c7f8c81ce3f27e742857ca2b3f03c6b"
    )


def test_campaign_rejects_unreviewed_definition(
    monkeypatch,
) -> None:
    _set_published_images(monkeypatch)
    definition = build_definition()
    contract = load_output_contract(definition.contract_path)

    with pytest.raises(
        RuntimeError,
        match="campaigns require qualitative review",
    ):
        build_campaign(definition, contract)


@pytest.mark.parametrize("effort", [None, "medium", "invalid"])
def test_provider_settings_reject_unsupported_effort(
    effort: str | None,
) -> None:
    with pytest.raises(ValueError, match="effort must be 'low'"):
        provider_settings(
            TrialIdentity(
                test_id="invalid-effort",
                provider="codex",
                model=CODEX_MODEL,
                effort=effort,
            )
        )


def test_campaign_rejects_invalid_parallelism(
    monkeypatch,
) -> None:
    monkeypatch.setenv("GRANULAR_MEAN_MAX_PARALLEL", "0")
    _set_published_images(monkeypatch)
    definition = build_reviewed_definition()
    contract = load_output_contract(definition.contract_path)

    with pytest.raises(
        RuntimeError,
        match="GRANULAR_MEAN_MAX_PARALLEL must be positive",
    ):
        build_campaign(definition, contract)


def test_codex_schema_is_normalized_for_azure() -> None:
    schema = strict_output_schema(
        {
            "type": "object",
            "properties": {
                "status": {"enum": ["complete", "failed"]},
                "manifest": {"const": "submission/manifest.json"},
                "details": {"type": "object"},
                "units": {
                    "type": "array",
                    "uniqueItems": True,
                    "items": {"type": "string"},
                },
            },
            "required": ["status", "manifest", "units"],
        }
    )

    assert set(schema["properties"]) == {
        "status",
        "manifest",
        "units",
    }
    assert schema["properties"]["status"]["type"] == "string"
    assert schema["properties"]["manifest"]["type"] == "string"
    assert "uniqueItems" not in schema["properties"]["units"]
    assert schema["additionalProperties"] is False


def test_codex_wrapper_replaces_output_schema(
    monkeypatch,
    tmp_path,
) -> None:
    source = tmp_path / "schema.json"
    source.write_text(
        '{"type":"object","properties":{"status":{"enum":["ok"]}},'
        '"required":["status"]}'
    )
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    arguments = prepare_arguments(
        ["exec", "--output-schema", str(source), "--model", CODEX_MODEL]
    )

    generated = Path(arguments[2])
    assert generated == codex_home / "brunner-strict-output-schema.json"
    assert json.loads(generated.read_text())["properties"]["status"] == {
        "enum": ["ok"],
        "type": "string",
    }


def test_campaign_default_parallelism_remains_sequential(
    monkeypatch,
) -> None:
    campaign = _campaign(monkeypatch)

    assert campaign.plan.max_parallel == DEFAULT_MAX_PARALLEL
    assert campaign.backend.max_parallel == DEFAULT_MAX_PARALLEL
    assert (
        campaign.backend.artifact_chunk_bytes
        == DEFAULT_STERLING_ARTIFACT_CHUNK_BYTES
    )
    assert (
        campaign.backend.artifact_chunk_attempts
        == DEFAULT_STERLING_ARTIFACT_CHUNK_ATTEMPTS
    )
    assert (
        campaign.backend.command_timeout_seconds
        == DEFAULT_STERLING_COMMAND_TIMEOUT_SECONDS
    )
