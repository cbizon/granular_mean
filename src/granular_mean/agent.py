from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from brunner.providers import ProviderSettings
from brunner.runner import run_staged_trial
from brunner.trial import TrialIdentity, load_trial_identity


CODEX_MODEL = "gpt-5.6-sol"
CODEX_EFFORTS = ("low", "medium", "high", "xhigh")
DEFAULT_CODEX_PROVIDER_ID = "azure"
DEFAULT_CODEX_PROVIDER_NAME = "Azure OpenAI"
DEFAULT_CODEX_BASE_URL = (
    "https://renci-analytics.openai.azure.com/openai/v1/"
)
DEFAULT_CODEX_ENVIRONMENT_KEY = "AZURE_OPENAI_API_KEY"


def codex_environment_key() -> str:
    return os.environ.get(
        "GRANULAR_MEAN_CODEX_ENVIRONMENT_KEY",
        DEFAULT_CODEX_ENVIRONMENT_KEY,
    )


def provider_settings(identity: TrialIdentity) -> ProviderSettings:
    if identity.provider != "codex":
        raise ValueError(
            f"granular campaign requires provider 'codex', got "
            f"{identity.provider!r}"
        )
    if identity.model != CODEX_MODEL:
        raise ValueError(
            f"granular campaign requires model {CODEX_MODEL!r}, got "
            f"{identity.model!r}"
        )
    if identity.effort not in CODEX_EFFORTS:
        raise ValueError(
            f"{CODEX_MODEL} effort must be one of {CODEX_EFFORTS}, got "
            f"{identity.effort!r}"
        )
    return ProviderSettings(
        provider=identity.provider,
        model=identity.model,
        effort=identity.effort,
        allowed_efforts=CODEX_EFFORTS,
        provider_id=os.environ.get(
            "GRANULAR_MEAN_CODEX_PROVIDER_ID",
            DEFAULT_CODEX_PROVIDER_ID,
        ),
        provider_name=os.environ.get(
            "GRANULAR_MEAN_CODEX_PROVIDER_NAME",
            DEFAULT_CODEX_PROVIDER_NAME,
        ),
        base_url=os.environ.get(
            "GRANULAR_MEAN_CODEX_BASE_URL",
            DEFAULT_CODEX_BASE_URL,
        ),
        environment_key=codex_environment_key(),
    )


def main() -> int:
    parser = argparse.ArgumentParser(prog="granular-mean-agent")
    parser.add_argument("trial", type=Path)
    arguments = parser.parse_args()
    trial = arguments.trial.resolve()
    identity = load_trial_identity(trial)
    state = run_staged_trial(
        trial,
        provider_settings(identity),
        executable=os.environ.get(
            "GRANULAR_MEAN_CODEX_EXECUTABLE",
            str(
                Path(sys.executable).with_name(
                    "granular-mean-codex"
                )
            ),
        ),
    )
    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
