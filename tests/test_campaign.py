from __future__ import annotations

import json
from pathlib import Path

import pytest

from brunner.backends import LocalBackend
from brunner.contract import load_output_contract
from brunner.trial import TrialIdentity

from granular_mean.agent import (
    CODEX_EFFORTS,
    CODEX_MODEL,
    DEFAULT_CODEX_BASE_URL,
    provider_settings,
)
from granular_mean.campaign import (
    CAMPAIGN_ID,
    build_campaign,
    build_campaign_trials,
)
from granular_mean.codex_wrapper import (
    prepare_arguments,
    strict_output_schema,
)
from granular_mean.definition import build_definition


def test_campaign_runs_sol_at_every_supported_effort() -> None:
    trials = build_campaign_trials()

    assert tuple(trial.effort for trial in trials) == CODEX_EFFORTS
    assert {trial.provider for trial in trials} == {"codex"}
    assert {trial.model for trial in trials} == {CODEX_MODEL}
    assert len({trial.test_id for trial in trials}) == len(CODEX_EFFORTS)


def test_campaign_uses_local_backend_and_configured_parallelism(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("GRANULAR_MEAN_CAMPAIGN_ROOT", str(tmp_path))
    monkeypatch.setenv("GRANULAR_MEAN_MAX_PARALLEL", "2")
    definition = build_definition()
    contract = load_output_contract(definition.contract_path)

    runner = build_campaign(definition, contract)

    assert runner.plan.campaign_id == CAMPAIGN_ID
    assert runner.plan.root == tmp_path.resolve()
    assert runner.plan.max_parallel == 2
    assert isinstance(runner.backend, LocalBackend)
    assert runner.backend.max_parallel == 2


def test_campaign_workload_uses_azure_launcher(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("GRANULAR_MEAN_CAMPAIGN_ROOT", str(tmp_path))
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
    definition = build_definition()
    contract = load_output_contract(definition.contract_path)
    runner = build_campaign(definition, contract)
    campaign_trial = runner.plan.trials[0]
    trial = tmp_path / campaign_trial.test_id

    workload = runner.workload_factory(
        trial,
        campaign_trial,
        runner.plan,
        definition,
        "local",
    )

    assert workload.command[1:] == (
        "-m",
        "granular_mean.agent",
        str(trial),
    )
    assert workload.environment == {
        "AZURE_OPENAI_API_KEY": "test-key"
    }


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
    definition = build_definition()
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
