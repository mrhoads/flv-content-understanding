import asyncio
from pathlib import Path

from cryptography.fernet import Fernet

from app.azure_clients import MockAgentClient, compact_case_context
from app.repository import CaseRepository
from app.storage import EncryptedStore, LocalObjectStorage


def test_case_and_upload_are_encrypted(tmp_path: Path):
    storage = LocalObjectStorage(tmp_path / "data")
    store = EncryptedStore(storage, Fernet.generate_key())
    repository = CaseRepository(store)

    case = repository.create("Taylor")
    repository.add_message(case, "assistant", "Please upload a registration.")
    store.put_bytes(
        f"cases/{case['id']}/uploads/example.bin.enc",
        b"VIN-SECRET",
        "application/octet-stream",
    )

    raw_case = (tmp_path / "data" / f"cases/{case['id']}/case.json.enc").read_bytes()
    raw_upload = (
        tmp_path / "data" / f"cases/{case['id']}/uploads/example.bin.enc"
    ).read_bytes()
    assert b"Taylor" not in raw_case
    assert b"VIN-SECRET" not in raw_upload
    assert repository.get(case["id"])["customerName"] == "Taylor"
    assert store.get_bytes(
        f"cases/{case['id']}/uploads/example.bin.enc"
    ) == b"VIN-SECRET"


def test_repository_lists_newest_cases_first(tmp_path: Path):
    store = EncryptedStore(
        LocalObjectStorage(tmp_path / "data"), Fernet.generate_key()
    )
    repository = CaseRepository(store)
    first = repository.create("First")
    second = repository.create("Second")
    first["status"] = "complete"
    repository.save(first)

    cases = repository.list()
    assert {case["id"] for case in cases} == {first["id"], second["id"]}
    assert cases[0]["id"] == first["id"]


def test_case_record_keeps_analysis_for_employee_review(tmp_path: Path):
    store = EncryptedStore(
        LocalObjectStorage(tmp_path / "data"), Fernet.generate_key()
    )
    repository = CaseRepository(store)
    case = repository.create("Taylor")
    case["status"] = "employee-review"
    case["uploads"].append(
        {
            "id": "upload-1",
            "filename": "vehicle.jpg",
            "contentType": "image/jpeg",
            "size": 12,
            "analysis": {"summary": "Private analysis"},
        }
    )
    repository.save(case)

    review_record = repository.get(case["id"])
    assert review_record["status"] == "employee-review"
    assert review_record["uploads"][0]["analysis"]["summary"] == "Private analysis"


def test_compact_context_includes_mock_analysis_fields():
    case = {
        "id": "case-1",
        "status": "clarification-needed",
        "uploads": [
            {
                "filename": "registration.pdf",
                "contentType": "application/pdf",
                "analysis": {
                    "summary": "Registration extracted.",
                    "contentUnderstanding": {
                        "fields": {"vin": {"value": "TESTVIN", "confidence": 0.99}}
                    },
                },
            }
        ],
    }

    context = compact_case_context(case)
    assert "TESTVIN" in context


def test_mock_employee_agent_does_not_invent_missing_vin():
    answer = asyncio.run(
        MockAgentClient().ask(
            "employee-evidence",
            'Employee question: Does the VIN match? Case context: {"uploads":[]}',
        )
    )
    assert "cannot be confirmed" in answer
