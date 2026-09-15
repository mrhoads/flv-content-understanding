# Progressive First-Look Verification demo

A runnable insurance intake demo that combines:

- A customer-facing Microsoft Foundry hosted agent for friendly evidence requests and clarification.
- Foundry Content Understanding for vehicle and document field extraction.
- Azure AI Document Intelligence for OCR and document structure.
- Client-side encryption plus private local or Azure Blob storage.
- A separately configured internal Foundry agent for grounded employee Q&A.

The app starts in `DEMO_MODE=true`, so the complete interaction works without an Azure deployment. Set `DEMO_MODE=false` and provide the values in `.env.example` to use Azure.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>. The employee demo key is `change-this-for-a-shared-demo`; replace it through `INTERNAL_ACCESS_KEY` before sharing the app.

## Azure architecture

```text
Customer browser
    |
    v
FastAPI application -- customer prompt --> Foundry hosted customer agent
    |
    +-- uploaded bytes --> Content Understanding analyzer
    |                 \-> Document Intelligence prebuilt-document
    |
    +-- encrypted payload and metadata --> private Azure Blob container
    |
Employee browser -- authenticated query --> Foundry hosted employee agent
                                            ^
                                            |
                                  compact grounded case context
```

Use two Foundry agent names even when both use the same model deployment. This keeps customer instructions and employee evidence-access policies independently deployable.

## Configure Azure mode

1. Copy `.env.example` to `.env` or inject equivalent App Service/Container Apps settings.
2. Set `DEMO_MODE=false`, `APP_ENV=production`, and `STORAGE_BACKEND=azure`.
3. Configure the Foundry project endpoint, model deployment, and two hosted agent names.
4. Configure separate Content Understanding analyzers for vehicle images and vehicle documents.
5. Configure a dedicated Document Intelligence endpoint. This deployment uses the `formrecognizer` API route with version `2023-07-31` for North Central US compatibility.
6. Provide `APP_ENCRYPTION_KEY` from Key Vault and a strong `INTERNAL_ACCESS_KEY`, or replace the demo header check with Microsoft Entra authentication.
7. Grant the app's managed identity only the required project, Cognitive Services, and blob data roles.

The Azure implementation requests tokens for `https://cognitiveservices.azure.com/.default`; no service keys are stored in code.

Customer names are collected before upload. The intake response confirms receipt without
displaying Content Understanding output; the encrypted case record stores the analysis for
authorized Employee Review users.

## Suggested analyzer fields

**Vehicle image analyzer:** vehicle type, year, make, model, color, VIN, plate, visible damage, related items, and per-field confidence.

**Vehicle document analyzer:** document type, issuing state, registered owner, VIN, plate, title number, year, make, model, issue/expiration dates, lienholder, title brand, and per-field confidence.

## Security boundaries

- Every file and case record is encrypted with Fernet before it reaches local disk or Blob Storage.
- Local development creates an owner-readable key under `.local-secrets/`; production refuses to start without an injected key.
- Production authentication uses `ManagedIdentityCredential`; `DefaultAzureCredential` is limited to development.
- The Azure container is never made public by the application.
- Upload MIME types and sizes are allow-listed.
- Employee APIs require separate authentication. The included header key is only a demo boundary; use Entra ID and role/app-role checks for production.
- Agent prompts explicitly prohibit final coverage, fraud, and document-authenticity decisions.

## Foundry agent instructions

Create two hosted agents with the following responsibilities:

**Customer agent**

> Guide an insurance customer through first-look vehicle verification in a friendly, professional tone. Ask for one clear vehicle image, registration, or title at a time. Ask at most one clarifying question per turn. Do not request unrelated sensitive data or make coverage, fraud, or authenticity decisions.

**Employee agent**

> Answer employee questions only from supplied case evidence. Clearly distinguish extracted facts from inferences, expose confidence and missing evidence, cite filenames, and never make the final coverage, fraud, or legal-authenticity decision.
