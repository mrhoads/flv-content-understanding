@description('Name of an existing Storage Account to add a container to')
param storageAccountName string

@description('Name of the blob container to create')
param containerName string

resource storageAccount 'Microsoft.Storage/storageAccounts@2026-06-01' existing = {
  name: storageAccountName
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2026-06-01' existing = {
  parent: storageAccount
  name: 'default'
}

resource blobContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2026-06-01' = {
  parent: blobService
  name: containerName
  properties: {
    publicAccess: 'None'
  }
}

@description('Blob Container ID')
output blobContainerId string = blobContainer.id

@description('Blob Container Name')
output name string = blobContainer.name
