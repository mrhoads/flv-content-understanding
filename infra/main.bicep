targetScope = 'subscription'

@description('Environment name (e.g., flv-demo-dev-e9fd)')
param environmentName string

@description('Azure region for all resources')
param location string = 'northcentralus'

@description('Session ID for unique resource naming')
param sessionId string

@description('User deploying the resources')
param deployedBy string

@description('ISO 8601 timestamp of deployment')
param createdAt string

@description('Object ID of the user performing the deployment (for Key Vault admin access)')
param deployerObjectId string

@description('Container image to run. The default supports the infrastructure-only first deployment.')
param containerImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('Set false after the application image is built and Key Vault secrets are populated.')
param isPlaceholder bool = true

// Standard tags applied to all resources
var commonTags = {
  'app-onboard-skill': 'true'
  'app-onboard-session-id': sessionId
  'created-at': createdAt
  'deployed-by': deployedBy
  securityControl: 'Ignore'
  environment: environmentName
}

// Resource naming from prepare-plan.json
var rgName = 'demo-prg-flv-rg'
var containerAppName = 'ca-flv-demo-dev-e9fd'
var containerAppEnvName = 'cae-flv-demo-dev-e9fd'
var containerRegistryName = 'crflvdemodeve9fd'
var managedIdentityName = 'id-flv-demo-dev-e9fd'
var storageAccountName = 'stflvdemodeve9fd'
var keyVaultName = 'kv-flv-demo-dev-e9fd'
var logAnalyticsName = 'log-flv-demo-dev-e9fd'
var appInsightsName = 'appi-flv-demo-dev-e9fd'
var foundryAccountName = 'aif-flv-demo-dev-e9fd'
var foundryProjectName = 'proj-flv-demo-dev-e9fd'
var contentUnderstandingAccountName = 'aif-flv-cu-dev-e9fd04'
var documentIntelligenceAccountName = 'di-flv-demo-dev-e9fd'

// Create Resource Group
resource resourceGroup 'Microsoft.Resources/resourceGroups@2023-07-01' = {
  name: rgName
  location: location
  tags: union(commonTags, {
    'resource-type': 'resourceGroup'
  })
}

// Deploy Log Analytics Workspace
module logAnalytics 'modules/log-analytics.bicep' = {
  scope: resourceGroup
  name: 'logAnalytics-${uniqueString(subscription().id, resourceGroup.id)}'
  params: {
    location: location
    workspaceName: logAnalyticsName
    tags: commonTags
  }
}

// Deploy Application Insights
module appInsights 'modules/app-insights.bicep' = {
  scope: resourceGroup
  name: 'appInsights-${uniqueString(subscription().id, resourceGroup.id)}'
  params: {
    location: location
    appInsightsName: appInsightsName
    workspaceId: logAnalytics.outputs.workspaceId
    tags: commonTags
  }
}

// Deploy Managed Identity
module managedIdentity 'modules/managed-identity.bicep' = {
  scope: resourceGroup
  name: 'managedIdentity-${uniqueString(subscription().id, resourceGroup.id)}'
  params: {
    location: location
    identityName: managedIdentityName
    tags: commonTags
  }
}

// Deploy Container Registry
module containerRegistry 'modules/container-registry.bicep' = {
  scope: resourceGroup
  name: 'containerRegistry-${uniqueString(subscription().id, resourceGroup.id)}'
  params: {
    location: location
    registryName: containerRegistryName
    tags: commonTags
  }
}

// Deploy Storage Account
module storage 'modules/storage.bicep' = {
  scope: resourceGroup
  name: 'storage-${uniqueString(subscription().id, resourceGroup.id)}'
  params: {
    location: location
    storageAccountName: storageAccountName
    containerName: 'flv-content'
    tags: commonTags
  }
}

// Deploy Key Vault
module keyVault 'modules/key-vault.bicep' = {
  scope: resourceGroup
  name: 'keyVault-${uniqueString(subscription().id, resourceGroup.id)}'
  params: {
    location: location
    vaultName: keyVaultName
    tags: commonTags
  }
}

// Deploy Container Apps Environment
module containerAppEnv 'modules/container-apps-env.bicep' = {
  scope: resourceGroup
  name: 'containerAppEnv-${uniqueString(subscription().id, resourceGroup.id)}'
  params: {
    location: location
    environmentName: containerAppEnvName
    workspaceCustomerId: logAnalytics.outputs.customerId
    workspaceKey: logAnalytics.outputs.workspaceKey
    tags: commonTags
  }
}

// Deploy Foundry Account and Project
module foundry 'modules/foundry.bicep' = {
  scope: resourceGroup
  name: 'foundry-${uniqueString(subscription().id, resourceGroup.id)}'
  params: {
    location: location
    foundryAccountName: foundryAccountName
    foundryProjectName: foundryProjectName
    modelDeploymentName: 'gpt-4-1-mini-flv'
    modelName: 'gpt-4.1-mini'
    modelVersion: '2025-04-14'
    tags: commonTags
  }
}

// Content Understanding is unavailable in North Central US, so it uses the approved East US 2 fallback.
module contentUnderstanding 'modules/content-understanding.bicep' = {
  scope: resourceGroup
  name: 'contentUnderstanding-${uniqueString(subscription().id, resourceGroup.id)}'
  params: {
    location: 'eastus2'
    accountName: contentUnderstandingAccountName
    modelDeploymentName: 'gpt-4-1-mini-cu-flv'
    modelName: 'gpt-4.1-mini'
    modelVersion: '2025-04-14'
    embeddingDeploymentName: 'text-embedding-3-large-cu-flv'
    embeddingModelName: 'text-embedding-3-large'
    embeddingModelVersion: '1'
    tags: commonTags
  }
}

module documentIntelligence 'modules/document-intelligence.bicep' = {
  scope: resourceGroup
  name: 'documentIntelligence-${uniqueString(subscription().id, resourceGroup.id)}'
  params: {
    location: location
    accountName: documentIntelligenceAccountName
    tags: commonTags
  }
}

// Deploy Role Assignments for RBAC
module roleAssignments 'modules/role-assignments.bicep' = {
  scope: resourceGroup
  name: 'roleAssignments-${uniqueString(subscription().id, resourceGroup.id)}'
  params: {
    keyVaultName: keyVault.outputs.vaultName
    containerRegistryId: containerRegistry.outputs.registryId
    storageAccountId: storage.outputs.storageAccountId
    foundryAccountName: foundry.outputs.accountName
    contentUnderstandingAccountName: contentUnderstanding.outputs.accountName
    documentIntelligenceAccountName: documentIntelligence.outputs.accountName
    managedIdentityPrincipalId: managedIdentity.outputs.principalId
    deployerObjectId: deployerObjectId
  }
}

// Deploy Container App after service identities and role assignments exist.
module containerApp 'modules/container-app.bicep' = {
  scope: resourceGroup
  name: 'containerApp-${uniqueString(subscription().id, resourceGroup.id)}'
  params: {
    location: location
    appName: containerAppName
    environmentId: containerAppEnv.outputs.environmentId
    containerImage: containerImage
    isPlaceholder: isPlaceholder
    registryLoginServer: containerRegistry.outputs.loginServer
    managedIdentityId: managedIdentity.outputs.identityId
    managedIdentityClientId: managedIdentity.outputs.clientId
    keyVaultEndpoint: keyVault.outputs.vaultUri
    storageAccountUrl: storage.outputs.blobEndpoint
    appInsightsConnectionString: appInsights.outputs.connectionString
    foundryProjectEndpoint: foundry.outputs.projectEndpoint
    contentUnderstandingEndpoint: contentUnderstanding.outputs.accountEndpoint
    documentIntelligenceEndpoint: documentIntelligence.outputs.accountEndpoint
    tags: commonTags
  }
  dependsOn: [
    roleAssignments
  ]
}

// Outputs
@description('Container App URL')
output containerAppUrl string = containerApp.outputs.appUrl

@description('Container Registry Login Server')
output containerRegistryLoginServer string = containerRegistry.outputs.loginServer

@description('Key Vault URI')
output keyVaultUri string = keyVault.outputs.vaultUri

@description('Storage Account Blob Endpoint')
output storageBlobEndpoint string = storage.outputs.blobEndpoint

@description('Foundry Account Endpoint')
output foundryAccountEndpoint string = foundry.outputs.accountEndpoint

@description('Managed Identity Principal ID')
output managedIdentityPrincipalId string = managedIdentity.outputs.principalId

@description('Foundry Project Endpoint')
output foundryProjectEndpoint string = foundry.outputs.projectEndpoint

@description('Content Understanding Endpoint')
output contentUnderstandingEndpoint string = contentUnderstanding.outputs.accountEndpoint

@description('Document Intelligence Endpoint')
output documentIntelligenceEndpoint string = documentIntelligence.outputs.accountEndpoint
