param location string
param accountName string
param modelDeploymentName string
param modelName string
param modelVersion string
param embeddingDeploymentName string
param embeddingModelName string
param embeddingModelVersion string
param tags object

resource contentUnderstandingAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: accountName
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
    customSubDomainName: accountName
    disableLocalAuth: true
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Allow'
    }
    publicNetworkAccess: 'Enabled'
  }
}

resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: contentUnderstandingAccount
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

resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: contentUnderstandingAccount
  name: embeddingDeploymentName
  sku: {
    name: 'Standard'
    capacity: 10
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: embeddingModelName
      version: embeddingModelVersion
    }
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
  }
  dependsOn: [
    modelDeployment
  ]
}

@description('Content Understanding account name')
output accountName string = contentUnderstandingAccount.name

@description('Content Understanding data-plane endpoint')
output accountEndpoint string = 'https://${contentUnderstandingAccount.properties.customSubDomainName}.services.ai.azure.com'
