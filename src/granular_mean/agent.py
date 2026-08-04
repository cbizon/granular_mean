from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
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
    parser = argparse.ArgumentParser(prog="granular-mean-agent")
    parser.add_argument("trial", type=Path)
    arguments = parser.parse_args()
    trial = arguments.trial.resolve()
    identity = load_trial_identity(trial)
    stop_requested = threading.Event()

    def request_stop(
        _signum: int,
        _frame: object,
    ) -> None:
        stop_requested.set()

    previous_handlers = {
        signum: signal.signal(signum, request_stop)
        for signum in (signal.SIGTERM, signal.SIGINT)
    }
    try:
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
            stop_requested=stop_requested,
        )
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
