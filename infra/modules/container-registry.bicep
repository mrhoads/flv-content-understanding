param location string
param registryName string
param tags object

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2025-11-01' = {
  name: registryName
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
    networkRuleBypassOptions: 'AzureServices'
  }
}

@description('Container Registry ID')
output registryId string = containerRegistry.id

@description('Container Registry Login Server')
output loginServer string = containerRegistry.properties.loginServer

@description('Container Registry Name')
output name string = containerRegistry.name
