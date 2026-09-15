from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.azure_clients import (
    AzureAnalysisClient,
    FoundryAgentClient,
    MockAgentClient,
    MockAnalysisClient,
    build_credential,
    compact_case_context,
)
from app.config import Settings, load_settings
from app.repository import CaseRepository
from app.storage import build_store


ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/tiff",
    "application/pdf",
}


class CreateCaseRequest(BaseModel):
    customer_name: str = Field(min_length=1, max_length=100)


class MessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class EmployeeQuestion(BaseModel):
    case_id: str = Field(min_length=1, max_length=64)
    question: str = Field(min_length=1, max_length=2000)


def build_dependencies(settings: Settings) -> dict[str, object]:
    credential = build_credential(settings)
    repository = CaseRepository(build_store(settings, credential))
    if settings.demo_mode:
        return {
            "settings": settings,
            "repository": repository,
            "agents": MockAgentClient(),
            "analysis": MockAnalysisClient(),
        }

    missing = [
        name
        for name, value in {
            "FOUNDRY_PROJECT_ENDPOINT": settings.foundry_project_endpoint,
            "FOUNDRY_MODEL_DEPLOYMENT": settings.foundry_model_deployment,
            "FOUNDRY_CUSTOMER_AGENT_NAME": settings.customer_agent_name,
            "FOUNDRY_EMPLOYEE_AGENT_NAME": settings.employee_agent_name,
            "CONTENT_UNDERSTANDING_ENDPOINT": settings.content_understanding_endpoint,
            "CONTENT_UNDERSTANDING_IMAGE_ANALYZER_ID": settings.content_understanding_image_analyzer_id,
            "CONTENT_UNDERSTANDING_DOCUMENT_ANALYZER_ID": settings.content_understanding_document_analyzer_id,
            "DOCUMENT_INTELLIGENCE_ENDPOINT": settings.document_intelligence_endpoint,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing Azure configuration: {', '.join(missing)}")

    return {
        "settings": settings,
        "repository": repository,
        "agents": FoundryAgentClient(settings, credential),
        "analysis": AzureAnalysisClient(settings, credential),
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.services = build_dependencies(load_settings())
    yield


app = FastAPI(title="Progressive FLV Demo", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


def services() -> dict[str, object]:
    return app.state.services


def employee_access(
    x_employee_key: Annotated[str | None, Header()] = None,
    svc: dict[str, object] = Depends(services),
) -> None:
    settings: Settings = svc["settings"]
    if x_employee_key != settings.internal_access_key:
        raise HTTPException(
            status_code=401,
            detail="The employee access key is missing or invalid.",
        )


@app.get("/")
async def home() -> FileResponse:
    return FileResponse(Path("app/static/index.html"))


@app.get("/health")
async def health(svc: dict[str, object] = Depends(services)) -> dict[str, object]:
    settings: Settings = svc["settings"]
    return {
        "status": "ok",
        "mode": "demo" if settings.demo_mode else "azure",
        "storage": settings.storage_backend,
    }


@app.post("/api/cases")
async def create_case(
    request: CreateCaseRequest,
    svc: dict[str, object] = Depends(services),
) -> dict[str, object]:
    repository: CaseRepository = svc["repository"]
    customer_name = request.customer_name.strip()
    if not customer_name:
        raise HTTPException(status_code=422, detail="Your name is required.")
    case = repository.create(customer_name)
    text = f"HI {customer_name}, please upload a recent photo of your vehicle"
    repository.add_message(case, "assistant", text)
    return {"case": case, "message": text}


@app.post("/api/cases/{case_id}/uploads")
async def upload_content(
    case_id: str,
    file: Annotated[UploadFile, File()],
    svc: dict[str, object] = Depends(services),
) -> dict[str, object]:
    settings: Settings = svc["settings"]
    repository: CaseRepository = svc["repository"]
    try:
        case = repository.get(case_id)
    except (FileNotFoundError, KeyError):
        raise HTTPException(status_code=404, detail="Case not found")

    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported file type")
    payload = await file.read(settings.max_upload_bytes + 1)
    if not payload:
        raise HTTPException(status_code=400, detail="The uploaded file is empty")
    if len(payload) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="The uploaded file is too large")

    upload_id = uuid4().hex
    blob_key = f"cases/{case_id}/uploads/{upload_id}.bin.enc"
    analysis = await svc["analysis"].analyze(payload, content_type, file.filename or "upload")
    repository.store.put_bytes(blob_key, payload, "application/octet-stream")
    upload = {
        "id": upload_id,
        "filename": Path(file.filename or "upload").name,
        "contentType": content_type,
        "size": len(payload),
        "blobKey": blob_key,
        "analysis": analysis,
    }
    case["uploads"].append(upload)
    case["status"] = "employee-review"
    repository.save(case)

    text = "Thanks — your photo was received and is ready for employee review."
    repository.add_message(case, "assistant", text)
    return {
        "upload": {
            "id": upload["id"],
            "filename": upload["filename"],
            "contentType": upload["contentType"],
            "size": upload["size"],
        },
        "message": text,
        "case": {
            "id": case["id"],
            "customerName": case["customerName"],
            "status": case["status"],
            "createdAt": case["createdAt"],
            "updatedAt": case["updatedAt"],
        },
    }


@app.post("/api/cases/{case_id}/messages")
async def customer_message(
    case_id: str,
    request: MessageRequest,
    svc: dict[str, object] = Depends(services),
) -> dict[str, str]:
    repository: CaseRepository = svc["repository"]
    try:
        case = repository.get(case_id)
    except (FileNotFoundError, KeyError):
        raise HTTPException(status_code=404, detail="Case not found")
    repository.add_message(case, "user", request.message)
    prompt = (
        "You are the customer-facing FLV intake agent. Respond professionally to the "
        "customer's message, using the case context. Ask only for information needed to "
        "complete first-look verification. Do not make a claim decision.\n"
        f"Customer message: {request.message}\nCase context: {compact_case_context(case)}"
    )
    settings: Settings = svc["settings"]
    text = await svc["agents"].ask(
        settings.customer_agent_name or "customer-intake", prompt
    )
    repository.add_message(case, "assistant", text)
    return {"message": text}


@app.get("/api/employee/cases", dependencies=[Depends(employee_access)])
async def employee_cases(
    svc: dict[str, object] = Depends(services),
) -> dict[str, object]:
    repository: CaseRepository = svc["repository"]
    cases = repository.list()
    return {
        "cases": [
            {
                "id": case["id"],
                "customerName": case["customerName"],
                "status": case["status"],
                "updatedAt": case["updatedAt"],
                "uploadCount": len(case["uploads"]),
            }
            for case in cases
        ]
    }


@app.post("/api/employee/query", dependencies=[Depends(employee_access)])
async def employee_query(
    request: EmployeeQuestion,
    svc: dict[str, object] = Depends(services),
) -> dict[str, str]:
    repository: CaseRepository = svc["repository"]
    try:
        case = repository.get(request.case_id)
    except (FileNotFoundError, KeyError):
        raise HTTPException(status_code=404, detail="Case not found")
    settings: Settings = svc["settings"]
    prompt = (
        "You are the internal FLV evidence assistant for insurance employees. Answer the "
        "question only from the supplied case context. Distinguish extracted facts from "
        "inferences, mention confidence or missing evidence, and never make the final "
        "coverage, fraud, or legal-authenticity decision. Refer to filenames when useful.\n"
        f"Employee question: {request.question}\nCase context: {compact_case_context(case)}"
    )
    text = await svc["agents"].ask(
        settings.employee_agent_name or "employee-evidence", prompt
    )
    return {"answer": text}
