#!/usr/bin/env bash
set -euo pipefail

KEY_VAULT_NAME="${KEY_VAULT_NAME:-kv-flv-demo-dev-e9fd}"
APP_ENCRYPTION_KEY="${APP_ENCRYPTION_KEY:-$(python3 -c 'import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())')}"
INTERNAL_ACCESS_KEY="${INTERNAL_ACCESS_KEY:-$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')}"

az keyvault secret set \
  --vault-name "${KEY_VAULT_NAME}" \
  --name app-encryption-key \
  --value "${APP_ENCRYPTION_KEY}" \
  --output none

az keyvault secret set \
  --vault-name "${KEY_VAULT_NAME}" \
  --name internal-access-key \
  --value "${INTERNAL_ACCESS_KEY}" \
  --output none

echo "Demo secrets stored in ${KEY_VAULT_NAME}."
echo "Retrieve the employee key with:"
echo "az keyvault secret show --vault-name ${KEY_VAULT_NAME} --name internal-access-key --query value -o tsv"

