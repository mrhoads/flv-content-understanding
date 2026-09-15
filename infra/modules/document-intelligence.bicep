param location string
param accountName string
param tags object

resource documentIntelligence 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: accountName
  location: location
  kind: 'FormRecognizer'
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
      defaultAction: 'Allow'
    }
    publicNetworkAccess: 'Enabled'
  }
}

@description('Document Intelligence account name')
output accountName string = documentIntelligence.name

@description('Document Intelligence data-plane endpoint')
output accountEndpoint string = 'https://${documentIntelligence.properties.customSubDomainName}.cognitiveservices.azure.com'
