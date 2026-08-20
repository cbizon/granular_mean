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
RESULTS_DIR="${2:-${ROOT_DIR}/campaign-results/luna-terra-sol-haiku-low-cluster-v1}"
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
    submit|status|monitor|retrieve|delete|delete-results)
        ;;
    *)
        fail "usage: $0 {submit|status|monitor|retrieve [DEST]|delete|delete-results}"
        ;;
esac

require_command "${BRUNNER}"
require_command "${KUBECTL}"
require_context

case "${ACTION}" in
    submit)
        run_brunner campaign-submit
        ;;
    status)
        run_brunner campaign-status
        ;;
    monitor)
        run_brunner campaign-monitor --local-port "${PORT}"
        ;;
    retrieve)
        mkdir -p "$(dirname -- "${RESULTS_DIR}")"
        "${BRUNNER}" \
            --benchmark "${BENCHMARK}" \
            campaign-retrieve "${CAMPAIGN}" "${RESULTS_DIR}"
        ;;
    delete)
        run_brunner campaign-delete
        ;;
    delete-results)
        "${BRUNNER}" \
            --benchmark "${BENCHMARK}" \
            campaign-delete "${CAMPAIGN}" --delete-results
        ;;
esac
