# SharePoint video analysis with Microsoft Graph and Logic Apps

Read a SharePoint video with an Azure Logic App's system-assigned managed identity,
then send its bytes to Azure Content Understanding for town hall analysis.
Every service call uses a built-in HTTP action: no SharePoint connector, service
keys, client secrets, or staging storage are required.

This is a separate Azure integration. It does not change the application's
`DEMO_MODE=true` default or require Azure for the local demo.

## Architecture

```text
Manual HTTP trigger
    |
    +-- Microsoft Graph: read the root site and resolve the file's sharing link
    |      Authentication: system-assigned managed identity
    |
    +-- HTTP GET: download bytes from Graph's temporary download URL
    |      Authentication: the URL itself is preauthenticated
    |
    +-- Verify file name, HTTP status, and downloaded size
    |
    +-- Content Understanding: POST cuTownHallAnalyzer:analyzeBinary
    |      Authentication: the same system-assigned managed identity
    |
    +-- Return HTTP 202 with operation URL and workflow run ID
    |
    +-- Poll the operation URL, then require Succeeded and nonempty contents
```

The initial HTTP 202 means the analysis was submitted, not completed. The
workflow continues running after the caller receives that response.

## Current demonstration resources

These are environment identifiers, not credentials. Replace them when using a
different tenant, Logic App, or Content Understanding resource.

| Setting | Value |
|---|---|
| Tenant ID | `72ed5f48-c1eb-47b1-a0b7-d4cd641a36bd` |
| Subscription ID | `c8fad4c4-3897-42b5-bbc2-5d96f255f209` |
| Logic App | `cu-sp-demo` |
| Logic App resource group | `demo-metlife-azcli-rg` |
| Logic App region | `northcentralus` |
| Managed identity object/principal ID | `5315b4cf-1e12-4913-a9f4-2eb4a8678c4d` |
| SharePoint host | `mngenvmcap024329.sharepoint.com` |
| Content Understanding account | `aif-flv-cu-dev-e9fd04` |
| Content Understanding resource group | `demo-prg-flv-rg` |
| Content Understanding endpoint | `https://aif-flv-cu-dev-e9fd04.services.ai.azure.com` |
| Analyzer ID | `cuTownHallAnalyzer` |
| Content Understanding API version | `2025-11-01` |

The existing town hall analyzer uses `prebuilt-video` as its base and whole-video
extraction (`enableSegment=false`). It must already exist and report `ready`;
the steps below grant access and invoke it, not create or replace its schema.

Do not commit the video's sharing URL, generated download URLs, workflow callback
URLs, access tokens, or analysis payloads.

## 1. Prepare local PowerShell

Use **PowerShell 7** (`pwsh`), not Windows PowerShell 5.1. Install only the Graph
modules needed for authentication, service-principal permissions, and optional
site-specific grants:

```powershell
Install-Module -Name Microsoft.Graph.Authentication,Microsoft.Graph.Applications,Microsoft.Graph.Sites `
    -Scope CurrentUser -Repository PSGallery

Import-Module Microsoft.Graph.Authentication
Import-Module Microsoft.Graph.Applications
Import-Module Microsoft.Graph.Sites

Get-Command Connect-MgGraph,Get-MgServicePrincipal,New-MgServicePrincipalAppRoleAssignment,New-MgSitePermission
```

Use `Get-PSRepository` to inspect configured package sources first. On the managed
machine used for this demonstration, the configured Microsoft package feed is
`azure-powershell`; use that repository name instead of `PSGallery`. The modules
were installed together at version `2.41.2`.

No execution-policy change is needed when the effective policy is already
`RemoteSigned` or otherwise permits these modules. Do not bypass an
organization-enforced policy.

Enable the Logic App's **Identity > System assigned** setting. Record its
**Object (principal) ID**. A managed identity is an Enterprise application/service
principal, not an app registration you configure under **App registrations**.

## 2. Grant Microsoft Graph read access to all sites

The demonstrated configuration uses the **application** permission
`Sites.Read.All`. This allows reading documents and list items across the tenant's
SharePoint sites. It is broader than a site-specific grant; use `Sites.Selected`
instead if access must be restricted to named sites.

Run the following locally as an authorized administrator in the target tenant,
typically an activated **Privileged Role Administrator** or **Global
Administrator**. Administrative consent to the requested delegated Graph scopes
may be required.

```powershell
$ErrorActionPreference = "Stop"
$tenantId = "72ed5f48-c1eb-47b1-a0b7-d4cd641a36bd"
$managedIdentityObjectId = "5315b4cf-1e12-4913-a9f4-2eb4a8678c4d"
$graphApplicationId = "00000003-0000-0000-c000-000000000000"
$permission = "Sites.Read.All"

Connect-MgGraph -TenantId $tenantId `
    -Scopes "Application.Read.All","AppRoleAssignment.ReadWrite.All" `
    -ContextScope Process

try {
    $identity = Get-MgServicePrincipal `
        -ServicePrincipalId $managedIdentityObjectId `
        -Property Id,AppId,DisplayName,ServicePrincipalType
    if ($identity.ServicePrincipalType -ne "ManagedIdentity") {
        throw "The supplied object ID is not a managed identity."
    }

    $graph = Get-MgServicePrincipal `
        -Filter "appId eq '$graphApplicationId'" -Property Id,AppRoles
    $roles = @($graph.AppRoles | Where-Object {
        $_.Value -eq $permission -and $_.IsEnabled -and
        $_.AllowedMemberTypes -contains "Application"
    })
    if ($roles.Count -ne 1) {
        throw "Could not resolve a unique $permission application role."
    }
    $role = $roles[0]

    $existing = Get-MgServicePrincipalAppRoleAssignment `
        -ServicePrincipalId $identity.Id -All |
        Where-Object {
            $_.ResourceId -eq $graph.Id -and $_.AppRoleId -eq $role.Id
        }
    if (-not $existing) {
        New-MgServicePrincipalAppRoleAssignment `
            -ServicePrincipalId $identity.Id `
            -PrincipalId $identity.Id `
            -ResourceId $graph.Id `
            -AppRoleId $role.Id | Out-Null
    }

    $verified = Get-MgServicePrincipalAppRoleAssignment `
        -ServicePrincipalId $identity.Id -All |
        Where-Object {
            $_.ResourceId -eq $graph.Id -and $_.AppRoleId -eq $role.Id
        }
    if (-not $verified) {
        throw "$permission assignment could not be verified."
    }
    Write-Host "Confirmed $permission on $($identity.DisplayName)."
}
finally {
    Disconnect-MgGraph | Out-Null
}
```

If interactive authentication fails because the embedded terminal cannot provide
a WAM window handle, add `-UseDeviceAuthentication` to `Connect-MgGraph` and
complete the sign-in promptly at the URL it displays. Device codes expire; never
save them in source control.

`Sites.Read.All` does **not** require `New-MgSitePermission`. Do not grant the
managed identity `Sites.FullControl.All` to perform this read-only integration.
Graph application permissions apply to Microsoft Graph requests, not directly to
SharePoint REST `/_api` requests.

### Alternative: restrict access to one site

For a restricted deployment, assign the identity the Graph application role
`Sites.Selected` instead of `Sites.Read.All` by changing `$permission` above.
Then run a separate administrative session to grant access to the site:

```powershell
Connect-MgGraph -TenantId $tenantId `
    -Scopes "Application.Read.All","Sites.FullControl.All" `
    -ContextScope Process

$identity = Get-MgServicePrincipal -ServicePrincipalId $managedIdentityObjectId `
    -Property AppId,DisplayName
$site = Get-MgSite `
    -SiteId "mngenvmcap024329.sharepoint.com:/sites/<site-name>"

New-MgSitePermission -SiteId $site.Id -Roles @("read") `
    -GrantedToIdentities @(@{
        Application = @{
            Id = $identity.AppId
            DisplayName = $identity.DisplayName
        }
    })

Disconnect-MgGraph
```

The administrator needs `Sites.FullControl.All` and a SharePoint Administrator
role or higher, and must be a member of the target site.
`Application.Id` in the site grant is the **client/application ID** (`AppId`),
not the identity's object/principal ID (`Id`). Inspect existing grants with
`Get-MgSitePermission` before creating another one.

Assigning `Sites.Selected` does not remove a previous `Sites.Read.All` grant;
that broad assignment must be separately removed to enforce site restrictions.
The workflow below was verified with `Sites.Read.All`. For a selected-site-only
variant, remove the unrelated tenant-root-site probe and use the permitted site's
drive/item IDs rather than assuming sharing-link resolution is supported.

## 3. Grant access to Content Understanding

Assign **Cognitive Services Content Understanding Reader** to the Logic App
identity at the Content Understanding account scope. Despite its name, this role
permits `analyze`, `analyzeBinary`, and result retrieval, without analyzer
creation/deletion or access-key listing.

Run this with Azure CLI as an operator authorized to create role assignments:

```powershell
az login --tenant "72ed5f48-c1eb-47b1-a0b7-d4cd641a36bd"
az account set --subscription "c8fad4c4-3897-42b5-bbc2-5d96f255f209"

$cuScope = "/subscriptions/c8fad4c4-3897-42b5-bbc2-5d96f255f209/resourceGroups/demo-prg-flv-rg/providers/Microsoft.CognitiveServices/accounts/aif-flv-cu-dev-e9fd04"

az role assignment create `
    --assignee-object-id "5315b4cf-1e12-4913-a9f4-2eb4a8678c4d" `
    --assignee-principal-type ServicePrincipal `
    --role "379c52cb-64de-498c-8b5b-c6170d6c49d4" `
    --scope $cuScope
```

Inspect existing assignments before repeating this grant. Azure RBAC and Graph
app-role assignments are separate permissions; both are needed. Allow time for
propagation and managed-identity token caches to refresh after changes.

## 4. Build the HTTP-only Logic App workflow

### Deploy the included code

[`workflow.json`](workflow.json) is the complete workflow definition, based on the
working demonstration. It parameterizes the SharePoint host, sharing URL, expected
filename, analyzer endpoint, analyzer ID, and API version, and additionally checks
that Graph identifies the input as `video/mp4`.
[`main.bicep`](main.bicep) loads that definition, enables the Logic App's
system-assigned identity, and passes the sharing URL as a secure parameter.
Neither file contains the video's sharing URL or generated credentials.

From the repository root, after signing in to the intended subscription, run:

```powershell
az deployment group create `
    --resource-group "demo-metlife-azcli-rg" `
    --template-file "sharepoint\main.bicep" `
    --parameters `
        logicAppName="cu-sp-demo" `
        location="northcentralus" `
        sharePointHost="mngenvmcap024329.sharepoint.com" `
        expectedFileName="4mjXPWPkWo8.mp4" `
        contentUnderstandingEndpoint="https://aif-flv-cu-dev-e9fd04.services.ai.azure.com" `
        analyzerId="cuTownHallAnalyzer"
```

Azure CLI prompts for the required secure `sharingUrl` parameter. Supply the
complete sharing URL interactively, not as a command-line argument or a committed
parameter value. Do not use `--no-prompt` for this interactive deployment.

**Deploying over an existing Logic App replaces its definition and workflow
parameters.** Back it up first, preserve its existing location, and do not use
this template on a resource with unrelated workflows or additional configuration.
It enables the workflow but does not invoke its manual trigger.

The template does not assign Graph application permissions, grant Content
Understanding RBAC, or create the analyzer. For a new Logic App, deploy it first
to obtain its `managedIdentityPrincipalId` output, then perform steps 2 and 3
using that principal ID before running the workflow. When updating the same
resource without disabling or recreating its identity, its existing identity
and grants remain in place.

The sections below explain the actions in the JSON so the workflow can also be
reviewed or adapted in the Logic App designer.

### Configure the trigger and parameters

The demonstrated Logic App is a Consumption resource
(`Microsoft.Logic/workflows`), so the workflow is the Logic App itself. Back up
any existing definition before replacing it; do not overwrite unrelated work.
The demonstrated resource was empty before this workflow was created.

Use **When an HTTP request is received** as the manual trigger. No recurrence is
needed. Treat its signed callback URL as a secret.

Define these workflow parameters:

| Parameter | Type | Value |
|---|---|---|
| `sharingUrl` | `SecureString` | Supply your video sharing URL at deployment; no committed default |
| `sharePointHost` | `String` | `mngenvmcap024329.sharepoint.com` |
| `expectedFileName` | `String` | `4mjXPWPkWo8.mp4` |
| `contentUnderstandingEndpoint` | `String` | `https://aif-flv-cu-dev-e9fd04.services.ai.azure.com` |
| `analyzerId` | `String` | `cuTownHallAnalyzer` |
| `contentUnderstandingApiVersion` | `String` | `2025-11-01` |

### Read the site and resolve the file

Add **HTTP** actions, not SharePoint connector actions. On each Graph request,
set authentication to **Managed identity**, select the **system-assigned**
identity, and set the audience to `https://graph.microsoft.com`.

Use `Read_SharePoint_root_site` for an initial access probe:

```http
GET https://graph.microsoft.com/v1.0/sites/mngenvmcap024329.sharepoint.com?$select=id,webUrl
```

After it succeeds, add `Resolve_shared_file` with method `GET` and this URI
expression. Graph sharing tokens are `u!` followed by the unpadded base64url
encoding of the complete sharing URL:

```text
@concat('https://graph.microsoft.com/v1.0/shares/u!', replace(replace(replace(base64(parameters('sharingUrl')), '=', ''), '/', '_'), '+', '-'), '/driveItem')
```

Enable **Secure Inputs** and **Secure Outputs** for this action. Its response
includes the file's name, size, MIME type, drive/item identifiers, and the
temporary `@microsoft.graph.downloadUrl`.

Sharing-link resolution succeeded with this identity's `Sites.Read.All` grant.
The Graph shares API documentation lists broader permissions for its general
contract; do not automatically grant write access if link resolution fails in a
different environment. Resolve the file by its known site/drive/item path instead.

### Download and verify the bytes

Check that the resolved name is the expected file and that its size is valid.
The current demonstration expects `4mjXPWPkWo8.mp4` with at least 1,024 bytes.
The included code uses `expectedFileName` for this guard and also requires MIME
type `video/mp4`. Supply a different expected filename when choosing another
MP4; reject mismatches explicitly.

Inside that successful condition, add `Read_file_content`:

| Setting | Value |
|---|---|
| Action | Built-in HTTP |
| Method | `GET` |
| URI | `@body('Resolve_shared_file')?['@microsoft.graph.downloadUrl']` |
| Authentication | None; this Graph-issued URL is already preauthenticated |
| Secure Inputs / Outputs | Both enabled |

Do **not** attach a Graph bearer token to the temporary download URL. Graph's
`/drives/{drive-id}/items/{item-id}/content` endpoint returns an HTTP 302 to this
same kind of URL. In this Logic App, the direct `/content` request was reported
as `Found` rather than followed automatically, so the workflow explicitly uses
Graph's returned download URL.

After the download, require HTTP 200 and a `Content-Length` matching the size
from Graph before submitting to Content Understanding. Account for header casing:

```text
@outputs('Read_file_content')?['statusCode']

@int(coalesce(outputs('Read_file_content')?['headers']?['Content-Length'], outputs('Read_file_content')?['headers']?['content-length'], '0'))

@int(body('Resolve_shared_file')?['size'])
```

Fail the workflow if the checks do not match. The size check above expects a
full-file response with a content-length header, as returned in this demo.

Do not use `Range: bytes=0-1023` as a bounded download test in this workflow.
Logic Apps treats a 206 response as a chunked download and can automatically
fetch the remaining file; status/header fields can also be unavailable in the
assembled output. The working flow intentionally downloads the full file.

### Submit to the town hall analyzer

Add `Submit_to_town_hall_analyzer` after the successful byte-count check:

| Setting | Value |
|---|---|
| Method | `POST` |
| URI | Expression below |
| `Content-Type` | `video/mp4` |
| Body | `@body('Read_file_content')` |
| Authentication | System-assigned managed identity |
| Audience | `https://cognitiveservices.azure.com` |
| Asynchronous pattern | Off (`"operationOptions": "DisableAsyncPattern"`) |
| Retry policy | None, to avoid automatic duplicate analysis submissions |
| Secure Inputs / Outputs | Both enabled |

```text
@concat(parameters('contentUnderstandingEndpoint'), '/contentunderstanding/analyzers/', parameters('analyzerId'), ':analyzeBinary?api-version=', parameters('contentUnderstandingApiVersion'))
```

For the current deployment this calls:

```http
POST https://aif-flv-cu-dev-e9fd04.services.ai.azure.com/contentunderstanding/analyzers/cuTownHallAnalyzer:analyzeBinary?api-version=2025-11-01
Content-Type: video/mp4

<raw video bytes>
```

This is **`analyzeBinary`**, not **`analyze`**. Do not JSON-wrap or base64-encode
the video body. `analyze` instead accepts JSON such as
`{"inputs":[{"url":"https://..."}]}` and requires the service to fetch that URL.
Binary submission avoids a staging blob and a storage SAS.

The service responds with HTTP 202, an operation ID, and an `Operation-Location`
header. Preserve this URL for polling:

```text
@coalesce(outputs('Submit_to_town_hall_analyzer')?['headers']?['Operation-Location'], outputs('Submit_to_town_hall_analyzer')?['headers']?['operation-location'])
```

### Respond promptly, then poll for completion

After submission succeeds, return HTTP 202 to the original caller. Include the
analyzer ID, file name, bytes read, analysis operation ID, operation URL, and
`@workflow().run.name`. Do not return the video, sharing URL, download URL, or
bearer tokens.

Continue after that Response action with an **Until** loop:

1. `Get_analysis_result`: HTTP `GET` to the operation URL, authenticated with the
   system-assigned identity and audience `https://cognitiveservices.azure.com`.
   Enable Secure Inputs and Secure Outputs.
2. Wait 10 seconds between polls. Stop for `Succeeded`, `Failed`, `Canceled`, or
   `Cancelled`, comparing status case-insensitively.
3. Bound the loop to 180 iterations and 30 minutes. Use
   `"operationOptions": "FailWhenLimitsReached"` so hitting the limit fails
   rather than appearing successful.
4. Require a final `Succeeded` status and a nonempty `result.contents` array.
   Otherwise explicitly terminate the workflow as failed.

The existing workflow retains the result in `Analysis_completed`. Its Compose
action uses Secure Inputs; Compose does not support explicitly configuring
`secureData.properties=["outputs"]`, and secured inputs protect its output too.
Results are not written to Blob Storage or Microsoft Fabric by this workflow.
If adding durable storage later, use a private container and managed identity.

## 5. Run and inspect the analysis

In the Logic App, select **Run trigger > manual**, then inspect **Runs history**.
The Graph read, file download, analyzer submission, polling, and completion
condition must all succeed. The initial caller response alone is not proof of
successful analysis.

The submission response's operation URL also lets an authorized operator
retrieve the result independently:

```powershell
$operationLocation = "<operationLocation returned by the workflow>"
az rest --method get --url $operationLocation `
    --resource "https://cognitiveservices.azure.com"
```

The operator needs Content Understanding result-read access as well. This
operator request retrieves a result; the Logic App's own submission and polling
are authenticated as the managed identity.

A local `Connect-MgGraph` administrator session cannot prove the identity's
effective SharePoint access. The HTTP actions running inside the Logic App are
the end-to-end test. A system-assigned identity cannot be directly impersonated
from a laptop or an unrelated Cloud Shell session.

### Verified demonstration

On October 28, 2026, the workflow read `4mjXPWPkWo8.mp4` and successfully invoked
`cuTownHallAnalyzer`:

| Check | Result |
|---|---|
| Downloaded bytes | `16,838,495`, matching the Graph-reported file size |
| Content Understanding submission | HTTP 202 |
| Final Logic App run | `Succeeded` |
| Final analysis status | `Succeeded` |
| Analysis contents | 1 |
| Extracted field names | 21 |
| Service warnings | None |
| End-to-end duration | Approximately 2 minutes 37 seconds |

The fields include `ExecutiveSummary`, `AgendaTopics`, `Speakers`,
`KeyAnnouncements`, `QuestionsAndAnswers`, `Decisions`, `ActionItems`,
`SlidesShared`, and `ChartsShared`. Full analysis payloads are intentionally not
committed here.

## Limits and troubleshooting

This is a single-video demonstration, not an unrestricted large-file pipeline.
Content Understanding's documented `analyzeBinary` video limits are 200 MB and
30 minutes. Logic Apps request/action size and timeout limits also apply and may
be lower; check both before substituting a larger town hall recording. For
larger recordings, design a private-storage URL-based `analyze` path instead of
silently switching this workflow to public storage.

| Symptom | Check |
|---|---|
| Graph HTTP 403 | Correct identity, Graph application role, tenant, permission propagation, and sharing-link compatibility |
| Content Understanding HTTP 403 | Account-scoped Content Understanding Reader assignment and Cognitive Services token audience |
| Graph file read reports `Found` | Follow the temporary Graph download URL explicitly; do not forward the Graph token |
| Unexpected downloaded size | File guard, response headers, header casing, or unintended range/chunked transfer |
| HTTP 202 but no completed result | Poll the operation URL and inspect the final workflow status; submission is asynchronous |
| HTTP 502 `NoResponse` | An action failed before the Response action, or submission exceeded the request-response window; inspect Runs history |
| Protected inputs/outputs are not visible | Expected security behavior; use authorized operation-result retrieval rather than disabling protection |

Do not disable secure logging settings just to inspect video bytes or temporary
URLs. Keep both SharePoint and Content Understanding authorization scoped to the
intended environment.

## References

- [Original managed-identity SharePoint article](https://techcommunity.microsoft.com/blog/azurearchitectureblog/granting-azure-resources-access-to-sharepoint-online-sites-using-managed-identit/4409633)
- [Install Microsoft Graph PowerShell](https://learn.microsoft.com/powershell/microsoftgraph/installation)
- [Assign managed-identity app roles](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/assign-app-role-managed-identity-powershell)
- [Create a site permission](https://learn.microsoft.com/graph/api/site-post-permissions?view=graph-rest-1.0)
- [Access shared items with Graph](https://learn.microsoft.com/graph/api/shares-get?view=graph-rest-1.0)
- [Download drive item content](https://learn.microsoft.com/graph/api/driveitem-get-content?view=graph-rest-1.0)
- [Logic Apps managed identity authentication](https://learn.microsoft.com/azure/logic-apps/authenticate-with-managed-identity)
- [Logic Apps chunked downloads](https://learn.microsoft.com/azure/logic-apps/logic-apps-handle-large-messages)
- [Content Understanding analyzeBinary API](https://learn.microsoft.com/rest/api/contentunderstanding/content-analyzers/analyze-binary?view=rest-contentunderstanding-2025-11-01)
- [Content Understanding service limits](https://learn.microsoft.com/azure/ai-services/content-understanding/service-limits)
