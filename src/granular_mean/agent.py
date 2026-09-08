from __future__ import annotations

import os

from brunner.agent_cli import main as brunner_agent_main
from brunner.providers import ProviderSettings
from brunner.trial import TrialIdentity, load_trial_identity


CODEX_MODEL = "gpt-5.6-sol"
CAMPAIGN_HISTORICAL_CODEX_MODELS = (
    "gpt-5.6-luna",
    "gpt-5.6-terra",
    CODEX_MODEL,
)
CAMPAIGN_NEW_CODEX_MODELS = ("gpt-6-astra",)
CAMPAIGN_CODEX_MODELS = (
    *CAMPAIGN_HISTORICAL_CODEX_MODELS,
    *CAMPAIGN_NEW_CODEX_MODELS,
)
CAMPAIGN_CLAUDE_MODELS = (
    "claude-haiku-4-5",
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-fable-5",
)
CAMPAIGN_HIGHEST_CLAUDE_MODELS = CAMPAIGN_CLAUDE_MODELS[:-1]
CAMPAIGN_LOW_EFFORT = "low"
CAMPAIGN_CODEX_HIGHEST_EFFORT = "xhigh"
CAMPAIGN_CLAUDE_HIGHEST_EFFORT = "max"
CAMPAIGN_CODEX_EFFORTS = (
    CAMPAIGN_LOW_EFFORT,
    CAMPAIGN_CODEX_HIGHEST_EFFORT,
)
CAMPAIGN_CLAUDE_EFFORTS = {
    model: (
        CAMPAIGN_LOW_EFFORT,
        CAMPAIGN_CLAUDE_HIGHEST_EFFORT,
    )
    for model in CAMPAIGN_HIGHEST_CLAUDE_MODELS
}
CAMPAIGN_CLAUDE_EFFORTS["claude-fable-5"] = (CAMPAIGN_LOW_EFFORT,)
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
    if identity.provider == "codex":
        if identity.model not in CAMPAIGN_CODEX_MODELS:
            raise ValueError(
                "granular Codex campaign model must be one of "
                f"{CAMPAIGN_CODEX_MODELS}, got {identity.model!r}"
            )
        if identity.effort not in CAMPAIGN_CODEX_EFFORTS:
            raise ValueError(
                f"granular Codex campaign effort must be one of "
                f"{CAMPAIGN_CODEX_EFFORTS}, got {identity.effort!r}"
            )
        return azure_codex_settings(
            identity.model,
            identity.effort,
            allowed_efforts=CAMPAIGN_CODEX_EFFORTS,
        )
    if identity.provider == "claude":
        allowed_efforts = CAMPAIGN_CLAUDE_EFFORTS.get(identity.model)
        if allowed_efforts is None:
            raise ValueError(
                "granular Claude campaign model must be one of "
                f"{CAMPAIGN_CLAUDE_MODELS}, got "
                f"{identity.model!r}"
            )
        if identity.effort not in allowed_efforts:
            raise ValueError(
                f"granular Claude campaign model {identity.model!r} "
                f"supports campaign efforts {allowed_efforts}, got "
                f"{identity.effort!r}"
            )
        return ProviderSettings(
            provider=identity.provider,
            model=identity.model,
            effort=identity.effort,
            allowed_efforts=allowed_efforts,
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
