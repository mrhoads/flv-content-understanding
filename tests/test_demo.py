import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from cryptography.fernet import Fernet
from app.azure_clients import AzureAnalysisClient, MockAgentClient, compact_case_context
from app.repository import CaseRepository
from app.storage import EncryptedStore, LocalObjectStorage


def test_employee_access_is_open_for_the_demo():
    from app.main import employee_access

    employee_access()
    employee_access()


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


def test_compact_context_includes_document_intelligence_fields():
    case = {
        "id": "case-1",
        "status": "employee-review",
        "uploads": [
            {
                "filename": "DriverLicense.png",
                "contentType": "image/png",
                "analysis": {
                    "summary": "OCR completed.",
                    "contentUnderstanding": {"fields": {}},
                    "documentIntelligence": {
                        "result": {
                            "documents": [
                                {
                                    "fields": {
                                        "LicenseNumber": {
                                            "valueString": "D7654321",
                                            "confidence": 0.99,
                                        }
                                    }
                                }
                            ]
                        },
                        "pages": 1,
                    },
                },
            }
        ],
    }

    context = compact_case_context(case)
    assert "D7654321" in context


def test_compact_context_reads_analyze_result_and_suppresses_vehicle_fields():
    case = {
        "id": "case-1",
        "status": "employee-review",
        "uploads": [
            {
                "filename": "DriverLicense.png",
                "contentType": "image/png",
                "analysis": {
                    "evidenceType": "identity-document",
                    "summary": "Driver's license analyzed.",
                    "contentUnderstanding": {
                        "fields": {
                            "VehicleType": {"value": "Other"},
                            "Year": {"value": 0},
                        }
                    },
                    "documentIntelligence": {
                        "status": "succeeded",
                        "analyzeResult": {
                            "modelId": "prebuilt-idDocument",
                            "content": "DRIVER LICENSE Avery Morgan D7654321",
                            "pages": [{}],
                            "documents": [
                                {
                                    "fields": {
                                        "FirstName": {
                                            "valueString": "Avery",
                                            "confidence": 0.99,
                                        },
                                        "DocumentNumber": {
                                            "valueString": "D7654321",
                                            "confidence": 0.98,
                                        },
                                    }
                                }
                            ],
                        },
                    },
                },
            }
        ],
    }

    context = json.loads(compact_case_context(case))
    upload = context["uploads"][0]
    assert upload["evidenceType"] == "identity-document"
    assert upload["fields"] == {}
    assert upload["documentIntelligence"]["modelId"] == "prebuilt-idDocument"
    assert upload["documentIntelligence"]["pages"] == 1
    assert upload["documentIntelligence"]["textLength"] == 36
    assert upload["documentIntelligence"]["fields"]["DocumentNumber"]["value"] == "D7654321"
    assert "VehicleType" not in json.dumps(upload)


def _azure_analysis_settings():
    return SimpleNamespace(
        content_understanding_endpoint="https://cu.example",
        content_understanding_document_analyzer_id="document-analyzer",
        content_understanding_image_analyzer_id="image-analyzer",
        content_understanding_api_version="2025-05-01-preview",
        document_intelligence_endpoint="https://di.example",
        document_intelligence_api_version="2023-07-31",
    )


class _RecordingAzureAnalysisClient(AzureAnalysisClient):
    def __init__(self, responses):
        super().__init__(_azure_analysis_settings(), credential=object())
        self.responses = iter(responses)
        self.urls = []

    async def _submit_and_poll(self, url, **kwargs):
        self.urls.append(url)
        return next(self.responses)


def test_azure_analysis_routes_named_driver_license_to_id_model():
    client = _RecordingAzureAnalysisClient(
        [
            {"status": "Succeeded", "result": {"contents": []}},
            {
                "status": "succeeded",
                "analyzeResult": {
                    "modelId": "prebuilt-idDocument",
                    "documents": [
                        {
                            "fields": {
                                "DocumentNumber": {
                                    "valueString": "D7654321",
                                    "confidence": 0.98,
                                }
                            }
                        }
                    ],
                },
            },
        ]
    )

    result = asyncio.run(
        client.analyze(b"image", "image/png", "DriverLicense.png")
    )

    assert "document-analyzer:analyze" in client.urls[0]
    assert "prebuilt-idDocument:analyze" in client.urls[1]
    assert result["evidenceType"] == "identity-document"
    assert "VehicleType" not in result["summary"]


def test_azure_analysis_reruns_ambiguous_identity_image_with_id_model():
    client = _RecordingAzureAnalysisClient(
        [
            {
                "status": "Succeeded",
                "result": {
                    "contents": [
                        {"fields": {"VehicleType": {"value": "Other"}}}
                    ]
                },
            },
            {
                "status": "succeeded",
                "analyzeResult": {
                    "modelId": "prebuilt-document",
                    "content": "STATE DRIVER LICENSE DATE OF BIRTH CLASS SEX EXPIRES",
                    "pages": [{}],
                    "documents": [],
                },
            },
            {
                "status": "succeeded",
                "analyzeResult": {
                    "modelId": "prebuilt-idDocument",
                    "content": "STATE DRIVER LICENSE",
                    "pages": [{}],
                    "documents": [
                        {
                            "fields": {
                                "FirstName": {
                                    "valueString": "Avery",
                                    "confidence": 0.99,
                                }
                            }
                        }
                    ],
                },
            },
        ]
    )

    result = asyncio.run(client.analyze(b"image", "image/png", "upload.png"))

    assert "image-analyzer:analyze" in client.urls[0]
    assert "prebuilt-document:analyze" in client.urls[1]
    assert "prebuilt-idDocument:analyze" in client.urls[2]
    assert result["evidenceType"] == "identity-document"
    assert "FirstName" in result["summary"]


def test_mock_employee_agent_does_not_invent_missing_vin():
    answer = asyncio.run(
        MockAgentClient().ask(
            "employee-evidence",
            'Employee question: Does the VIN match? Case context: {"uploads":[]}',
        )
    )
    assert "cannot be confirmed" in answer


def test_mock_employee_agent_summarizes_uploaded_vehicle_photo():
    context = {
        "uploads": [
            {
                "contentType": "image/jpeg",
                "summary": "Vehicle photo",
                "fields": {
                    "contentType": {"value": "Vehicle photo"},
                    "color": {"value": "Green"},
                    "make": {"value": "Toyota"},
                    "model": {"value": "Corolla"},
                },
            }
        ]
    }
    answer = asyncio.run(
        MockAgentClient().ask(
            "employee-evidence",
            "Employee instruction: Summarize what was uploaded in this case. "
            f"Case context: {json.dumps(context)}",
        )
    )
    assert "color: Green" in answer
    assert "make: Toyota" in answer
    assert "model: Corolla" in answer
    assert "Honda" not in answer


def test_mock_employee_agent_uses_document_intelligence_for_driver_license():
    context = {
        "uploads": [
            {
                "filename": "DriverLicense.png",
                "contentType": "image/png",
                "summary": "The image underwent OCR.",
                "fields": {
                    "documentType": {"value": "Driver's License"},
                    "vehicleType": {"value": "Other"},
                },
                "documentIntelligence": {
                    "fields": {
                        "firstName": {"value": "Avery"},
                        "lastName": {"value": "Morgan"},
                        "licenseNumber": {"value": "D7654321"},
                        "issuingState": {"value": "Oregon"},
                    }
                },
            }
        ]
    }
    answer = asyncio.run(
        MockAgentClient().ask(
            "employee-evidence",
            "Employee instruction: Summarize what was uploaded in this case. "
            f"Case context: {json.dumps(context)}",
        )
    )
    assert "Document Intelligence results" in answer
    assert "licenseNumber: D7654321" in answer
    assert "issuingState: Oregon" in answer
    assert "Extracted Vehicle Details" not in answer
