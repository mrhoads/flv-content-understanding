from __future__ import annotations

import binascii
import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.fernet import Fernet
from dotenv import load_dotenv


load_dotenv()


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_env: str
    demo_mode: bool
    internal_access_key: str
    max_upload_bytes: int
    encryption_key: bytes
    storage_backend: str
    local_data_dir: Path
    storage_account_url: str | None
    storage_container: str
    foundry_project_endpoint: str | None
    foundry_model_deployment: str | None
    customer_agent_name: str | None
    employee_agent_name: str | None
    content_understanding_endpoint: str | None
    content_understanding_image_analyzer_id: str | None
    content_understanding_document_analyzer_id: str | None
    content_understanding_api_version: str
    document_intelligence_endpoint: str | None
    document_intelligence_api_version: str


def _load_encryption_key(app_env: str) -> bytes:
    configured = os.getenv("APP_ENCRYPTION_KEY", "").strip()
    if configured:
        try:
            Fernet(configured.encode())
        except (ValueError, binascii.Error) as exc:
            raise RuntimeError("APP_ENCRYPTION_KEY must be a valid Fernet key") from exc
        return configured.encode()

    if app_env != "development":
        raise RuntimeError("APP_ENCRYPTION_KEY is required outside development")

    key_path = Path(".local-secrets/storage.key")
    key_path.parent.mkdir(parents=True, exist_ok=True)
    if not key_path.exists():
        key_path.write_bytes(Fernet.generate_key())
        key_path.chmod(0o600)
    return key_path.read_bytes().strip()


def load_settings() -> Settings:
    app_env = os.getenv("APP_ENV", "development")
    demo_mode = _as_bool(os.getenv("DEMO_MODE"), default=True)
    internal_key = os.getenv("INTERNAL_ACCESS_KEY", "").strip()
    if not internal_key:
        if app_env != "development":
            raise RuntimeError("INTERNAL_ACCESS_KEY is required outside development")
        internal_key = "change-this-for-a-shared-demo"

    return Settings(
        app_env=app_env,
        demo_mode=demo_mode,
        internal_access_key=internal_key,
        max_upload_bytes=int(os.getenv("MAX_UPLOAD_MB", "15")) * 1024 * 1024,
        encryption_key=_load_encryption_key(app_env),
        storage_backend=os.getenv("STORAGE_BACKEND", "local").lower(),
        local_data_dir=Path(os.getenv("LOCAL_DATA_DIR", ".demo-data")),
        storage_account_url=os.getenv("AZURE_STORAGE_ACCOUNT_URL"),
        storage_container=os.getenv("AZURE_STORAGE_CONTAINER", "flv-content"),
        foundry_project_endpoint=os.getenv("FOUNDRY_PROJECT_ENDPOINT"),
        foundry_model_deployment=os.getenv("FOUNDRY_MODEL_DEPLOYMENT"),
        customer_agent_name=os.getenv("FOUNDRY_CUSTOMER_AGENT_NAME"),
        employee_agent_name=os.getenv("FOUNDRY_EMPLOYEE_AGENT_NAME"),
        content_understanding_endpoint=os.getenv("CONTENT_UNDERSTANDING_ENDPOINT"),
        content_understanding_image_analyzer_id=os.getenv(
            "CONTENT_UNDERSTANDING_IMAGE_ANALYZER_ID"
        ),
        content_understanding_document_analyzer_id=os.getenv(
            "CONTENT_UNDERSTANDING_DOCUMENT_ANALYZER_ID"
        ),
        content_understanding_api_version=os.getenv(
            "CONTENT_UNDERSTANDING_API_VERSION", "2025-05-01-preview"
        ),
        document_intelligence_endpoint=os.getenv("DOCUMENT_INTELLIGENCE_ENDPOINT"),
        document_intelligence_api_version=os.getenv(
            "DOCUMENT_INTELLIGENCE_API_VERSION", "2023-07-31"
        ),
    )
