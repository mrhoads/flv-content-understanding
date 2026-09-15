param location string
param workspaceName string
param tags object

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2026-03-01' = {
  name: workspaceName
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

@description('Log Analytics Workspace ID')
output workspaceId string = logAnalyticsWorkspace.id

@description('Log Analytics Workspace Name')
output workspaceName string = logAnalyticsWorkspace.name

@description('Log Analytics Workspace Customer ID')
output customerId string = logAnalyticsWorkspace.properties.customerId

@description('Log Analytics Workspace Primary Key')
@secure()
output workspaceKey string = logAnalyticsWorkspace.listKeys().primarySharedKey
