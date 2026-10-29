# Read-only SharePoint access through Microsoft Graph

Use an Azure resource's system-assigned managed identity to read SharePoint
content through Microsoft Graph without passwords, client secrets, or a
SharePoint connector. This guide uses placeholders only.

Choose **one** permission model:

| Scope | Graph application permission | Additional site grant |
|---|---|---|
| One specific SharePoint site | `Sites.Selected` | `read` on that site |
| All SharePoint sites in the tenant | `Sites.Read.All` | None |

Prefer the specific-site option when possible. Neither procedure grants write
access. However, permissions are additive: adding a read grant does not remove
existing write access or broader access granted elsewhere.

## 1. Prerequisites and local setup

1. Enable **Identity > System assigned > On** on the Azure resource, such as a
   Logic App, Function App, or VM.
2. Record its **Object (principal) ID**. The identity appears in Microsoft Entra
   ID under **Enterprise applications**, not as a normal app registration.
3. Use **PowerShell 7** (`pwsh`) on your local machine.
4. Arrange the administrative permissions needed for the two operations:
   assigning Microsoft Graph application roles, and, for the specific-site
   option, granting access to the site.

Install the necessary modules from an organization-approved package repository:

```powershell
Get-PSRepository

Install-Module -Name Microsoft.Graph.Authentication,Microsoft.Graph.Applications,Microsoft.Graph.Sites `
    -Scope CurrentUser -Repository "<approved-PowerShell-repository-name>"

Import-Module Microsoft.Graph.Authentication
Import-Module Microsoft.Graph.Applications
Import-Module Microsoft.Graph.Sites
```

`PSGallery` is the public PowerShell Gallery repository name if your organization
permits it. Do not bypass organization execution policies or repository controls.

Set these placeholders once in your PowerShell session:

```powershell
$ErrorActionPreference = "Stop"
$tenantId = "<Microsoft-Entra-tenant-ID>"
$managedIdentityObjectId = "<managed-identity-object-or-principal-ID>"
$sharePointHost = "<tenant-name>.sharepoint.com"
$sitePath = "/sites/<site-name>"
```

Use the actual server-relative path for the site, such as `/sites/<site-name>`
or `/teams/<team-name>`. A document sharing link is not a site path.

### Object ID versus client ID

| Value | Used for |
|---|---|
| Managed identity object/principal ID (`Id`) | Looking up the service principal and assigning Graph application roles |
| Managed identity application/client ID (`AppId`) | `Application.Id` in `New-MgSitePermission` |
| Microsoft Graph service principal object ID | Resource receiving the app-role assignment |

The scripts below resolve `AppId` automatically from the identity object ID.
The Microsoft Graph application ID `00000003-0000-0000-c000-000000000000` is
a fixed Microsoft service identifier, not an environment-specific value.

## 2. Assign the selected Graph application permission

For either option, first assign the appropriate application role to the
managed identity. This is separate from Azure subscription RBAC.

Set **exactly one** of the following:

```powershell
# Option A: one specific site. Continue with section 3 afterward.
$permission = "Sites.Selected"

# Option B: all sites. Use this INSTEAD of the line above.
# $permission = "Sites.Read.All"
```

Run the following as an administrator authorized to assign Microsoft Graph
application permissions, typically an activated **Privileged Role Administrator**
or **Global Administrator** in the target tenant. The administrator's Graph
PowerShell session may require admin consent for its delegated scopes.

```powershell
Connect-MgGraph -TenantId $tenantId `
    -Scopes "Application.Read.All","AppRoleAssignment.ReadWrite.All" `
    -ContextScope Process

try {
    if ($permission -notin @("Sites.Selected", "Sites.Read.All")) {
        throw "Choose Sites.Selected or Sites.Read.All."
    }

    $identity = Get-MgServicePrincipal `
        -ServicePrincipalId $managedIdentityObjectId `
        -Property Id,AppId,DisplayName,ServicePrincipalType
    if ($identity.ServicePrincipalType -ne "ManagedIdentity") {
        throw "The supplied object ID is not a managed identity."
    }

    $graph = Get-MgServicePrincipal `
        -Filter "appId eq '00000003-0000-0000-c000-000000000000'" `
        -Property Id,AppRoles
    $roles = @($graph.AppRoles | Where-Object {
        $_.Value -eq $permission -and $_.IsEnabled -and
        $_.AllowedMemberTypes -contains "Application"
    })
    if ($roles.Count -ne 1) {
        throw "Could not resolve a unique $permission application role."
    }
    $role = $roles[0]

    # Review existing Graph application permissions before adding another.
    $assignments = @(Get-MgServicePrincipalAppRoleAssignment `
        -ServicePrincipalId $identity.Id -All)
    foreach ($assignment in $assignments) {
        if ($assignment.ResourceId -eq $graph.Id) {
            $assignedRole = $graph.AppRoles | Where-Object {
                $_.Id -eq $assignment.AppRoleId
            }
            [pscustomobject]@{
                AssignmentId = $assignment.Id
                GraphPermission = $assignedRole.Value
            }
        }
    }

    $existing = $assignments | Where-Object {
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
    $identity | Format-List DisplayName,Id,AppId
}
finally {
    Disconnect-MgGraph | Out-Null
}
```

If sign-in fails with a WAM/window-handle error in an embedded terminal, add
`-UseDeviceAuthentication` to `Connect-MgGraph` and complete the displayed
device sign-in promptly. Never save device codes or access tokens in the repo.

**Review existing permissions, not just the newly added permission.** For the
specific-site model, broad grants such as `Sites.Read.All`, `Files.Read.All`,
`Sites.ReadWrite.All`, `Files.ReadWrite.All`, or `Sites.FullControl.All` can
defeat the intended scope. For either model, existing write/full-control grants
can defeat the read-only requirement. Remove conflicting grants separately,
after assessing their impact; this script does not silently remove permissions.

## 3. Option A: grant READ access to one specific site

Complete this section only after assigning **`Sites.Selected`** in section 2.
`Sites.Selected` alone grants no site access.

Sign in as a **SharePoint Administrator or higher who is also a member of the
target site**, with consent for delegated `Sites.FullControl.All`. This scope is
for the administrative session only; do not assign it to the managed identity.

```powershell
Connect-MgGraph -TenantId $tenantId `
    -Scopes "Application.Read.All","Sites.FullControl.All" `
    -ContextScope Process

try {
    $identity = Get-MgServicePrincipal `
        -ServicePrincipalId $managedIdentityObjectId `
        -Property Id,AppId,DisplayName,ServicePrincipalType
    if ($identity.ServicePrincipalType -ne "ManagedIdentity") {
        throw "The supplied object ID is not a managed identity."
    }

    $site = Get-MgSite -SiteId "${sharePointHost}:$sitePath"
    $permissions = @(Get-MgSitePermission -SiteId $site.Id -All)
    $existing = @($permissions | Where-Object {
        $clientIds = @($_.GrantedToIdentitiesV2.Application.Id) +
            @($_.GrantedToIdentities.Application.Id)
        $clientIds -contains $identity.AppId
    })

    if ($existing.Count -gt 0) {
        $existing | Select-Object Id,Roles | Format-Table
        $notReadOnly = @($existing | Where-Object {
            @($_.Roles).Count -ne 1 -or $_.Roles -notcontains "read"
        })
        if ($notReadOnly.Count -gt 0) {
            throw "Existing site grants are not read-only. Review and remove or change them before proceeding."
        }
        Write-Host "A read-only site grant already exists."
    }
    else {
        New-MgSitePermission -SiteId $site.Id -Roles @("read") `
            -GrantedToIdentities @(@{
                Application = @{
                    Id = $identity.AppId
                    DisplayName = $identity.DisplayName
                }
            }) | Out-Null
    }

    $verified = @(Get-MgSitePermission -SiteId $site.Id -All |
        Where-Object {
            $clientIds = @($_.GrantedToIdentitiesV2.Application.Id) +
                @($_.GrantedToIdentities.Application.Id)
            $clientIds -contains $identity.AppId -and
                @($_.Roles).Count -eq 1 -and $_.Roles -contains "read"
        })
    if ($verified.Count -eq 0) {
        throw "The read-only site grant could not be verified."
    }
    Write-Host "Confirmed read access to $($site.WebUrl)."
    $verified | Select-Object Id,Roles | Format-Table
}
finally {
    Disconnect-MgGraph | Out-Null
}
```

The resulting combination is **`Sites.Selected` + site role `read`**.
No other site is authorized by this grant. If using an existing identity, review
its grants on other sites too: this procedure does not revoke them. A fresh
managed identity is the simplest way to demonstrate access to exactly one site.

## 4. Option B: READ access to all sites

Assign **`Sites.Read.All`** in section 2. That application permission provides
tenant-wide read access to SharePoint site content through Graph.

**Do not run `New-MgSitePermission` for this option.** It does not need
`Sites.Selected`, an individual site grant, or SharePoint site membership for
the managed identity. Do not substitute `Sites.ReadWrite.All` or
`Sites.FullControl.All`.

This is a broader authorization choice, not a way to make the one-site option
work. Use a separate identity when comparing both models so the broad grant
does not invalidate your site-isolation test.

## 5. Test using the managed identity, not your administrator account

Permission-assignment verification from your laptop confirms configuration.
The definitive access test must run **inside the Azure resource that owns the
system-assigned identity**. A laptop or unrelated Cloud Shell cannot directly
impersonate that identity.

### HTTP-only Logic App test

Create a manual request trigger and built-in **HTTP** actions. Do not use the
SharePoint connector.

For each Graph HTTP action, configure:

| Setting | Value |
|---|---|
| Method | `GET` |
| Authentication | Managed identity |
| Identity | System-assigned |
| Audience | `https://graph.microsoft.com` |
| Secure Inputs / Outputs | Enable when requests or responses contain sensitive content |

First test the intended site, replacing the hostname and path:

```http
GET https://graph.microsoft.com/v1.0/sites/<tenant-name>.sharepoint.com:/sites/<site-name>
```

Use the returned `id` for subsequent requests:

```http
GET https://graph.microsoft.com/v1.0/sites/<site-id>/drives
GET https://graph.microsoft.com/v1.0/drives/<drive-id>/root/children
GET https://graph.microsoft.com/v1.0/drives/<drive-id>/items/<file-item-id>
GET https://graph.microsoft.com/v1.0/drives/<drive-id>/items/<file-item-id>/content
```

To prove file-byte access, the `/content` request returns HTTP 302 to a
preauthenticated download URL. If the Logic App does not follow it automatically,
obtain `@microsoft.graph.downloadUrl` from the file metadata and use another HTTP
GET with **no authentication** to that temporary URL. Do not forward the Graph
token to the download endpoint. Protect that action's inputs and outputs, and do
not log or persist the temporary URL.

For **one-site access**, test a second, known-existing site that has not been
granted to the identity. Reading that site's protected content should fail.
Do not use the tenant root site as the initial success test unless it is the
site you explicitly authorized. If the second site's content is readable, inspect
broad Graph permissions and existing site grants before claiming isolation.

For **all-sites access**, repeat the read against another known-existing site.
Successful reads prove access to the tested resources; they do not prove that
every possible site or workload endpoint has been individually tested.

Prefer known site/drive/item paths for a selected-site test. Do not assume the
Graph sharing-link `/shares/...` API supports the same least-privilege
permissions as direct site/file endpoints, and do not add write permissions just
to resolve a sharing link.

### Troubleshooting and read-only checks

| Symptom | Check |
|---|---|
| Graph HTTP 403 | Correct principal, tenant, Graph application role, and, for `Sites.Selected`, the site's `read` grant |
| Graph HTTP 404 | Correct existing hostname, site path, drive ID, and file ID; a 404 alone is not proof of site isolation |
| Identity authentication fails | System-assigned identity is enabled and the test runs on its owning Azure resource |
| New grants do not take effect immediately | Allow for permission propagation and managed-identity token caching |
| Only the administrator can read | The test is probably using delegated user authentication instead of managed identity |
| Site-limited identity reads other sites | Check broad Graph application permissions and previous site grants |

Do not attempt a destructive write to prove read-only behavior. Review the
identity's full permission set and the site's roles instead. These procedures
authorize Microsoft Graph, not direct SharePoint REST `/_api` calls.

## References

- [Managed identity app-role assignment](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/assign-app-role-managed-identity-powershell)
- [Selected permissions overview](https://learn.microsoft.com/graph/permissions-selected-overview)
- [Create a site permission](https://learn.microsoft.com/graph/api/site-post-permissions?view=graph-rest-1.0)
- [Get a site](https://learn.microsoft.com/graph/api/site-get?view=graph-rest-1.0)
- [Download file content](https://learn.microsoft.com/graph/api/driveitem-get-content?view=graph-rest-1.0)
- [Logic Apps managed identity authentication](https://learn.microsoft.com/azure/logic-apps/authenticate-with-managed-identity)
