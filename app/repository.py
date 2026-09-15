from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.storage import EncryptedStore


class CaseRepository:
    def __init__(self, store: EncryptedStore):
        self.store = store

    @staticmethod
    def _case_key(case_id: str) -> str:
        return f"cases/{case_id}/case.json.enc"

    def create(self, customer_name: str | None) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        case = {
            "id": uuid4().hex,
            "customerName": customer_name or "Customer",
            "status": "awaiting-upload",
            "createdAt": now,
            "updatedAt": now,
            "messages": [],
            "uploads": [],
        }
        self.save(case)
        return case

    def save(self, case: dict[str, Any]) -> None:
        case["updatedAt"] = datetime.now(timezone.utc).isoformat()
        self.store.put_json(self._case_key(case["id"]), case)

    def get(self, case_id: str) -> dict[str, Any]:
        return self.store.get_json(self._case_key(case_id))

    def list(self) -> list[dict[str, Any]]:
        cases = []
        for key in self.store.list_keys("cases"):
            if key.endswith("/case.json.enc"):
                cases.append(self.store.get_json(key))
        return sorted(cases, key=lambda item: item["updatedAt"], reverse=True)

    def add_message(
        self, case: dict[str, Any], role: str, text: str
    ) -> dict[str, Any]:
        message = {
            "id": uuid4().hex,
            "role": role,
            "text": text,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        case["messages"].append(message)
        self.save(case)
        return message

