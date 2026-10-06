param location string
param storageAccountName string
param containerName string
param tags object

@description('Enable Hierarchical Namespace (Azure Data Lake Storage Gen2). Required for OneLake/Fabric shortcuts. Set only at account creation time for a new, dedicated account - do not flip this on an existing account with blob index tags (e.g. from Defender for Storage malware scanning), since migration is a separate, one-way operation with its own prerequisites.')
param isHnsEnabled bool = false

resource storageAccount 'Microsoft.Storage/storageAccounts@2026-06-01' = {
  name: storageAccountName
  location: location
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  tags: tags
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    allowCrossTenantReplication: false
    allowSharedKeyAccess: false
    defaultToOAuthAuthentication: true
    dnsEndpointType: 'Standard'
    isHnsEnabled: isHnsEnabled
    encryption: {
      keySource: 'Microsoft.Storage'
      services: {
        blob: {
          enabled: true
        }
        file: {
          enabled: true
        }
        queue: {
          enabled: true
        }
        table: {
          enabled: true
        }
      }
    }
    minimumTlsVersion: 'TLS1_2'
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Allow'
    }
    publicNetworkAccess: 'Enabled'
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2026-06-01' = {
  parent: storageAccount
  name: 'default'
  properties: {
    changeFeed: {
      enabled: false
    }
  }
}

resource blobContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2026-06-01' = {
  parent: blobService
  name: containerName
  properties: {
    publicAccess: 'None'
  }
}

@description('Storage Account ID')
output storageAccountId string = storageAccount.id

@description('Storage Account Name')
output name string = storageAccount.name

@description('Blob Service ID')
output blobServiceId string = blobService.id

@description('Blob Container ID')
output blobContainerId string = blobContainer.id

@description('Blob Container Name')
output containerName string = blobContainer.name

@description('Blob Endpoint')
output blobEndpoint string = storageAccount.properties.primaryEndpoints.blob

@description('DFS (ADLS Gen2) Endpoint - used for OneLake shortcuts when isHnsEnabled is true')
output dfsEndpoint string = storageAccount.properties.primaryEndpoints.dfs
