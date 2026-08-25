#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

ACTION="${1:-}"
BRUNNER="${GRANULAR_MEAN_BRUNNER:-${ROOT_DIR}/.venv/bin/brunner}"
BENCHMARK="${GRANULAR_MEAN_BENCHMARK:-granular_mean.definition:build_reviewed_definition}"
CAMPAIGN="${GRANULAR_MEAN_CAMPAIGN:-granular_mean.campaign}"
EXPECTED_CONTEXT="${GRANULAR_MEAN_STERLING_CONTEXT:-bizon@sterling}"
PORT="${GRANULAR_MEAN_CAMPAIGN_PORT:-8765}"
ARCHIVE_DIR="${2:-${ROOT_DIR}/campaign-results/haiku-luna-terra-sol-low-cluster-v1}"
KUBECTL="${KUBECTL:-kubectl}"

fail() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

require_command() {
    if [[ "$1" == */* ]]; then
        [[ -x "$1" ]] || fail "required command is not executable: $1"
        return
    fi
    command -v "$1" >/dev/null 2>&1 \
        || fail "required command not found: $1"
}

require_context() {
    local current_context
    current_context="$("${KUBECTL}" config current-context)"
    [[ "${current_context}" == "${EXPECTED_CONTEXT}" ]] || fail \
        "current Kubernetes context is '${current_context}'; expected '${EXPECTED_CONTEXT}'"
}

run_brunner() {
    local command="$1"
    shift
    "${BRUNNER}" \
        --benchmark "${BENCHMARK}" \
        "${command}" "${CAMPAIGN}" "$@"
}

case "${ACTION}" in
    submit|status|sync|monitor|retire|resume)
        ;;
    *)
        fail "usage: $0 {submit|status|sync [ARCHIVE]|monitor [ARCHIVE]|retire [ARCHIVE]|resume [ARCHIVE]}"
        ;;
esac

require_command "${BRUNNER}"

case "${ACTION}" in
    monitor)
        [[ -d "${ARCHIVE_DIR}" ]] \
            || fail "campaign archive does not exist: ${ARCHIVE_DIR}"
        "${BRUNNER}" \
            campaign-monitor "${ARCHIVE_DIR}" \
            --local-port "${PORT}"
        exit
        ;;
esac

require_command "${KUBECTL}"
require_context

case "${ACTION}" in
    submit)
        run_brunner campaign-submit
        ;;
    status)
        run_brunner campaign-status
        ;;
    sync)
        mkdir -p "$(dirname -- "${ARCHIVE_DIR}")"
        run_brunner campaign-sync "${ARCHIVE_DIR}"
        ;;
    retire)
        mkdir -p "$(dirname -- "${ARCHIVE_DIR}")"
        run_brunner campaign-retire "${ARCHIVE_DIR}"
        ;;
    resume)
        [[ -d "${ARCHIVE_DIR}" ]] \
            || fail "campaign archive does not exist: ${ARCHIVE_DIR}"
        run_brunner campaign-submit --resume-from "${ARCHIVE_DIR}"
        ;;
esac
