param location string
param vaultName string
param tags object

resource keyVault 'Microsoft.KeyVault/vaults@2026-05-15' = {
  name: vaultName
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    accessPolicies: []
    enableRbacAuthorization: true
    softDeleteRetentionInDays: 7
    enableSoftDelete: true
    enabledForDeployment: true
    enabledForTemplateDeployment: true
    enabledForDiskEncryption: false
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Allow'
    }
  }
}

@description('Key Vault Resource ID')
output vaultId string = keyVault.id

@description('Key Vault Name')
output vaultName string = keyVault.name

@description('Key Vault URI')
output vaultUri string = keyVault.properties.vaultUri
