from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet

from app.config import Settings


class ObjectStorage(ABC):
    @abstractmethod
    def put(self, key: str, payload: bytes, content_type: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def get(self, key: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def list_keys(self, prefix: str) -> list[str]:
        raise NotImplementedError


class LocalObjectStorage(ObjectStorage):
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.root.chmod(0o700)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("Invalid storage key")
        return path

    def put(self, key: str, payload: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        path.chmod(0o600)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def list_keys(self, prefix: str) -> list[str]:
        base = self._path(prefix)
        if not base.exists():
            return []
        return [
            str(path.relative_to(self.root))
            for path in base.rglob("*")
            if path.is_file()
        ]


class AzureBlobObjectStorage(ObjectStorage):
    def __init__(self, account_url: str, container: str, credential: object):
        from azure.core.exceptions import ResourceExistsError
        from azure.storage.blob import BlobServiceClient

        service = BlobServiceClient(account_url=account_url, credential=credential)
        self.container = service.get_container_client(container)
        try:
            self.container.create_container()
        except ResourceExistsError:
            pass

    def put(self, key: str, payload: bytes, content_type: str) -> None:
        from azure.storage.blob import ContentSettings

        self.container.upload_blob(
            name=key,
            data=payload,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
        )

    def get(self, key: str) -> bytes:
        return self.container.download_blob(key).readall()

    def list_keys(self, prefix: str) -> list[str]:
        return [blob.name for blob in self.container.list_blobs(name_starts_with=prefix)]


class EncryptedStore:
    def __init__(self, storage: ObjectStorage, key: bytes):
        self.storage = storage
        self.cipher = Fernet(key)

    def put_bytes(self, key: str, payload: bytes, content_type: str) -> None:
        self.storage.put(key, self.cipher.encrypt(payload), content_type)

    def get_bytes(self, key: str) -> bytes:
        return self.cipher.decrypt(self.storage.get(key))

    def put_json(self, key: str, value: dict[str, Any]) -> None:
        self.put_bytes(
            key,
            json.dumps(value, separators=(",", ":"), ensure_ascii=True).encode(),
            "application/octet-stream",
        )

    def get_json(self, key: str) -> dict[str, Any]:
        return json.loads(self.get_bytes(key))

    def list_keys(self, prefix: str) -> list[str]:
        return self.storage.list_keys(prefix)


def build_store(settings: Settings, credential: object) -> EncryptedStore:
    if settings.storage_backend == "azure":
        if not settings.storage_account_url:
            raise RuntimeError("AZURE_STORAGE_ACCOUNT_URL is required for Azure storage")
        storage: ObjectStorage = AzureBlobObjectStorage(
            settings.storage_account_url,
            settings.storage_container,
            credential,
        )
    elif settings.storage_backend == "local":
        storage = LocalObjectStorage(settings.local_data_dir)
    else:
        raise RuntimeError("STORAGE_BACKEND must be 'local' or 'azure'")
    return EncryptedStore(storage, settings.encryption_key)
