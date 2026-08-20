from __future__ import annotations

import os

from brunner.agent_cli import main as brunner_agent_main
from brunner.providers import ProviderSettings
from brunner.trial import TrialIdentity, load_trial_identity


CODEX_MODEL = "gpt-5.6-sol"
CAMPAIGN_CODEX_MODELS = (
    "gpt-5.6-luna",
    "gpt-5.6-terra",
    CODEX_MODEL,
)
CAMPAIGN_CLAUDE_MODEL = "claude-haiku-4-5"
CAMPAIGN_EFFORT = "low"
CAMPAIGN_EFFORTS = (CAMPAIGN_EFFORT,)
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
    if identity.effort != CAMPAIGN_EFFORT:
        raise ValueError(
            f"granular campaign effort must be {CAMPAIGN_EFFORT!r}, got "
            f"{identity.effort!r}"
        )
    if identity.provider == "codex":
        if identity.model not in CAMPAIGN_CODEX_MODELS:
            raise ValueError(
                "granular Codex campaign model must be one of "
                f"{CAMPAIGN_CODEX_MODELS}, got {identity.model!r}"
            )
        return azure_codex_settings(
            identity.model,
            identity.effort,
            allowed_efforts=CAMPAIGN_EFFORTS,
        )
    if (
        identity.provider == "claude"
        and identity.model == CAMPAIGN_CLAUDE_MODEL
    ):
        return ProviderSettings(
            provider=identity.provider,
            model=identity.model,
            effort=identity.effort,
            allowed_efforts=CAMPAIGN_EFFORTS,
        )
    if identity.provider == "claude":
        raise ValueError(
            f"granular Claude campaign requires model "
            f"{CAMPAIGN_CLAUDE_MODEL!r}, got "
            f"{identity.model!r}"
        )
    raise ValueError(
        "granular campaign provider must be 'codex' or 'claude', got "
        f"{identity.provider!r}"
    )


def main() -> int:
    brunner_agent_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
