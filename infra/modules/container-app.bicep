param location string
param appName string
param environmentId string
param containerImage string
param isPlaceholder bool
param registryLoginServer string
param managedIdentityId string
param managedIdentityClientId string
param keyVaultEndpoint string
param storageAccountUrl string
param appInsightsConnectionString string
param foundryProjectEndpoint string
param contentUnderstandingEndpoint string
param documentIntelligenceEndpoint string
param tags object

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      secrets: isPlaceholder ? [] : [
        {
          name: 'app-encryption-key-secret'
          keyVaultUrl: '${keyVaultEndpoint}secrets/app-encryption-key'
          identity: managedIdentityId
        }
        {
          name: 'internal-access-key-secret'
          keyVaultUrl: '${keyVaultEndpoint}secrets/internal-access-key'
          identity: managedIdentityId
        }
      ]
      registries: isPlaceholder ? [] : [
        {
          server: registryLoginServer
          identity: managedIdentityId
        }
      ]
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
      }
    }
    template: {
      containers: [
        {
          image: containerImage
          name: 'content-understanding-app'
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: isPlaceholder ? [] : [
            {
              name: 'APP_ENV'
              value: 'production'
            }
            {
              name: 'AZURE_CLIENT_ID'
              value: managedIdentityClientId
            }
            {
              name: 'DEMO_MODE'
              value: 'false'
            }
            {
              name: 'MAX_UPLOAD_MB'
              value: '15'
            }
            {
              name: 'APP_ENCRYPTION_KEY'
              secretRef: 'app-encryption-key-secret'
            }
            {
              name: 'INTERNAL_ACCESS_KEY'
              secretRef: 'internal-access-key-secret'
            }
            {
              name: 'STORAGE_BACKEND'
              value: 'azure'
            }
            {
              name: 'AZURE_STORAGE_ACCOUNT_URL'
              value: storageAccountUrl
            }
            {
              name: 'AZURE_STORAGE_CONTAINER'
              value: 'flv-content'
            }
            {
              name: 'FOUNDRY_PROJECT_ENDPOINT'
              value: foundryProjectEndpoint
            }
            {
              name: 'FOUNDRY_MODEL_DEPLOYMENT'
              value: 'gpt-4-1-mini-flv'
            }
            {
              name: 'FOUNDRY_CUSTOMER_AGENT_NAME'
              value: 'flv-customer-agent'
            }
            {
              name: 'FOUNDRY_EMPLOYEE_AGENT_NAME'
              value: 'flv-employee-agent'
            }
            {
              name: 'CONTENT_UNDERSTANDING_ENDPOINT'
              value: contentUnderstandingEndpoint
            }
            {
              name: 'CONTENT_UNDERSTANDING_IMAGE_ANALYZER_ID'
              value: 'flvVehicleAnalyzer'
            }
            {
              name: 'CONTENT_UNDERSTANDING_DOCUMENT_ANALYZER_ID'
              value: 'flvVehicleDocumentAnalyzer'
            }
            {
              name: 'CONTENT_UNDERSTANDING_API_VERSION'
              value: '2025-11-01'
            }
            {
              name: 'DOCUMENT_INTELLIGENCE_ENDPOINT'
              value: documentIntelligenceEndpoint
            }
            {
              name: 'DOCUMENT_INTELLIGENCE_API_VERSION'
              value: '2023-07-31'
            }
            {
              name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
              value: appInsightsConnectionString
            }
          ]
          probes: [
            {
              type: 'liveness'
              httpGet: {
                path: '/health'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 5
              periodSeconds: 10
              timeoutSeconds: 2
              failureThreshold: 3
            }
            {
              type: 'readiness'
              httpGet: {
                path: '/health'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 5
              periodSeconds: 10
              timeoutSeconds: 2
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 3
        rules: [
          {
            name: 'http-requests'
            http: {
              metadata: {
                concurrentRequests: '20'
              }
            }
          }
        ]
      }
    }
  }
}

@description('Container App URL')
output appUrl string = 'https://${containerApp.properties.configuration.ingress.fqdn}'

@description('Container App Name')
output name string = containerApp.name

@description('Container App ID')
output resourceId string = containerApp.id
