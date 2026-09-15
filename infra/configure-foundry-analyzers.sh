#!/usr/bin/env bash
set -euo pipefail

FOUNDRY_ENDPOINT="${CONTENT_UNDERSTANDING_ENDPOINT:?Set CONTENT_UNDERSTANDING_ENDPOINT}"
API_VERSION="${CONTENT_UNDERSTANDING_API_VERSION:-2025-11-01}"
MODEL_DEPLOYMENT="${CONTENT_UNDERSTANDING_MODEL_DEPLOYMENT:-gpt-4-1-mini-cu-flv}"
EMBEDDING_DEPLOYMENT="${CONTENT_UNDERSTANDING_EMBEDDING_DEPLOYMENT:-text-embedding-3-large-cu-flv}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOKEN="$(az account get-access-token --scope https://cognitiveservices.azure.com/.default --query accessToken -o tsv)"

curl --fail --silent --show-error \
  --request PATCH \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  --data "{\"modelDeployments\":{\"gpt-4.1-mini\":\"${MODEL_DEPLOYMENT}\",\"prebuilt-analyzer-completion\":\"${MODEL_DEPLOYMENT}\",\"prebuilt-analyzer-completion-mini\":\"${MODEL_DEPLOYMENT}\",\"text-embedding-3-large\":\"${EMBEDDING_DEPLOYMENT}\",\"prebuilt-analyzer-embedding\":\"${EMBEDDING_DEPLOYMENT}\"}}" \
  "${FOUNDRY_ENDPOINT%/}/contentunderstanding/defaults?api-version=${API_VERSION}" \
  >/dev/null

poll_operation() {
  local operation_url="$1"
  for _ in $(seq 1 90); do
    local response
    response="$(curl --fail --silent --show-error \
      -H "Authorization: Bearer ${TOKEN}" \
      "${operation_url}")"
    local status
    status="$(printf '%s' "${response}" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status", ""))')"
    status="$(printf '%s' "${status}" | tr '[:upper:]' '[:lower:]')"
    case "${status}" in
      succeeded) return 0 ;;
      failed|canceled)
        printf '%s\n' "${response}" >&2
        return 1
        ;;
    esac
    sleep 2
  done
  echo "Timed out waiting for analyzer operation: ${operation_url}" >&2
  return 1
}

poll_analyzer_ready() {
  local analyzer_url="$1"
  for _ in $(seq 1 90); do
    local response
    response="$(curl --fail --silent --show-error \
      -H "Authorization: Bearer ${TOKEN}" \
      "${analyzer_url}")"
    local status
    status="$(printf '%s' "${response}" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status", ""))')"
    status="$(printf '%s' "${status}" | tr '[:upper:]' '[:lower:]')"
    case "${status}" in
      ready) return 0 ;;
      failed)
        printf '%s\n' "${response}" >&2
        return 1
        ;;
    esac
    sleep 2
  done
  echo "Timed out waiting for analyzer readiness: ${analyzer_url}" >&2
  return 1
}

put_analyzer() {
  local analyzer_id="$1"
  local schema_file="$2"
  local analyzer_url="${FOUNDRY_ENDPOINT%/}/contentunderstanding/analyzers/${analyzer_id}?api-version=${API_VERSION}"
  local existing_status
  existing_status="$(curl --silent --output /dev/null --write-out '%{http_code}' \
    -H "Authorization: Bearer ${TOKEN}" \
    "${analyzer_url}")"
  if [[ "${existing_status}" == "200" ]]; then
    poll_analyzer_ready "${analyzer_url}"
    echo "Analyzer ${analyzer_id} already exists and is ready"
    return 0
  fi
  if [[ "${existing_status}" != "404" ]]; then
    echo "Unexpected status checking analyzer ${analyzer_id}: ${existing_status}" >&2
    return 1
  fi

  local headers
  headers="$(mktemp)"
  trap 'rm -f "${headers}"' RETURN

  curl --fail --silent --show-error \
    --dump-header "${headers}" \
    --request PUT \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    --data-binary "@${schema_file}" \
    "${analyzer_url}" \
    >/dev/null

  local operation_url
  operation_url="$(awk 'BEGIN {IGNORECASE=1} /^operation-location:/ {$1=""; sub(/^ /,""); gsub(/\r/,""); print}' "${headers}")"
  if [[ -n "${operation_url}" ]]; then
    poll_operation "${operation_url}"
  fi
  poll_analyzer_ready "${analyzer_url}"
  rm -f "${headers}"
  echo "Configured analyzer ${analyzer_id} and confirmed readiness"
}

put_analyzer "flvVehicleAnalyzer" "${SCRIPT_DIR}/analyzers/vehicle-image.json"
put_analyzer "flvVehicleDocumentAnalyzer" "${SCRIPT_DIR}/analyzers/vehicle-document.json"
