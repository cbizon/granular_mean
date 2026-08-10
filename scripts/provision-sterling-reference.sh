#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

NAMESPACE="${GRANULAR_MEAN_STERLING_NAMESPACE:-bizon}"
EXPECTED_CONTEXT="${GRANULAR_MEAN_STERLING_CONTEXT:-bizon@sterling}"
REFERENCE_DIR="${GRANULAR_MEAN_REFERENCE_DIR:-${ROOT_DIR}/reference}"
WAIT_TIMEOUT="${GRANULAR_MEAN_REFERENCE_WAIT_TIMEOUT:-10m}"
KUBECTL="${KUBECTL:-kubectl}"

PVC_NAME="granular-mean-reference-v1"
UPLOAD_POD="granular-mean-reference-upload"
PVC_MANIFEST="${ROOT_DIR}/deploy/sterling-reference-pvc.yaml"
POLICY_MANIFEST="${ROOT_DIR}/deploy/sterling-reference-network-policy.yaml"
UPLOAD_MANIFEST="${ROOT_DIR}/deploy/sterling-reference-upload.yaml"
MANIFEST_PATH="${REFERENCE_DIR}/manifest.json"
ANNOTATION="dev.brunner/reference-manifest-sha256"

cleanup_policy=false
cleanup_pod=false
cleanup_annotation=false

fail() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"
}

cleanup() {
    local status=$?
    trap - EXIT
    set +e

    if [[ "${cleanup_annotation}" == true ]]; then
        if ! "${KUBECTL}" annotate pvc "${PVC_NAME}" \
            -n "${NAMESPACE}" \
            "${ANNOTATION}-" \
            --overwrite; then
            printf 'warning: failed to remove unverified PVC annotation\n' >&2
        fi
    fi

    if [[ "${cleanup_pod}" == true ]]; then
        if ! "${KUBECTL}" delete pod "${UPLOAD_POD}" \
            -n "${NAMESPACE}" \
            --ignore-not-found=true \
            --wait=true; then
            printf 'warning: failed to delete upload pod %s\n' \
                "${UPLOAD_POD}" >&2
        fi
    fi

    if [[ "${cleanup_policy}" == true ]]; then
        if ! "${KUBECTL}" delete \
            -n "${NAMESPACE}" \
            -f "${POLICY_MANIFEST}" \
            --ignore-not-found=true; then
            printf 'warning: failed to delete upload network policy\n' >&2
        fi
    fi

    exit "${status}"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

require_command "${KUBECTL}"
require_command shasum

[[ -f "${MANIFEST_PATH}" ]] \
    || fail "reference manifest not found: ${MANIFEST_PATH}"
[[ -f "${PVC_MANIFEST}" ]] || fail "PVC manifest not found: ${PVC_MANIFEST}"
[[ -f "${POLICY_MANIFEST}" ]] \
    || fail "network policy manifest not found: ${POLICY_MANIFEST}"
[[ -f "${UPLOAD_MANIFEST}" ]] \
    || fail "upload pod manifest not found: ${UPLOAD_MANIFEST}"

current_context="$("${KUBECTL}" config current-context)"
[[ "${current_context}" == "${EXPECTED_CONTEXT}" ]] || fail \
    "current Kubernetes context is '${current_context}'; expected '${EXPECTED_CONTEXT}'"

if "${KUBECTL}" get pod "${UPLOAD_POD}" \
    -n "${NAMESPACE}" \
    -o name >/dev/null 2>&1; then
    fail "upload pod ${UPLOAD_POD} already exists in namespace ${NAMESPACE}"
fi

manifest_digest="$(shasum -a 256 "${MANIFEST_PATH}")"
manifest_digest="${manifest_digest%% *}"
[[ "${manifest_digest}" =~ ^[0-9a-f]{64}$ ]] \
    || fail "could not compute a valid SHA-256 digest for ${MANIFEST_PATH}"

printf 'Provisioning %s in %s on %s\n' \
    "${PVC_NAME}" "${NAMESPACE}" "${current_context}"

"${KUBECTL}" apply -n "${NAMESPACE}" -f "${PVC_MANIFEST}"
"${KUBECTL}" wait -n "${NAMESPACE}" \
    --for=jsonpath='{.status.phase}'=Bound \
    "pvc/${PVC_NAME}" \
    --timeout="${WAIT_TIMEOUT}"
"${KUBECTL}" annotate pvc "${PVC_NAME}" \
    -n "${NAMESPACE}" \
    "${ANNOTATION}-" \
    --overwrite

cleanup_policy=true
"${KUBECTL}" apply -n "${NAMESPACE}" -f "${POLICY_MANIFEST}"

cleanup_pod=true
"${KUBECTL}" apply -n "${NAMESPACE}" -f "${UPLOAD_MANIFEST}"
"${KUBECTL}" wait -n "${NAMESPACE}" \
    --for=condition=Ready \
    "pod/${UPLOAD_POD}" \
    --timeout="${WAIT_TIMEOUT}"

"${KUBECTL}" exec -n "${NAMESPACE}" "${UPLOAD_POD}" -- \
    sh -c 'find /reference -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +'
"${KUBECTL}" cp -n "${NAMESPACE}" \
    "${REFERENCE_DIR}/." \
    "${UPLOAD_POD}:/reference"
"${KUBECTL}" exec -n "${NAMESPACE}" "${UPLOAD_POD}" -- \
    granular-reference-validate \
    --reference-root /reference

cleanup_annotation=true
"${KUBECTL}" annotate pvc "${PVC_NAME}" \
    -n "${NAMESPACE}" \
    "${ANNOTATION}=${manifest_digest}" \
    --overwrite

recorded_digest="$("${KUBECTL}" get pvc "${PVC_NAME}" \
    -n "${NAMESPACE}" \
    -o 'jsonpath={.metadata.annotations.dev\.brunner/reference-manifest-sha256}')"
[[ "${recorded_digest}" == "${manifest_digest}" ]] || fail \
    "PVC annotation verification failed: '${recorded_digest}'"
cleanup_annotation=false

printf 'Reference provisioned and validated: %s\n' "${manifest_digest}"
