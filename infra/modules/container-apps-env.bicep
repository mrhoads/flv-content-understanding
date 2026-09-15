param location string
param environmentName string
param workspaceCustomerId string
@secure()
param workspaceKey string
param tags object

resource containerAppEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: environmentName
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: workspaceCustomerId
        sharedKey: workspaceKey
      }
    }
  }
}

@description('Container Apps Environment ID')
output environmentId string = containerAppEnvironment.id

@description('Container Apps Environment Name')
output name string = containerAppEnvironment.name

@description('Container Apps Environment Default Domain')
output defaultDomain string = containerAppEnvironment.properties.defaultDomain
