# Content Understanding → Microsoft Fabric: Marketing Campaign Reporting Plan

## Goal

Get Content Understanding results for commercial/marketing video campaigns into
Microsoft Fabric so historic campaign attributes (brand, products, competitors,
sentiment, call-to-action, humor, etc.) can be reported on in Power BI, and later
joined with simulated engagement data to analyze marketing effectiveness.

This repo already has the hard part: `infra/analyzers/commercial-video.json`
defines `flvCommercialVideoAnalyzer`, a Content Understanding analyzer tuned for
marketing attributes, and `examples/analyze_video.py` shows how to call it and
get back structured JSON. This plan wires that JSON into Fabric.

## Why this differs from the public sample

The [Azure-Samples/azure-ai-content-understanding-with-fabric](https://github.com/Azure-Samples/azure-ai-content-understanding-with-fabric)
tutorial has a Fabric *notebook* call Content Understanding directly (with a
resource key) and write JSON to Blob with a SAS token, then a Fabric *pipeline*
Copy activity moves that JSON into a Lakehouse.

This repo's storage account sets `allowSharedKeyAccess: false` (no account keys,
no SAS tokens — Entra ID/managed identity only), and Content Understanding is
already invoked from Python using managed identity. So the plan adapts the
sample to this repo's no-secrets posture:

- **Analysis stays where it already happens** (the app / `examples/analyze_video.py`
  or your own batch script), using the existing managed-identity-authenticated
  `ContentUnderstandingClient`. No Fabric notebook needs Content Understanding
  credentials.
- **Landing JSON in Fabric uses a OneLake Shortcut instead of a Copy activity.**
  A shortcut makes the `cu-results` Blob container appear directly under the
  Lakehouse's `Files/` folder, authenticated via the Fabric **workspace
  identity** (a system-assigned Entra ID identity for the whole workspace) with
  a single `Storage Blob Data Reader` RBAC role grant. No key, SAS, or app
  registration secret is created anywhere.
- **A Fabric notebook still does the transform**, flattening the nested CU JSON
  (`contents[].fields`) into a queryable Delta table, same purpose as the
  sample's notebook — just not the half that calls Content Understanding.

## End-to-end architecture

```text
Historic campaign videos
    |
    v
Content Understanding analyzer (flvCommercialVideoAnalyzer)
  called via examples/analyze_video.py or your batch script,
  authenticated with managed identity / DefaultAzureCredential
    |
    v
Azure Blob Storage: cu-results/<campaign_name>/<id>.json   (new container, no public access)
    |
    | OneLake Shortcut (Fabric workspace identity, Storage Blob Data Reader -- no secrets)
    v
Fabric Lakehouse  "Files/cu-results"  (read-only view of the same blobs, no copy)
    |
    | fabric/notebooks/campaign_insights_ingestion.ipynb  (flattens JSON -> Delta)
    v
Delta table: campaign_insights   (one row per video/segment, one column per CU field)
    |
    v
Power BI report / Fabric semantic model: historic marketing campaign results
    |
    (future) join with a simulated impressions/clicks/conversions table
    v
Marketing effectiveness analysis
```

## What's already deployed by this change

Run `infra/main.bicep` (same process as today — see `infra/DEPLOYMENT_GUIDE.md`)
to provision:

- A new Blob container, **`cu-results`**, in the existing storage account
  (`infra/modules/blob-container.bicep`, wired from `infra/main.bicep`). This is
  where CU JSON output for campaign videos should be written, one blob per
  analyzed video, suggested key shape:
  `cu-results/<campaign_name>/<video-id>.json`.
- An optional, idempotent RBAC grant: pass `fabricWorkspaceIdentityPrincipalId`
  as a bicep parameter once you know it (see step 2 below) and redeploy, or run
  `infra/grant-fabric-workspace-access.sh <principal-id>` directly — both grant
  `Storage Blob Data Reader` on the storage account to the Fabric workspace
  identity, scoped to the whole account (Blob RBAC isn't container-scoped).

Nothing else in the app changes. `DEMO_MODE=true` continues to work with no
Azure dependency at all; the Fabric pieces are opt-in and additive.

## One-time manual setup in Fabric (no Bicep/ARM support for these item types yet)

1. **Create (or reuse) a Fabric workspace** on a capacity that supports
   Lakehouses, notebooks, and workspace identity.
2. **Enable workspace identity**: Workspace settings → *Workspace identity* →
   *Create*. Copy the resulting principal/object ID.
3. **Grant storage access**: run
   `./infra/grant-fabric-workspace-access.sh <principal-id-from-step-2>`
   (or redeploy `main.bicep` with that value in `fabricWorkspaceIdentityPrincipalId`).
4. **Create a Lakehouse**, e.g. `lh_marketing_campaigns`.
5. **Add a OneLake shortcut**: in the Lakehouse's `Files` pane → *New shortcut* →
   *Azure Data Lake Storage Gen2* → point at the storage account's `cu-results`
   container → authentication method **Organizational account / Workspace
   identity** (no key or SAS needed because of the RBAC grant in step 3).
   Name it so its path is `Files/cu-results` to match the notebook default.
6. **Import the notebook**: Workspace → *Import* → *Notebook* →
   `fabric/notebooks/campaign_insights_ingestion.ipynb`. Attach it to the
   Lakehouse from step 4 as its default Lakehouse.
7. **Run it once** to create the `campaign_insights` Delta table, then schedule
   it (Notebook's own schedule, or a simple Fabric Data Pipeline with a single
   Notebook activity) to run after each batch of new campaign videos is
   analyzed.
8. **Build the report**: create a Power BI report or Fabric semantic model on
   `campaign_insights` (e.g., mention counts by `AdvertiserBrand`/
   `CompetitorsMentioned`, `EmotionSentiment` distribution, `CallToAction`
   presence rate, grouped by `campaign_name`).

## Writing results so the pipeline picks them up

Whatever analyzes the historic videos (a batch script using the same pattern as
`examples/analyze_video.py`) should write each analyzer result JSON to:

```text
cu-results/<campaign_name>/<video-id>.json
```

using `AzureBlobObjectStorage`-style managed-identity upload (see
`app/storage.py` for the existing pattern) against the `cu-results` container.
`campaign_name` becomes a column in `campaign_insights` automatically (the
notebook derives it from the blob path), so group videos into a folder per
campaign for reporting.

## Later: simulated data for marketing effectiveness

Once historic reporting works end to end, add a second Fabric notebook that
generates a synthetic `campaign_engagement_simulated` table — impressions,
clicks, and conversions per `file_path`/`campaign_name` — with values
correlated to real CU attributes already in `campaign_insights` (e.g., a
simulated conversion-rate lift when `CallToAction` is present, or when
`EmotionSentiment` is positive). Join the two tables in the semantic model so
reports can show "campaigns with a clear CTA simulate N% higher conversion,"
clearly labeled as simulated/demo data, not real measured performance. This is
intentionally deferred — flag when you want it built and we'll add the
generator notebook plus the join logic.

## Files added by this change

- `infra/modules/blob-container.bicep` — creates an additional container on the
  existing storage account.
- `infra/main.bicep` / `infra/modules/role-assignments.bicep` — wire up the
  `cu-results` container and the optional Fabric workspace identity RBAC grant.
- `infra/grant-fabric-workspace-access.sh` — one-shot script to grant
  `Storage Blob Data Reader` once the Fabric workspace identity exists.
- `fabric/notebooks/campaign_insights_ingestion.ipynb` — Fabric PySpark
  notebook that flattens CU JSON from the shortcut into the `campaign_insights`
  Delta table. Schema-agnostic: new analyzer fields show up as new columns.
