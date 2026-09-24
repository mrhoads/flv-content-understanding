# FLV Content Understanding Demo

A runnable example agentic workflow using Content Understanding and Document Intelligence:

- A customer-facing Microsoft Foundry hosted agent for friendly evidence requests and clarification.
- Foundry Content Understanding for vehicle and document field extraction.
- Azure AI Document Intelligence for OCR, document structure, and identity-document extraction.
- Application-layer encryption plus private local or Azure Blob storage.
- A separately configured internal Foundry agent for grounded Employee Review summaries and Q&A.

The app starts in `DEMO_MODE=true`, so the complete interaction works without an Azure deployment. Set `DEMO_MODE=false` and provide the values in `.env.example` to use Azure.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>. Employee Review is intentionally open without an
access key in both local and Azure demo deployments.

## Analyze the sample video

The standalone video example follows the Microsoft Learn Python quickstart
pattern for video analysis:
[`ContentUnderstandingClient.begin_analyze`](https://learn.microsoft.com/azure/ai-services/content-understanding/quickstart/use-rest-api?tabs=cu-studio%2Cvideo&pivots=programming-language-python)
with `AnalysisInput(url=...)`.
It creates a `ContentUnderstandingClient`, calls `begin_analyze` with an
`AnalysisInput`, prints each detected segment and summary, and writes the full JSON
and RAG-ready Markdown results to `output/video-analysis/`. By default it uses the
custom `flvCommercialVideoAnalyzer`, so `analysis.json` includes structured
commercial fields such as `Characters`, `VisibleProducts`, and `MusicAndAudio`.

Authenticate to Azure and set the Content Understanding endpoint:

```bash
az login
export CONTENT_UNDERSTANDING_ENDPOINT="https://your-resource.services.ai.azure.com"
export AZURE_STORAGE_ACCOUNT_URL="https://yourstorageaccount.blob.core.windows.net"
python examples/analyze_video.py
```

The default input is:

```text
data/Dr._Rick_Tuning_In_Progressive_Insurance_Commercial [Ufzt44z-Ng0].webm
```

Use `--video`, `--video-url`, `--storage-account-url`, `--output-dir`,
`--api-version`, or `--timeout` to override the defaults. `--video-url` follows the
quickstart's URL input shape exactly. For the default local WebM path, the example
first converts the file to an MP4 under `output/video-analysis/`, because Content
Understanding video input supports `.mp4`, `.m4v`, `.flv`, `.wmv`, `.asf`, `.avi`,
`.mkv`, and `.mov` but not `.webm`. It then uploads the MP4 to private Blob Storage,
creates a temporary user-delegation SAS, and calls `begin_analyze` with
`AnalysisInput(url=...)`. The example uses `DefaultAzureCredential` during local
development. With `--app-env production`, it uses managed identity and the optional
`AZURE_CLIENT_ID`; it never accepts or stores an API key. Video analysis uses the
quickstart's `2025-11-01` API version by default.

To deploy or refresh the custom video analyzer for commercial-specific attributes
such as characters, music/audio, visible products, on-screen text, and the ad
message, run:

```bash
export CONTENT_UNDERSTANDING_ENDPOINT="https://aif-flv-cu-dev-e9fd04.services.ai.azure.com"
export AZURE_STORAGE_ACCOUNT_URL="https://stflvdemodeve9fd.blob.core.windows.net/"

bash infra/configure-foundry-analyzers.sh

python examples/analyze_video.py
```

The analyzer definition is in `infra/analyzers/commercial-video.json`. It uses
`prebuilt-video` as its base analyzer and whole-video extraction
(`enableSegment=false`) so short commercials are analyzed as one ad unit before
adding optional scene-level segmentation. You can still run the generic prebuilt
video search analyzer with `--analyzer-id prebuilt-videoSearch` when you only need
transcript, key-frame, and summary output.

## Azure architecture

```text
Customer browser
    |
    v
FastAPI application -- customer prompt --> Foundry hosted customer agent
    |
    +-- uploaded bytes --> Content Understanding analyzer
    |                 \-> Document Intelligence
    |                       +-- general documents: prebuilt-document
    |                       \-- identity documents: prebuilt-idDocument
    |
    +-- encrypted payload and metadata --> private Azure Blob container
    |
Employee browser -- open demo review --> Foundry hosted employee agent
                                      ^
                                      |
                            compact grounded case context
```

Use two Foundry agent names even when both use the same model deployment. This keeps customer instructions and employee evidence-access policies independently deployable.

## Configure Azure mode

1. Copy `.env.example` to `.env` or inject equivalent App Service/Container Apps settings.
2. Set `DEMO_MODE=false`, `APP_ENV=production`, and `STORAGE_BACKEND=azure`.
3. Configure the Foundry project endpoint, model deployment, and two hosted agent names.
4. Configure separate Content Understanding analyzers for vehicle images and documents.
5. Configure a dedicated Document Intelligence endpoint. This deployment uses the
   `formrecognizer` API route with version `2023-07-31` for North Central US
   compatibility. The app selects `prebuilt-idDocument` for identity documents and
   `prebuilt-document` for other documents.
6. Provide `APP_ENCRYPTION_KEY` from Key Vault. Employee Review is intentionally unauthenticated because this deployment is for demonstration purposes only.
7. Grant the app's managed identity only the required project, Cognitive Services, and blob data roles.

The Azure implementation requests tokens for `https://cognitiveservices.azure.com/.default`; no service keys are stored in code.

Customer names are collected before upload. The intake agent responds with
`HI <name>, please upload a recent photo of your vehicle`. Upload responses confirm receipt
without displaying analysis output; the encrypted case record stores that analysis for
Employee Review. When an employee selects a case, the internal agent automatically
summarizes the uploaded files and extracted details before allowing follow-up questions.
The review interface requests that summary immediately on case selection.

Identity-document routing is hybrid. Clear filename hints such as `DriverLicense.png`
route directly to `prebuilt-idDocument`. For ambiguous filenames, the app first performs
general OCR and reruns the upload with `prebuilt-idDocument` when the OCR text contains
identity-document signals. Azure Document Intelligence responses are normalized from
`analyzeResult`, including structured fields, OCR text, page count, key-value pairs,
model ID, and confidence values. Vehicle Content Understanding fields are suppressed
from identity-document summaries.

Employee Review is open without an access key in both local and Azure deployments because
this application is a demonstration and is not intended for production use.

## Suggested analyzer fields

**Vehicle image analyzer:** vehicle type, year, make, model, color, VIN, plate, visible damage, related items, and per-field confidence.

**Vehicle document analyzer:** document type, issuing state, registered owner, VIN, plate, title number, year, make, model, issue/expiration dates, lienholder, title brand, and per-field confidence.

**Identity documents:** The application uses Document Intelligence
`prebuilt-idDocument`; no custom identity-document analyzer is required.

## Security boundaries

- Every file and case record is encrypted with Fernet before it reaches local disk or Blob Storage.
- Local development creates an owner-readable key under `.local-secrets/`; production refuses to start without an injected key.
- Production authentication uses `ManagedIdentityCredential`; `DefaultAzureCredential` is limited to development.
- The Azure container is never made public by the application.
- Upload MIME types and sizes are allow-listed.
- Employee APIs are intentionally unauthenticated for this demo. Add Entra ID and
  role/app-role authorization before adapting the application for production use.
- Agent prompts explicitly prohibit final coverage, fraud, and document-authenticity decisions.

## Current Azure deployment

- Container App: `ca-flv-demo-dev-e9fd`
- Region: North Central US
- Image: `crflvdemodeve9fd.azurecr.io/flv-demo:20260915.7`
- Revision: `ca-flv-demo-dev-e9fd--20260915-7`
- URL: <https://ca-flv-demo-dev-e9fd.ashysea-8bf3a2e5.northcentralus.azurecontainerapps.io>

The deployment uses managed identity for ACR, Key Vault, Blob Storage, Foundry,
Content Understanding, and Document Intelligence access. No Azure service API keys
are committed to the repository.

## Foundry agent instructions

Create two hosted agents with the following responsibilities:

**Customer agent**

> Guide an insurance customer through first-look vehicle verification in a friendly, professional tone. Ask for one clear vehicle image, registration, or title at a time. Ask at most one clarifying question per turn. Do not request unrelated sensitive data or make coverage, fraud, or authenticity decisions.

**Employee agent**

> Answer employee questions only from supplied case evidence. Clearly distinguish extracted facts from inferences, expose confidence and missing evidence, cite filenames, and never make the final coverage, fraud, or legal-authenticity decision.
