# Azure deployment guide

This package deploys the FLV demo to Azure Container Apps in two phases. The first phase creates infrastructure with a public placeholder image. The second phase runs the application image after managed-identity permissions and Key Vault secrets exist.

## Target

- Subscription: `01-ME-MngEnvMCAP024329-mirhoads-sandbox`
- Resource group: `demo-prg-flv-rg`
- Region: `northcentralus`
- Container App: `ca-flv-demo-dev-e9fd`
- Foundry project: `proj-flv-demo-dev-e9fd`
- Content Understanding: `aif-flv-cu-dev-e9fd04` in `eastus2`
- Document Intelligence: `di-flv-demo-dev-e9fd`
- Required tag: `securityControl=Ignore`

## 1. Validate

```bash
az bicep build --file infra/main.bicep
az deployment sub validate \
  --name flv-demo-validate \
  --location northcentralus \
  --template-file infra/main.bicep \
  --parameters infra/main.parameters.json
```

## 2. Deploy placeholder infrastructure

```bash
az deployment sub create \
  --name flv-demo-infra \
  --location northcentralus \
  --template-file infra/main.bicep \
  --parameters infra/main.parameters.json
```

This creates the resource group, identity, RBAC, storage, Key Vault, monitoring, ACR, Foundry account/project/model, the eastus2 Content Understanding account and models, a dedicated Document Intelligence account, the Container Apps environment, and a placeholder Container App.

## 3. Populate demo secrets

Role assignments can take several minutes to propagate.

```bash
bash infra/set-demo-secrets.sh
```

The script generates a Fernet encryption key and employee access key and stores both in Key Vault. It does not print either secret.

## 4. Build the application image

```bash
az acr build \
  --registry crflvdemodeve9fd \
  --image flv-demo:latest \
  --file infra/Dockerfile.azure \
  .

IMAGE="crflvdemodeve9fd.azurecr.io/flv-demo:latest"
```

## 5. Configure Foundry

Create the two prompt-agent versions with the current Foundry 2.x SDK in an isolated tools environment:

```bash
python3 -m venv .foundry-tools
.foundry-tools/bin/pip install -r infra/requirements-tools.txt

export FOUNDRY_PROJECT_ENDPOINT="https://aif-flv-demo-dev-e9fd.services.ai.azure.com/api/projects/proj-flv-demo-dev-e9fd"
export FOUNDRY_MODEL_DEPLOYMENT="gpt-4-1-mini-flv"
.foundry-tools/bin/python infra/configure-foundry-agents.py
```

Create or update the Content Understanding analyzers using Microsoft Entra tokens:

```bash
export CONTENT_UNDERSTANDING_ENDPOINT="https://aif-flv-cu-dev-e9fd04.services.ai.azure.com"
export CONTENT_UNDERSTANDING_API_VERSION="2025-11-01"
export CONTENT_UNDERSTANDING_MODEL_DEPLOYMENT="gpt-4-1-mini-cu-flv"
export CONTENT_UNDERSTANDING_EMBEDDING_DEPLOYMENT="text-embedding-3-large-cu-flv"
bash infra/configure-foundry-analyzers.sh
```

The script waits until both analyzers report `ready`. The application uses the dedicated `di-flv-demo-dev-e9fd` endpoint with Document Intelligence API `2023-07-31`, which is the supported prebuilt-document route for this North Central US resource.

## 6. Activate the application image

```bash
az deployment sub create \
  --name flv-demo-app \
  --location northcentralus \
  --template-file infra/main.bicep \
  --parameters infra/main.parameters.json \
  --parameters containerImage="$IMAGE" isPlaceholder=false
```

## 7. Verify

```bash
FQDN="$(az containerapp show \
  --name ca-flv-demo-dev-e9fd \
  --resource-group demo-prg-flv-rg \
  --query properties.configuration.ingress.fqdn -o tsv)"

curl --fail --show-error "https://${FQDN}/health"
```

Retrieve the employee demo key only when needed:

```bash
az keyvault secret show \
  --vault-name kv-flv-demo-dev-e9fd \
  --name internal-access-key \
  --query value -o tsv
```

## Security notes

- Azure credentials and service keys are not stored in source or application settings.
- The application uses a user-assigned managed identity for ACR, Blob Storage, Key Vault, Foundry agents, Content Understanding, and Document Intelligence.
- Storage shared-key authorization and public blob access are disabled.
- Key Vault uses RBAC with no access policies.
- The employee key is a demo boundary. Replace it with Microsoft Entra app-role authorization before production use.
- Public service endpoints remain enabled for the cost-optimized demo. Use private endpoints for a production security boundary.
