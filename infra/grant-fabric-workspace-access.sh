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
# Single HNS-enabled storage account used for both the app's flv-content container
# and the cu-results container the Fabric OneLake shortcut reads. HNS is required for
# ADLS Gen2/OneLake shortcuts; it does not support blob index tags, so Defender for
# Storage malware-scan tags will not appear on blobs here (an accepted trade-off for a
# single, simpler storage account).
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
