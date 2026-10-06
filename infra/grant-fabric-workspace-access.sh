#!/usr/bin/env bash
# Grants a Microsoft Fabric workspace identity read-only access to the cu-results
# Blob container so a OneLake shortcut can ingest Content Understanding JSON output
# without any SAS token, account key, or secret. Run this after:
#   1. infra/main.bicep has been deployed (creates the cu-results container), and
#   2. Workspace identity has been enabled in Fabric
#      (Workspace settings > Workspace identity > Create), which produces a
#      service-principal object ID shown in that same screen.
#
# Usage:
#   ./infra/grant-fabric-workspace-access.sh <fabric-workspace-identity-object-id>
set -euo pipefail

FABRIC_PRINCIPAL_ID="${1:?Usage: $0 <fabric-workspace-identity-object-id>}"
RESOURCE_GROUP="demo-prg-flv-rg"
# Dedicated, HNS-enabled storage account for the Fabric OneLake shortcut. Not the
# production flv-content account: ADLS Gen2 (HNS) requires no blob index tags, and the
# production account has Defender for Storage malware-scanning tags on its blobs.
STORAGE_ACCOUNT_NAME="stflvfabricdeve9fd"

STORAGE_ACCOUNT_ID=$(az storage account show \
  --name "$STORAGE_ACCOUNT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query id -o tsv)

az role assignment create \
  --assignee-object-id "$FABRIC_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Reader" \
  --scope "$STORAGE_ACCOUNT_ID"

echo "Granted Storage Blob Data Reader on $STORAGE_ACCOUNT_NAME to Fabric workspace identity $FABRIC_PRINCIPAL_ID"
echo "Re-running infra/main.bicep with fabricWorkspaceIdentityPrincipalId set will make this grant idempotent/declarative going forward."
