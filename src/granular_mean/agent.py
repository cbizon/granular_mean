from __future__ import annotations

import os
import sys

from brunner.agent_cli import main as brunner_agent_main
from brunner.providers import ProviderSettings
from brunner.trial import TrialIdentity, load_trial_identity


CODEX_MODEL = "gpt-5.6-sol"
CODEX_EFFORTS = ("low", "medium", "high", "xhigh", "max", "ultra")
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


def azure_codex_settings(
    model: str,
    effort: str | None,
    *,
    allowed_efforts: tuple[str, ...] | None = None,
) -> ProviderSettings:
    return ProviderSettings(
        provider="codex",
        model=model,
        effort=effort,
        allowed_efforts=allowed_efforts,
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
    return azure_codex_settings(
        identity.model,
        identity.effort,
        allowed_efforts=CODEX_EFFORTS,
    )


def main() -> int:
    if "--provider-executable" not in sys.argv:
        sys.argv.extend(
            (
                "--provider-executable",
                os.environ.get(
                    "GRANULAR_MEAN_CODEX_EXECUTABLE",
                    "granular-mean-codex",
                ),
            )
        )
    brunner_agent_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
