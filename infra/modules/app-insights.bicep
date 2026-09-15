param location string
param appInsightsName string
param workspaceId string
param tags object

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: workspaceId
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
  tags: tags
}

resource failureAnomaliesRule 'Microsoft.AlertsManagement/smartDetectorAlertRules@2021-04-01' existing = {
  name: 'Failure Anomalies - ${appInsightsName}'
}

resource failureAnomaliesRuleTags 'Microsoft.Resources/tags@2024-11-01' = {
  name: 'default'
  scope: failureAnomaliesRule
  properties: {
    tags: tags
  }
  dependsOn: [
    appInsights
  ]
}

@description('Application Insights Instrumentation Key')
output instrumentationKey string = appInsights.properties.InstrumentationKey

@description('Application Insights Connection String')
output connectionString string = appInsights.properties.ConnectionString

@description('Application Insights Resource ID')
output resourceId string = appInsights.id
