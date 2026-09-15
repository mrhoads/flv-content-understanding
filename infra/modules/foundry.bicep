param location string
param foundryAccountName string
param foundryProjectName string
param modelDeploymentName string
param modelName string
param modelVersion string
param tags object

var accountBaseEndpoint = 'https://${foundryAccountName}.services.ai.azure.com'

// Deploy Microsoft Foundry Account (AIServices S0)
resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: foundryAccountName
  location: location
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    allowProjectManagement: true
    customSubDomainName: foundryAccountName
    disableLocalAuth: true
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Allow'
    }
    publicNetworkAccess: 'Enabled'
  }
}

// Deploy Foundry Project
resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: foundryAccount
  name: foundryProjectName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    displayName: 'Progressive FLV Demo'
    description: 'Foundry project for vehicle first-look verification.'
  }
}

// Regional deployment required because subscription policy denies GlobalStandard.
resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: foundryAccount
  name: modelDeploymentName
  sku: {
    name: 'Standard'
    capacity: 10
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: modelName
      version: modelVersion
    }
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
  }
}

@description('Foundry Account Endpoint')
output accountEndpoint string = 'https://${foundryAccount.properties.customSubDomainName}.services.ai.azure.com'

@description('Foundry Account ID')
output accountId string = foundryAccount.id

@description('Foundry Project Endpoint')
output projectEndpoint string = '${accountBaseEndpoint}/api/projects/${foundryProject.name}'

@description('Document Intelligence Endpoint')
output documentIntelligenceEndpoint string = 'https://${foundryAccount.properties.customSubDomainName}.cognitiveservices.azure.com'

@description('Foundry Project Name')
output projectName string = foundryProject.name

@description('Foundry Account Resource Name')
output accountName string = foundryAccount.name
