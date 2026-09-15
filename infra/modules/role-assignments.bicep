param keyVaultName string
param containerRegistryId string
param storageAccountId string
param foundryAccountName string
param contentUnderstandingAccountName string
param documentIntelligenceAccountName string
param managedIdentityPrincipalId string
param deployerObjectId string

resource keyVault 'Microsoft.KeyVault/vaults@2026-05-15' existing = {
  name: keyVaultName
}

// Key Vault role definitions
var keyVaultSecretsOfficer = 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7'
var keyVaultSecretsUser = '4633458b-17de-408a-b874-0445c86b69e6'
var storageBlobDataContributor = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
var acrPull = '7f951dda-4ed3-4680-a7ca-43fe172d538d'
var cognitiveServicesUser = 'a97b65f3-24c7-4388-baec-2e87135dc908'
var foundryAgentConsumer = 'eed3b665-ab3a-47b6-8f48-c9382fb1dad6'

// Deployer gets Key Vault Secrets Officer
resource deployerKeyVaultRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: keyVault
  name: guid(keyVault.id, deployerObjectId, keyVaultSecretsOfficer)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsOfficer)
    principalId: deployerObjectId
    principalType: 'User'
  }
}

// Managed identity gets Key Vault Secrets User
resource appIdentityKeyVaultRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: keyVault
  name: guid(keyVault.id, managedIdentityPrincipalId, keyVaultSecretsUser)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsUser)
    principalId: managedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// Managed identity gets AcrPull for container registry
resource managedIdentityAcrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: containerRegistry
  name: guid(containerRegistry.id, managedIdentityPrincipalId, acrPull)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPull)
    principalId: managedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// Get reference to container registry
resource containerRegistry 'Microsoft.ContainerRegistry/registries@2025-11-01' existing = {
  name: last(split(containerRegistryId, '/'))
}

// Managed identity gets Storage Blob Data Contributor
resource managedIdentityStorageRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, managedIdentityPrincipalId, storageBlobDataContributor)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataContributor)
    principalId: managedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// Get reference to storage account
resource storage 'Microsoft.Storage/storageAccounts@2026-06-01' existing = {
  name: last(split(storageAccountId, '/'))
}

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: foundryAccountName
}

resource contentUnderstandingAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: contentUnderstandingAccountName
}

resource documentIntelligenceAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: documentIntelligenceAccountName
}

// Managed identity can invoke Foundry agents, models, and analysis APIs.
resource managedIdentityFoundryRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: foundryAccount
  name: guid(foundryAccount.id, managedIdentityPrincipalId, cognitiveServicesUser)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUser)
    principalId: managedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// Deployer configures Foundry agents and Content Understanding analyzers.
resource deployerFoundryRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: foundryAccount
  name: guid(foundryAccount.id, deployerObjectId, cognitiveServicesUser)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUser)
    principalId: deployerObjectId
    principalType: 'User'
  }
}

resource managedIdentityContentUnderstandingRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: contentUnderstandingAccount
  name: guid(contentUnderstandingAccount.id, managedIdentityPrincipalId, cognitiveServicesUser)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUser)
    principalId: managedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource deployerContentUnderstandingRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: contentUnderstandingAccount
  name: guid(contentUnderstandingAccount.id, deployerObjectId, cognitiveServicesUser)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUser)
    principalId: deployerObjectId
    principalType: 'User'
  }
}

resource managedIdentityDocumentIntelligenceRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: documentIntelligenceAccount
  name: guid(documentIntelligenceAccount.id, managedIdentityPrincipalId, cognitiveServicesUser)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUser)
    principalId: managedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// Managed identity can invoke the two project-scoped Foundry agents.
resource managedIdentityAgentConsumerRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: foundryAccount
  name: guid(foundryAccount.id, managedIdentityPrincipalId, foundryAgentConsumer)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', foundryAgentConsumer)
    principalId: managedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

@description('Deployer Key Vault Role Assignment ID')
output deployerKeyVaultRoleId string = deployerKeyVaultRole.id

@description('App Identity Key Vault Role Assignment ID')
output appIdentityKeyVaultRoleId string = appIdentityKeyVaultRole.id

@description('App Identity ACR Pull Role Assignment ID')
output appIdentityAcrPullRoleId string = managedIdentityAcrPullRole.id

@description('App Identity Storage Role Assignment ID')
output appIdentityStorageRoleId string = managedIdentityStorageRole.id

@description('App Identity Foundry Role Assignment ID')
output appIdentityFoundryRoleId string = managedIdentityFoundryRole.id

@description('Deployer Foundry Role Assignment ID')
output deployerFoundryRoleId string = deployerFoundryRole.id

@description('App Identity Content Understanding Role Assignment ID')
output appIdentityContentUnderstandingRoleId string = managedIdentityContentUnderstandingRole.id

@description('Deployer Content Understanding Role Assignment ID')
output deployerContentUnderstandingRoleId string = deployerContentUnderstandingRole.id

@description('App Identity Document Intelligence Role Assignment ID')
output appIdentityDocumentIntelligenceRoleId string = managedIdentityDocumentIntelligenceRole.id

@description('App Identity Foundry Agent Consumer Role Assignment ID')
output appIdentityAgentConsumerRoleId string = managedIdentityAgentConsumerRole.id
