param location string
param identityName string
param tags object

resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = {
  name: identityName
  location: location
  tags: tags
}

@description('Managed Identity Resource ID')
output identityId string = managedIdentity.id

@description('Managed Identity Client ID')
output clientId string = managedIdentity.properties.clientId

@description('Managed Identity Principal ID')
output principalId string = managedIdentity.properties.principalId
