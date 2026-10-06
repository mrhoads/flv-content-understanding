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
- **`cu-results` lives in its own, dedicated storage account** (`stflvfabricdeve9fd`),
  separate from the app's production `stflvdemodeve9fd` account. ADLS Gen2
  OneLake shortcuts require **Hierarchical Namespace (HNS)** enabled on the
  storage account, and HNS is permanently incompatible with **Blob Index
  Tags**. The production account has blob index tags from Defender for
  Storage's malware-scanning feature (`Malware Scanning scan result` /
  `scan time UTC`, applied to every uploaded blob), so enabling HNS there would
  either require stripping those tags one-time and opting into the preview
  "Blob Tags for Hierarchical Namespace" feature (to keep Defender tagging
  working on every future upload), or would otherwise break Defender's malware
  scanning going forward. A new, dedicated account avoids both: it's
  HNS-enabled from creation, holds only CU result JSON (no user-uploaded
  content), and needs no change to the production account's security posture.
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
Azure Blob Storage (dedicated, HNS-enabled account "stflvfabricdeve9fd"):
  cu-results/<campaign_name>/<id>.json   (new account + container, no public access)
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

- A new, dedicated, **HNS-enabled** storage account, **`stflvfabricdeve9fd`**,
  with a **`cu-results`** Blob container (`infra/modules/storage.bicep`, wired
  from `infra/main.bicep`). `examples/analyze_video.py` uploads CU JSON output
  for campaign videos here automatically (one blob per analyzed video), key
  shape: `cu-results/<campaign_name>/<id>.json`. It's separate from the
  production `stflvdemodeve9fd` account so enabling HNS never touches that
  account's Defender for Storage malware-scanning blob tags (see above).
- RBAC so both the app's managed identity and the deployer (running the
  example locally with `az login`/`DefaultAzureCredential`) have
  `Storage Blob Data Contributor` on `stflvfabricdeve9fd` and can write result
  JSON (`infra/modules/role-assignments.bicep`).
- An optional, idempotent RBAC grant: pass `fabricWorkspaceIdentityPrincipalId`
  as a bicep parameter once you know it (see step 2 below) and redeploy, or run
  `infra/grant-fabric-workspace-access.sh <principal-id>` directly — both grant
  `Storage Blob Data Reader` on the `stflvfabricdeve9fd` storage account to the
  Fabric workspace identity, scoped to the whole account (Blob RBAC isn't
  container-scoped).

Nothing else in the app changes. `DEMO_MODE=true` continues to work with no
Azure dependency at all; the Fabric pieces are opt-in and additive.

## Writing CU results for Fabric to consume

`examples/analyze_video.py` now uploads its result JSON to `stflvfabricdeve9fd`
automatically whenever `--fabric-storage-account-url`
(or `FABRIC_STORAGE_ACCOUNT_URL`) is set, in addition to its usual local
`output/video-analysis/analysis.json`:

```bash
export CONTENT_UNDERSTANDING_ENDPOINT="https://aif-flv-cu-dev-e9fd04.cognitiveservices.azure.com/"
export AZURE_STORAGE_ACCOUNT_URL="https://stflvdemodeve9fd.blob.core.windows.net"
export FABRIC_STORAGE_ACCOUNT_URL="https://stflvfabricdeve9fd.blob.core.windows.net"
export CAMPAIGN_NAME="progressive-dr-rick"

python examples/analyze_video.py --video-url "https://<public-or-sas-url-to-a-video>"
```

This writes `cu-results/<CAMPAIGN_NAME>/<id>.json`, exactly the blob the
OneLake shortcut below exposes at `Files/cu-results/<CAMPAIGN_NAME>/<id>.json`.
`--fabric-container` overrides the container name (default `cu-results`) if
you ever rename it.

### Troubleshooting: `RuntimeError: Content Understanding returned no video segments`

This means the underlying operation actually **failed**, not that the video
format was rejected — the SDK's `poller.result()` doesn't raise on a
`Failed` operation status, so the script only sees the (empty) `contents`
list. To see the real error, poll the `operation-location` URL from the
`analyze` response directly and read its top-level `error` field.

The most common cause is a `429 RateLimit` from the `gpt-4-1-mini-cu-flv`
model deployment: video analysis issues many vision-model calls in a tight
burst (checked over 1-10 second windows), so even a short (~48s) commercial
can exceed a low deployment capacity. If you see this, increase the
deployment's capacity (`infra/modules/content-understanding.bicep`'s
`modelDeployment.sku.capacity`, currently `1000`) and redeploy, or bump it
directly for a quick retest:

```bash
az cognitiveservices account deployment create \
  --name aif-flv-cu-dev-e9fd04 -g <resource-group> \
  --deployment-name gpt-4-1-mini-cu-flv \
  --model-name gpt-4.1-mini --model-version 2025-04-14 --model-format OpenAI \
  --sku-name Standard --sku-capacity 1000
```

Check `az cognitiveservices usage list --location <region>` for the regional
`OpenAI.Standard.gpt4.1-mini` quota ceiling before raising capacity further.

### Troubleshooting: notebook errors reading shortcut files

The ingestion notebook (`fabric/notebooks/campaign_insights_ingestion.ipynb`)
reads files from the `cu-results` OneLake shortcut using plain Python `open()`
against the attached default Lakehouse's local filesystem mount, because
`notebookutils.fs` has **no `open()` method** (only `ls`, `cp`, `mv`, `rm`,
`mkdirs`, `head`, `put`, `append`, `exists`, `mount`/`unmount` — `head()` caps
reads at 100 KB, which risks truncating larger CU result JSON). If you see
`AttributeError: module 'notebookutils.fs' has no attribute 'open'`, that's the
symptom of calling `notebookutils.fs.open(...)` instead.

Separately, `notebookutils.fs.ls()` returns **absolute**
`abfss://<workspace-id>@onelake.dfs.fabric.microsoft.com/<item-id>/Files/...`
paths, not paths relative to the shortcut. Naively prefixing that with
`/lakehouse/default/` (the local mount point) produces a broken, doubled path
like `/lakehouse/default/abfss://.../Files/cu-results/...json` and fails with
`[Errno 2] No such file or directory`. The notebook's `to_local_path()` helper
(cell 6) strips everything up to and including `/Files/` and rebuilds the path
as `/lakehouse/default/Files/...` before calling `open()`. If you ever rewrite
this cell, keep that conversion — don't pass the raw `notebookutils.fs.ls()`
path straight to `open()`.

## One-time manual setup in Fabric (no Bicep/ARM support for these item types yet)

1. **Create (or reuse) a Fabric workspace** on a capacity that supports
   Lakehouses, notebooks, and workspace identity.
2. **Enable workspace identity**: Workspace settings → *Workspace identity* →
   *Create*. Copy the resulting principal/object ID. Workspace identity is
   tied to the workspace itself — if you ever delete and recreate the
   workspace, re-enabling workspace identity mints a **new** object ID, and
   any existing RBAC grant (step 3) becomes stale and must be re-run with the
   new ID.
3. **Grant storage access**: run
   `./infra/grant-fabric-workspace-access.sh <principal-id-from-step-2>`
   (or redeploy `main.bicep` with that value in `fabricWorkspaceIdentityPrincipalId`).
4. **Create a Lakehouse**, e.g. `lh_marketing_campaigns`.
5. **Add a OneLake shortcut**: in the Lakehouse's **Lake view**, expand and
   **right-click directly on the `Files` folder** (not the Lakehouse root —
   invoking *New shortcut* from the wrong level creates a top-level artifact
   sibling to `Files`/`Tables` instead of nesting under `Files`, which Fabric
   rejects at read time) → *New shortcut* → *Azure Data Lake Storage Gen2*.
   - **URL**: `https://stflvfabricdeve9fd.dfs.core.windows.net`
   - **Connection**: *Create new connection* → name it (e.g.
     `stflvfabricdeve9fd-workspace-identity`) → **Authentication kind**:
     **Workspace Identity** (no key or SAS needed because of the RBAC grant in
     step 3).
   - **Next** → browse into the storage account and **check the box** next to
     the `cu-results` container (don't type a path).
   - **Next** → on the review page, confirm the shortcut name is `cu-results`
     (edit via the pencil icon if it defaulted to something else) → **Create**.
   - Verify in the Explorer pane that the shortcut appears **nested inside
     `Files`** (with a small link icon), i.e. its path is `Files/cu-results`,
     matching the notebook's `SHORTCUT_PATH` default.
6. **Import the notebook**: Workspace → *Import* → *Notebook* →
   `fabric/notebooks/campaign_insights_ingestion.ipynb`. Attach it to the
   Lakehouse from step 4 as its default Lakehouse.
7. **Run it once** to create the `campaign_insights` Delta table, then schedule
   it (Notebook's own schedule, or a simple Fabric Data Pipeline with a single
   Notebook activity) to run after each batch of new campaign videos is
   analyzed.
   - **Iterating on the notebook without re-uploading each change**: install
     the **Fabric Data Engineering** VS Code extension, sign in, and
     **Download** the workspace notebook locally (copy this repo's
     `fabric/notebooks/campaign_insights_ingestion.ipynb` content over the
     downloaded file to keep git as the source of truth). Select the
     **Microsoft Fabric Runtime** kernel (with the Lakehouse from step 4 set
     as default) to run cells against the real remote Spark session, then use
     **Publish** in the extension to push a finished change back to the
     workspace notebook before committing the same file to git.
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
`app/storage.py` for the existing pattern) against the `cu-results` container
in the **`stflvfabricdeve9fd`** storage account (not the app's production
`stflvdemodeve9fd` account).
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

- `infra/modules/storage.bicep` — creates the dedicated, HNS-enabled
  `stflvfabricdeve9fd` storage account and its `cu-results` container
  (reused from the production storage module via an `isHnsEnabled` parameter).
- `infra/main.bicep` / `infra/modules/role-assignments.bicep` — wire up the
  Fabric storage account, its `cu-results` container, and the optional Fabric
  workspace identity RBAC grant (scoped to the Fabric account only).
- `infra/grant-fabric-workspace-access.sh` — one-shot script to grant
  `Storage Blob Data Reader` on `stflvfabricdeve9fd` once the Fabric workspace
  identity exists.
- `fabric/notebooks/campaign_insights_ingestion.ipynb` — Fabric PySpark
  notebook that flattens CU JSON from the shortcut into the `campaign_insights`
  Delta table. Schema-agnostic: new analyzer fields show up as new columns.
