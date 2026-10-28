@description('Name of the Consumption Logic App. Deploying over an existing name replaces its workflow definition.')
@minLength(1)
param logicAppName string

@description('Use the existing Logic App location when updating a resource.')
param location string = resourceGroup().location

@description('SharePoint hostname without a scheme or trailing slash.')
@minLength(1)
param sharePointHost string

@description('Complete SharePoint sharing URL. Never save this value in a committed parameter file.')
@secure()
@minLength(1)
param sharingUrl string

@description('Exact MP4 filename expected when resolving the sharing URL.')
@minLength(1)
param expectedFileName string

@description('Content Understanding endpoint, including https:// and without a trailing slash.')
@minLength(1)
param contentUnderstandingEndpoint string

param analyzerId string = 'cuTownHallAnalyzer'
param contentUnderstandingApiVersion string = '2025-11-01'

resource workflow 'Microsoft.Logic/workflows@2019-05-01' = {
  name: logicAppName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    state: 'Enabled'
    definition: loadJsonContent('workflow.json')
    parameters: {
      sharePointHost: {
        value: sharePointHost
      }
      sharingUrl: {
        value: sharingUrl
      }
      expectedFileName: {
        value: expectedFileName
      }
      contentUnderstandingEndpoint: {
        value: contentUnderstandingEndpoint
      }
      analyzerId: {
        value: analyzerId
      }
      contentUnderstandingApiVersion: {
        value: contentUnderstandingApiVersion
      }
    }
  }
}

output workflowResourceId string = workflow.id
output managedIdentityPrincipalId string = workflow.identity.principalId
