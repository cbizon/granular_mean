from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from brunner.backends import KubernetesBackend
from brunner.backends.kubernetes import render_job
from brunner.contract import load_output_contract
from brunner.trial import TrialIdentity

from granular_mean import agent as agent_module
from granular_mean.agent import (
    CODEX_EFFORTS,
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
    DEFAULT_AGENT_IMAGE,
    DEFAULT_AGENT_MEMORY_LIMIT,
    DEFAULT_AGENT_MEMORY_REQUEST,
    DEFAULT_STERLING_ARTIFACT_CHUNK_ATTEMPTS,
    DEFAULT_STERLING_ARTIFACT_CHUNK_BYTES,
    DEFAULT_STERLING_CODEX_SECRET,
    DEFAULT_STERLING_COMMAND_TIMEOUT_SECONDS,
    DEFAULT_STERLING_NAMESPACE,
    DEFAULT_STERLING_PROXY_IMAGE,
    DEFAULT_STERLING_REFERENCE_CLAIM,
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
    DEFAULT_EVALUATOR_IMAGE,
    DEFAULT_EVALUATOR_MEMORY_LIMIT,
    DEFAULT_EVALUATOR_MEMORY_REQUEST,
    DEFAULT_REVIEWER_EFFORT,
    DEFAULT_REVIEWER_MODEL,
    build_definition,
    build_reviewed_definition,
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


def test_campaign_runs_sol_at_every_supported_effort() -> None:
    trials = build_campaign_trials()

    assert tuple(trial.effort for trial in trials) == CODEX_EFFORTS
    assert {trial.provider for trial in trials} == {"codex"}
    assert {trial.model for trial in trials} == {CODEX_MODEL}
    assert len({trial.test_id for trial in trials}) == len(CODEX_EFFORTS)


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
            "--provider-executable",
            "granular-mean-codex",
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
    tmp_path,
) -> None:
    monkeypatch.setenv("GRANULAR_MEAN_CAMPAIGN_ROOT", str(tmp_path))
    monkeypatch.setenv("GRANULAR_MEAN_MAX_PARALLEL", "2")
    monkeypatch.setenv("GRANULAR_MEAN_AGENT_IMAGE", "agent:test")
    definition = build_reviewed_definition()
    contract = load_output_contract(definition.contract_path)

    runner = build_campaign(definition, contract)

    assert runner.plan.campaign_id == CAMPAIGN_ID
    assert runner.plan.root == tmp_path.resolve()
    assert runner.plan.max_parallel == 2
    assert runner.plan.backend_image == "agent:test"
    assert runner.plan.provider_executable == "granular-mean-codex"
    assert isinstance(runner.backend, KubernetesBackend)
    assert runner.backend.profile.namespace == DEFAULT_STERLING_NAMESPACE
    assert runner.backend.profile.agent_image == "agent:test"
    assert (
        runner.backend.profile.artifact_reader_image
        == DEFAULT_EVALUATOR_IMAGE
    )
    assert (
        runner.backend.profile.reference_claim_name
        == DEFAULT_STERLING_REFERENCE_CLAIM
    )
    assert (
        runner.backend.profile.proxy_image
        == DEFAULT_STERLING_PROXY_IMAGE
    )
    assert runner.backend.profile.image_pull_secrets == ()
    assert runner.backend.profile.max_parallel == 2
    assert (
        runner.backend.profile.artifact_chunk_bytes
        == DEFAULT_STERLING_ARTIFACT_CHUNK_BYTES
    )
    assert (
        runner.backend.profile.artifact_chunk_attempts
        == DEFAULT_STERLING_ARTIFACT_CHUNK_ATTEMPTS
    )
    assert (
        runner.backend.profile.command_timeout_seconds
        == DEFAULT_STERLING_COMMAND_TIMEOUT_SECONDS
    )
    assert runner.backend.profile.secret_environment == {}
    assert runner.plan.provider_secret_environment == {
        "codex": {
            "AZURE_OPENAI_API_KEY": (
                DEFAULT_STERLING_CODEX_SECRET,
                "AZURE_OPENAI_API_KEY",
            )
        }
    }
    assert runner.backend.profile.nonsecret_environment == {
        NESTED_SANDBOX_BYPASS_ENVIRONMENT: "true",
    }


def test_campaign_accepts_artifact_stream_overrides(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("GRANULAR_MEAN_CAMPAIGN_ROOT", str(tmp_path))
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

    runner = build_campaign(definition, contract)

    assert runner.backend.profile.artifact_chunk_bytes == 512 * 1024
    assert runner.backend.profile.artifact_chunk_attempts == 7
    assert runner.backend.profile.command_timeout_seconds == 900


def test_campaign_workload_uses_containerized_azure_launcher(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("GRANULAR_MEAN_CAMPAIGN_ROOT", str(tmp_path))
    monkeypatch.setenv("GRANULAR_MEAN_AGENT_IMAGE", "agent:test")
    definition = build_reviewed_definition()
    contract = load_output_contract(definition.contract_path)
    runner = build_campaign(definition, contract)
    campaign_trial = runner.plan.trials[0]
    trial = tmp_path / campaign_trial.test_id

    workload = runner.workload_factory(
        trial,
        campaign_trial,
        runner.plan,
        definition,
        "kubernetes",
    )

    assert workload.command == (
        "python",
        "-m",
        "brunner.agent_cli",
        "/brunner/trial",
        "--provider-executable",
        "granular-mean-codex",
    )
    assert workload.image == "agent:test"
    assert workload.secret_environment == {
        "AZURE_OPENAI_API_KEY": (
            DEFAULT_STERLING_CODEX_SECRET,
            "AZURE_OPENAI_API_KEY",
        )
    }
    assert workload.evaluation is not None
    assert workload.evaluation.image == DEFAULT_EVALUATOR_IMAGE
    assert workload.evaluation.command == (
        "python",
        "-m",
        "granular_mean.evaluator",
    )
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
        runner.backend.profile,
        {},
        proxy_url="http://10.96.4.12:3128",
    )
    pod = job["spec"]["template"]["spec"]
    agent = pod["initContainers"][0]
    evaluator = pod["containers"][0]
    assert agent["name"] == "agent"
    assert evaluator["name"] == "evaluator"
    assert agent["resources"] == {
        "requests": {
            "cpu": DEFAULT_AGENT_CPU_REQUEST,
            "memory": DEFAULT_AGENT_MEMORY_REQUEST,
            "ephemeral-storage": DEFAULT_AGENT_EPHEMERAL_STORAGE_REQUEST,
        },
        "limits": {
            "cpu": DEFAULT_AGENT_CPU_LIMIT,
            "memory": DEFAULT_AGENT_MEMORY_LIMIT,
            "ephemeral-storage": DEFAULT_AGENT_EPHEMERAL_STORAGE_LIMIT,
        },
    }
    assert evaluator["resources"] == {
        "requests": {
            "cpu": DEFAULT_EVALUATOR_CPU_REQUEST,
            "memory": DEFAULT_EVALUATOR_MEMORY_REQUEST,
            "ephemeral-storage": (
                DEFAULT_EVALUATOR_EPHEMERAL_STORAGE_REQUEST
            ),
        },
        "limits": {
            "cpu": DEFAULT_EVALUATOR_CPU_LIMIT,
            "memory": DEFAULT_EVALUATOR_MEMORY_LIMIT,
            "ephemeral-storage": (
                DEFAULT_EVALUATOR_EPHEMERAL_STORAGE_LIMIT
            ),
        },
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


def test_campaign_workload_accepts_resource_overrides(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("GRANULAR_MEAN_CAMPAIGN_ROOT", str(tmp_path))
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
    definition = build_reviewed_definition()
    contract = load_output_contract(definition.contract_path)
    runner = build_campaign(definition, contract)
    campaign_trial = runner.plan.trials[0]
    trial = tmp_path / campaign_trial.test_id

    workload = runner.workload_factory(
        trial,
        campaign_trial,
        runner.plan,
        definition,
        "kubernetes",
    )

    assert workload.cpu_request == "1500m"
    assert workload.cpu_limit == "6"
    assert workload.memory_request == "12Gi"
    assert workload.memory_limit == "24Gi"
    assert workload.ephemeral_storage_request == "750Mi"
    assert workload.ephemeral_storage_limit == "2Gi"


def test_campaign_defaults_to_pinned_agent_image(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("GRANULAR_MEAN_CAMPAIGN_ROOT", str(tmp_path))
    monkeypatch.delenv("GRANULAR_MEAN_AGENT_IMAGE", raising=False)
    definition = build_reviewed_definition()
    contract = load_output_contract(definition.contract_path)

    runner = build_campaign(definition, contract)

    assert runner.plan.backend_image == DEFAULT_AGENT_IMAGE
    assert runner.backend.profile.agent_image == DEFAULT_AGENT_IMAGE
    assert (
        runner.backend.profile.artifact_reader_image
        == DEFAULT_EVALUATOR_IMAGE
    )


def test_images_pin_current_brunner_build() -> None:
    root = Path(__file__).parents[1]
    agent = (root / "containers" / "agent.Dockerfile").read_text()
    evaluator = (
        root / "containers" / "evaluator.Dockerfile"
    ).read_text()

    brunner_revision = (
        "f3e01c1913a49e7440fa455566200c97751b9655"
    )
    assert f"ARG BRUNNER_REVISION={brunner_revision}" in agent
    assert f"ARG BRUNNER_REVISION={brunner_revision}" in evaluator
    assert "COPY --from=brunner" in agent
    assert "COPY --from=brunner" in evaluator
    assert DEFAULT_AGENT_IMAGE == (
        "ghcr.io/cbizon/granular-mean-agent@"
        "sha256:8b785dc13f0c52ad53ddd59088b210c64327dd1dfedd38df4b5d952f76c99868"
    )
    assert DEFAULT_EVALUATOR_IMAGE == (
        "ghcr.io/cbizon/granular-mean-evaluator@"
        "sha256:6a2cdcb2a2e66ccbef8451f29dbdb246f3fa888052d24004f50b034457e19f05"
    )


def test_definition_requires_image_backed_sterling_evaluation() -> None:
    definition = build_definition()

    assert definition.evaluation.image == DEFAULT_EVALUATOR_IMAGE
    assert definition.evaluation.command == (
        "python",
        "-m",
        "granular_mean.evaluator",
    )
    assert definition.evaluation.cpu_request == DEFAULT_EVALUATOR_CPU_REQUEST
    assert definition.evaluation.cpu_limit == DEFAULT_EVALUATOR_CPU_LIMIT
    assert (
        definition.evaluation.memory_request
        == DEFAULT_EVALUATOR_MEMORY_REQUEST
    )
    assert definition.evaluation.memory_limit == DEFAULT_EVALUATOR_MEMORY_LIMIT
    assert definition.reference is not None
    assert definition.reference.validate_command == (
        "python",
        "-m",
        "granular_mean.reference_validation",
    )


def test_provider_settings_pin_model_efforts_and_azure() -> None:
    settings = provider_settings(
        TrialIdentity(
            test_id="sol-high",
            provider="codex",
            model=CODEX_MODEL,
            effort="high",
        )
    )

    assert settings.allowed_efforts == CODEX_EFFORTS
    assert settings.provider_id == "azure"
    assert settings.base_url == DEFAULT_CODEX_BASE_URL
    assert settings.environment_key == "AZURE_OPENAI_API_KEY"


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


def test_codex_wrapper_requires_initial_sandbox_when_bypassing(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        NESTED_SANDBOX_BYPASS_ENVIRONMENT,
        "true",
    )

    with pytest.raises(
        RuntimeError,
        match="does not include --sandbox",
    ):
        prepare_arguments(["exec", "--json"])


def test_reviewed_definition_defaults_to_azure_sol_xhigh() -> None:
    definition = build_reviewed_definition()
    review = definition.qualitative_review

    assert review is not None
    assert review.reviewer == azure_codex_settings(
        DEFAULT_REVIEWER_MODEL,
        DEFAULT_REVIEWER_EFFORT,
    )
    assert review.reviewer_executable == str(
        Path(sys.executable).with_name("granular-mean-codex")
    )
    assert review.required is False
    assert "workspace/**/*.py" in review.trial_evidence_paths


def test_campaign_rejects_unreviewed_definition(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("GRANULAR_MEAN_CAMPAIGN_ROOT", str(tmp_path))
    definition = build_definition()
    contract = load_output_contract(definition.contract_path)

    with pytest.raises(
        RuntimeError,
        match="campaigns require qualitative review",
    ):
        build_campaign(definition, contract)


@pytest.mark.parametrize("effort", [None, "max", "ultra"])
def test_provider_settings_reject_unsupported_effort(
    effort: str | None,
) -> None:
    with pytest.raises(ValueError, match="effort must be one of"):
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
    tmp_path,
) -> None:
    monkeypatch.setenv("GRANULAR_MEAN_CAMPAIGN_ROOT", str(tmp_path))
    monkeypatch.setenv("GRANULAR_MEAN_MAX_PARALLEL", "0")
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
