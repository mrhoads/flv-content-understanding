# Content Understanding → Microsoft Fabric: Marketing Campaign Reporting Plan

## Goal

Get Content Understanding results for commercial/marketing video campaigns into
Microsoft Fabric so historic campaign attributes (brand, products, competitors,
sentiment, call-to-action, humor, etc.) can be reported on in Power BI, joined
with simulated engagement/sales data to analyze marketing effectiveness.

This repo already has the hard part: `infra/analyzers/commercial-video.json`
defines `flvCommercialVideoAnalyzer`, a Content Understanding analyzer tuned for
marketing attributes, and `examples/analyze_video.py` shows how to call it and
get back structured JSON. This plan wires that JSON into Fabric.

For a high-level diagram of how Content Understanding analyzers/field schemas
work in general, see
[`../docs/content-understanding-architecture.md`](../docs/content-understanding-architecture.md).

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
- **`cu-results` lives in a single, HNS-enabled storage account**
  (`stflvfabricdeve9fd`), which also holds the app's `flv-content` container.
  ADLS Gen2 OneLake shortcuts require **Hierarchical Namespace (HNS)** enabled
  on the storage account, and HNS is permanently incompatible with **Blob
  Index Tags**. Defender for Storage's on-upload malware-scanning feature
  tags blobs with `Malware Scanning scan result` / `scan time UTC` index tags
  on non-HNS accounts; those tags simply do not appear on blobs in this
  HNS-enabled account. That's an accepted trade-off in exchange for one
  storage account instead of two: there is no app-level malware-scan
  signal on this account, so don't rely on blob index tags for case-evidence
  review here.
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
Azure Blob Storage (single, HNS-enabled account "stflvfabricdeve9fd"):
  cu-results/<campaign_name>/<id>.json   (same account as flv-content, no public access)
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
    join with the simulated impressions/clicks/conversions table
    v
Marketing effectiveness analysis (simulated)
```

## What's already deployed by this change

Run `infra/main.bicep` (same process as today — see `infra/DEPLOYMENT_GUIDE.md`)
to provision:

- A single, **HNS-enabled** storage account, **`stflvfabricdeve9fd`**, with
  both a **`flv-content`** container (app data) and a **`cu-results`** Blob
  container (`infra/modules/storage.bicep`, wired from `infra/main.bicep`).
  `examples/analyze_video.py` uploads CU JSON output for campaign videos to
  `cu-results` automatically (one blob per analyzed video), key shape:
  `cu-results/<campaign_name>/<id>.json`. Because this account is
  HNS-enabled, Defender for Storage's malware-scan blob index tags do not
  apply here (see above).
- RBAC so both the app's managed identity and the deployer (running the
  example locally with `az login`/`DefaultAzureCredential`) have
  `Storage Blob Data Contributor` on `stflvfabricdeve9fd` and can write to
  both containers (`infra/modules/role-assignments.bicep`).
- An optional, idempotent RBAC grant: pass `fabricWorkspaceIdentityPrincipalId`
  as a bicep parameter once you know it (see step 2 below) and redeploy, or run
  `infra/grant-fabric-workspace-access.sh <principal-id>` directly — both grant
  `Storage Blob Data Reader` on the `stflvfabricdeve9fd` storage account to the
  Fabric workspace identity, scoped to the whole account (Blob RBAC isn't
  container-scoped).

Nothing else in the app changes. `DEMO_MODE=true` continues to work with no
Azure dependency at all; the Fabric pieces are opt-in and additive.

## Writing CU results for Fabric to consume

`examples/analyze_video.py` uploads its result JSON to the `cu-results`
container on the same `AZURE_STORAGE_ACCOUNT_URL` automatically whenever
`--fabric-container` is non-empty (default: `cu-results`), in addition to its
usual local `output/video-analysis/analysis.json`:

```bash
export CONTENT_UNDERSTANDING_ENDPOINT="https://aif-flv-cu-dev-e9fd04.cognitiveservices.azure.com/"
export AZURE_STORAGE_ACCOUNT_URL="https://stflvfabricdeve9fd.blob.core.windows.net"
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

## Demo with synthetic Progressive commercials (no video analysis needed)

To demo Fabric reporting without an Azure deployment or real commercial
footage, `fabric/sample-data/` has pre-generated, committed Content
Understanding-shaped JSON for recognizable, long-running Progressive campaigns
(Flo and the Progressive Store, Dr. Rick's "Parentamorphosis", The Motaur,
Jamie, and the Baker Mayfield jingle spots). Each file matches the exact
envelope `flvCommercialVideoAnalyzer` returns (`result.contents[].fields`,
`type` + `value*` + `confidence` per field), one file per
`cu-results/<campaign_name>/<id>.json`, across 6 campaigns / 26 distinct
commercial variants (each campaign has several genuinely different ads —
different settings, key actions, messaging, and humor — not just the same
spot re-aired) — enough variety for brand/competitor mention counts,
sentiment distribution, and CTA presence rate by campaign in Power BI.

Regenerate (or extend with new campaigns) via
`fabric/sample-data/generate_synthetic_commercials.py`; see its module
docstring. Re-running with the default `--seed 42` reproduces the same files
(stable IDs, re-randomized confidence scores and `createdAt` dates). Use
`--extra N` to additionally generate `N` "flight re-airing" samples drawn at
random from the existing campaign/variant pool (new IDs, timestamps, and
confidence scores), useful for padding out volume for a Power BI demo without
inventing new ad concepts; `--extra-seed` controls that randomization
independently (defaults to `--seed + 1`).

To use these for the OneLake shortcut described below, upload them into the
`cu-results` container of the dedicated `stflvfabricdeve9fd`-style storage
account, authenticated the same managed-identity way as the rest of this repo
(no keys or SAS tokens):

```bash
az login
python fabric/sample-data/generate_synthetic_commercials.py --upload \
  --fabric-storage-account-url https://stflvfabricdeve9fd.blob.core.windows.net
```

`--upload` reuses `examples/analyze_video.py`'s `build_credential`/
`upload_fabric_result` helpers, so it authenticates with `DefaultAzureCredential`
in development (`--app-env production` switches to managed identity, matching
`analyze_video.py`) and writes to the same
`cu-results/<campaign_name>/<id>.json` blob layout real analyzer output uses.
`FABRIC_STORAGE_ACCOUNT_URL` and `FABRIC_RESULTS_CONTAINER` work as environment
variable equivalents of `--fabric-storage-account-url`/`--fabric-container`.
Then run the ingestion notebook as usual. No Content Understanding call, video
file, or `examples/analyze_video.py` run is required for this path — it's
synthetic data standing in for historic campaign results, clearly for demo
purposes.

## Comparing analyzer schema versions (v1 vs v2)

`infra/analyzers/commercial-video.json` (`flvCommercialVideoAnalyzer`, v1,
live) and `infra/analyzers/commercial-video-v2.json`
(`cuCommercialVideoAnalyzerV2`, v2, new-convention naming) define two
different field schemas for the *same kind* of commercial video. The v2
schema is a deliberate evolution, meant to demo how changing a Content
Understanding field schema changes what you get back for identical footage:

| v1 field (`generate`, free text)            | v2 field(s) (`classify`/new)                                   | Why change it |
| -------------------------------------------- | ---------------------------------------------------------------- | ------------- |
| `CallToAction` (string)                      | `HasCallToAction` (Yes/No) + `CallToActionType` (enum)           | Presence/category becomes directly chartable — no string parsing to find "no clear CTA" rows. |
| `EmotionSentiment` (string)                   | `SentimentCategory` (enum) + `SentimentNarrative` (string, renamed) | Sentiment distribution becomes a `GROUP BY`-able column while keeping the narrative detail. |
| `BrandSafetyNotes` (string)                  | `BrandSafetyFlag` (Clear/ReviewRecommended) + `BrandSafetyNotes` (string) | A reviewer can filter to flagged rows instead of reading every note. |
| *(none)*                                      | `BrandMentionCount` (integer)  | New quantitative field for trend lines that v1's all-text/array schema couldn't produce. |
| *(none, covered by free-text `Characters`)*  | `KnownCharacters` (multi-select enum: Flo, Jamie, Mara, Alan, Dr. Rick) | Flags which recurring campaign characters appear, for reliable filtering/aggregation by character, while `Characters` keeps capturing the full cast (including any character outside that roster) as free text. |

All other fields (brand, products, competitors, setting, etc.) are unchanged,
so most of the schema is stable and only the fields that benefit from
structure actually changed — a realistic schema-versioning story, not a full
rewrite.

`fabric/sample-data/generate_synthetic_commercials_v2.py` renders the exact
same synthetic campaigns/variants as
`generate_synthetic_commercials.py` through the v2 schema instead, reusing
the same stable `id` per video, so v1 and v2 rows for the same commercial
can be joined and compared side by side:

```bash
python fabric/sample-data/generate_synthetic_commercials_v2.py
```

Writes `fabric/sample-data/cu-results-v2/<campaign_name>/<id>.json`. Ingest it
the same way as `cu-results` — add a second OneLake shortcut
(e.g. `Files/cu-results-v2`) and either reuse
`campaign_insights_ingestion.ipynb` with `SHORTCUT_PATH`/`DELTA_TABLE_NAME`
pointed at the v2 path/table name, or duplicate the notebook. Deploying the
v2 analyzer itself (so it can analyze real video, not just synthetic JSON) is
wired into `infra/configure-foundry-analyzers.sh` alongside the three
existing analyzers.

## Simulated data for marketing effectiveness

`fabric/sample-data/generate_synthetic_sales.py` generates a
**fully synthetic** `campaign_sales_simulated` table — impressions, clicks,
conversions, and revenue, one row per commercial sample, correlated with real
Content Understanding attributes for that same video (the v2 schema's
classified `SentimentCategory` and `CallToActionType`, plus whether the video
references sports/entertainment). No real Progressive sales, spend, or
performance numbers are used; every row is marked `is_simulated = true` and
every column is clearly documented as invented for the demo in the script's
module docstring.

```bash
python fabric/sample-data/generate_synthetic_sales.py
```

Writes `fabric/sample-data/campaign-sales/campaign_sales_simulated.csv`. Copy
it into a `Files/campaign-sales` shortcut/folder the same way as the
`cu-results` JSON, then run
`fabric/notebooks/campaign_sales_ingestion.ipynb`, which:

1. Loads the CSV into a `campaign_sales_simulated` Delta table.
2. Joins it to `campaign_insights` on `campaign_name` + the result `id`
   parsed out of `file_path`, producing a `campaign_performance_simulated`
   table.
3. Prints a quick sanity-check aggregate (click-through rate by sentiment
   category, conversion rate by call-to-action type) so you can confirm the
   simulated correlation looks like the documented pattern before building a
   Power BI report on top of it.

Build a Power BI report/semantic model on `campaign_performance_simulated` —
revenue and conversion rate by `campaign_name`, `sentiment_category`, and
`call_to_action_type` — clearly labeled throughout as simulated/demo data,
not real measured marketing performance.

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
in the **`stflvfabricdeve9fd`** storage account (the same single, HNS-enabled
account that also holds the app's `flv-content` container).
`campaign_name` becomes a column in `campaign_insights` automatically (the
notebook derives it from the blob path), so group videos into a folder per
campaign for reporting.

## Files added by this change

- `infra/modules/storage.bicep` — single module that creates the one
  HNS-enabled `stflvfabricdeve9fd` storage account with its `flv-content` and
  `cu-results` containers.
- `infra/main.bicep` / `infra/modules/role-assignments.bicep` — wire up the
  single storage account, its two containers, and the optional Fabric
  workspace identity RBAC grant (`Storage Blob Data Reader`, scoped to the
  whole account since Blob RBAC isn't container-scoped).
- `infra/grant-fabric-workspace-access.sh` — one-shot script to grant
  `Storage Blob Data Reader` on `stflvfabricdeve9fd` once the Fabric workspace
  identity exists.
- `infra/analyzers/commercial-video-v2.json` — the `cuCommercialVideoAnalyzerV2`
  schema, a deliberately evolved v2 of `commercial-video.json` for the
  schema-comparison demo (see "Comparing analyzer schema versions" above).
- `fabric/notebooks/campaign_insights_ingestion.ipynb` — Fabric PySpark
  notebook that flattens CU JSON from the shortcut into the `campaign_insights`
  Delta table. Schema-agnostic: new analyzer fields show up as new columns.
- `fabric/notebooks/campaign_sales_ingestion.ipynb` — Fabric PySpark notebook
  that loads the simulated sales CSV and joins it with `campaign_insights`.
- `fabric/sample-data/` — synthetic, committed Content Understanding result
  JSON for recognizable Progressive commercial campaigns (`cu-results/` for
  v1, `cu-results-v2/` for the v2 schema), a simulated sales CSV
  (`campaign-sales/`), and the generator scripts that produce all three, for
  demoing the reporting pipeline without Azure.
