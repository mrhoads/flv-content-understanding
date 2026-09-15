# Deployment artifact manifest

## Infrastructure

- `main.bicep` — subscription-scoped orchestration and exact resource group creation
- `main.parameters.json` — non-secret deployment parameters
- `modules/*.bicep` — Container Apps, ACR, identity, storage, Key Vault, monitoring, Foundry, Content Understanding, Document Intelligence, and RBAC
- `bicepconfig.json` — LF formatting configuration

## Container

- `Dockerfile.azure` — Python 3.12, non-root Uvicorn image
- `../.dockerignore` — excludes local secrets, environments, tests, and session state

## Foundry configuration

- `configure-foundry-agents.py` — creates new versions of the customer and employee prompt agents
- `configure-foundry-analyzers.sh` — idempotently creates or updates both analyzers
- `analyzers/vehicle-image.json` — vehicle image extraction schema
- `analyzers/vehicle-document.json` — vehicle form and title extraction schema
- `requirements-tools.txt` — isolated deployment-tool dependencies

## Deployment support

- `set-demo-secrets.sh` — generates and stores the two application secrets in Key Vault
- `DEPLOYMENT_GUIDE.md` — two-phase manual deployment and verification procedure

All taggable resources receive `securityControl=Ignore` and `app-onboard-skill=true`.
