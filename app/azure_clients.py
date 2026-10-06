from __future__ import annotations

import asyncio
import base64
import json
import os
from typing import Any

import httpx
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential

from app.config import Settings


IDENTITY_FILENAME_TERMS = ("driver", "license", "licence", "id-card", "id_card")


def build_credential(settings: Settings) -> object:
    if settings.app_env == "development":
        return DefaultAzureCredential()
    return ManagedIdentityCredential(client_id=os.getenv("AZURE_CLIENT_ID"))


class FoundryAgentClient:
    def __init__(self, settings: Settings, credential: object):
        self.settings = settings
        self.credential = credential
        self._openai_clients: dict[str, object] = {}

    def _client(self, agent_name: str):
        if agent_name not in self._openai_clients:
            from azure.ai.projects import AIProjectClient

            project = AIProjectClient(
                endpoint=self.settings.foundry_project_endpoint,
                credential=self.credential,
            )
            self._openai_clients[agent_name] = project.get_openai_client(
                agent_name=agent_name
            )
        return self._openai_clients[agent_name]

    async def ask(self, agent_name: str, prompt: str) -> str:
        response = await asyncio.to_thread(
            self._client(agent_name).responses.create,
            input=prompt,
        )
        return response.output_text


class MockAgentClient:
    async def ask(self, agent_name: str, prompt: str) -> str:
        lowered = prompt.lower()
        if "employee" in agent_name or "internal" in lowered:
            context = _mock_case_context(prompt)
            if "summarize what was uploaded" in lowered:
                return _summarize_mock_uploads(context)
            has_vin = '"vin"' in lowered or "1hgbh41jxmn109186" in lowered
            has_vehicle_photo = '"vehicle photo"' in lowered
            if "vin" in lowered and has_vin and has_vehicle_photo:
                return (
                    "The submitted registration lists VIN 1HGBH41JXMN109186. "
                    "The vehicle image analysis found the same VIN with high confidence."
                )
            if "vin" in lowered and has_vin:
                return (
                    "VIN 1HGBH41JXMN109186 was extracted from the submitted document with "
                    "high confidence, but no second VIN source is available for comparison."
                )
            if "vin" in lowered:
                return (
                    "No VIN was extracted from the submitted evidence, so a match cannot "
                    "be confirmed. Request a clear VIN plate image or registration document."
                )
            if has_vehicle_photo:
                return (
                    "The uploaded image was recognized as a blue 2022 Honda Accord with "
                    "no obvious exterior damage detected. Make and model confidence were "
                    "high; the model-year confidence was lower and should be corroborated."
                )
            return (
                "The available case evidence does not contain enough extracted detail to "
                "answer that question. Review the upload or request clearer evidence."
            )
        if "uploaded" in lowered:
            return (
                "Thanks — I received it. The information appears clear and the key "
                "vehicle details are consistent. Could you also confirm whether the "
                "vehicle currently has any visible damage not shown in the image?"
            )
        return (
            "Hello! To complete your first-look verification, please upload a clear "
            "photo of your vehicle or a readable copy of its current registration or "
            "title. Please avoid including unrelated personal documents."
        )


def _mock_case_context(prompt: str) -> dict[str, Any]:
    marker = "Case context:"
    if marker not in prompt:
        return {}
    try:
        context = json.loads(prompt.split(marker, 1)[1].strip())
    except json.JSONDecodeError:
        return {}
    return context if isinstance(context, dict) else {}


def _summarize_mock_uploads(context: dict[str, Any]) -> str:
    uploads = context.get("uploads", [])
    if not isinstance(uploads, list) or not uploads:
        return (
            "The case does not contain enough extracted upload detail to provide a "
            "summary. Review the submitted files or request clearer evidence."
        )

    descriptions = []
    for upload in uploads:
        if not isinstance(upload, dict):
            continue
        filename = upload.get("filename", "Unnamed file")
        fields = upload.get("fields", {})
        document_intelligence = upload.get("documentIntelligence")
        if _is_identity_document(filename, fields, document_intelligence):
            details = _format_document_fields(fields, document_intelligence)
            description = f"{filename}: Document Intelligence results"
            if details:
                description += f". Extracted document fields: {details}."
            descriptions.append(description)
            continue
        details = []
        if isinstance(fields, dict):
            for name, field in fields.items():
                value = field.get("value") if isinstance(field, dict) else field
                if value not in (None, "") and name != "contentType":
                    details.append(f"{name}: {value}")
        summary = upload.get("summary") or "No extracted summary is available."
        description = f"{filename}: {summary}"
        if details:
            description += f" Extracted details: {', '.join(details)}."
        descriptions.append(description)

    if not descriptions:
        return (
            "The case does not contain enough extracted upload detail to provide a "
            "summary. Review the submitted files or request clearer evidence."
        )
    return "Uploaded evidence summary:\n" + "\n".join(
        f"- {description}" for description in descriptions
    )


def _is_identity_document(
    filename: str,
    fields: dict[str, Any],
    document_intelligence: dict[str, Any] | None,
) -> bool:
    if _filename_suggests_identity_document(filename):
        return True
    document_type = fields.get("documentType")
    if isinstance(document_type, dict):
        document_type = document_type.get("value")
    if not isinstance(document_type, str) and document_intelligence:
        document_type = document_intelligence.get("fields", {}).get("documentType")
        if isinstance(document_type, dict):
            document_type = document_type.get("value")
    if document_intelligence:
        model_id = document_intelligence.get("modelId")
        if isinstance(model_id, str) and model_id.lower() == "prebuilt-iddocument":
            return True
    return isinstance(document_type, str) and any(
        term in document_type.lower() for term in ("license", "licence", "identity")
    )


def _filename_suggests_identity_document(filename: str) -> bool:
    filename_hint = filename.lower()
    return any(term in filename_hint for term in IDENTITY_FILENAME_TERMS)


def _ocr_suggests_identity_document(result: dict[str, Any]) -> bool:
    content = _document_intelligence_result(result).get("content")
    if not isinstance(content, str):
        return False
    normalized = " ".join(content.lower().replace("’", "'").split())
    if any(
        phrase in normalized
        for phrase in (
            "driver license",
            "driver's license",
            "drivers license",
            "identification card",
        )
    ):
        return True
    signals = (
        "date of birth",
        " dob ",
        "class",
        "sex",
        "height",
        "eyes",
        "expires",
        "expiration",
    )
    return sum(signal in f" {normalized} " for signal in signals) >= 3


def _format_document_fields(
    fields: dict[str, Any],
    document_intelligence: dict[str, Any] | None,
) -> str:
    values = []
    for name, field in fields.items():
        value = field.get("value") if isinstance(field, dict) else field
        if value not in (None, ""):
            values.append(f"{name}: {value}")
    if document_intelligence:
        for name, field in document_intelligence.get("fields", {}).items():
            value = field.get("value") if isinstance(field, dict) else field
            if value not in (None, "") and not any(
                item.startswith(f"{name}:") for item in values
            ):
                values.append(f"{name}: {value}")
    return ", ".join(values)


class AzureAnalysisClient:
    def __init__(self, settings: Settings, credential: object):
        self.settings = settings
        self.credential = credential

    def _token(self) -> str:
        return self.credential.get_token(
            "https://cognitiveservices.azure.com/.default"
        ).token

    async def _submit_and_poll(
        self,
        url: str,
        *,
        payload: bytes | None = None,
        content_type: str = "application/json",
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._token()}",
            "Content-Type": content_type,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                url,
                content=payload,
                json=json_body,
                headers=headers,
            )
            response.raise_for_status()
            operation_url = response.headers.get("operation-location")
            if not operation_url:
                return response.json()
            for _ in range(60):
                await asyncio.sleep(1)
                result = await client.get(
                    operation_url,
                    headers={"Authorization": headers["Authorization"]},
                )
                result.raise_for_status()
                body = result.json()
                status = body.get("status", "").lower()
                if status in {"succeeded", "failed", "canceled"}:
                    if status != "succeeded":
                        raise RuntimeError(
                            f"Azure analysis ended with status '{status}'"
                        )
                    return body
            raise TimeoutError("Azure analysis did not complete within 60 seconds")

    async def analyze(
        self, payload: bytes, content_type: str, filename: str
    ) -> dict[str, Any]:
        is_document = content_type == "application/pdf" or filename.lower().endswith(
            (".pdf", ".tif", ".tiff")
        )
        is_identity_document = _filename_suggests_identity_document(filename)
        analyzer_id = (
            self.settings.content_understanding_document_analyzer_id
            if is_document or is_identity_document
            else self.settings.content_understanding_image_analyzer_id
        )
        cu_url = (
            f"{self.settings.content_understanding_endpoint.rstrip('/')}"
            f"/contentunderstanding/analyzers/{analyzer_id}:analyze"
            f"?api-version={self.settings.content_understanding_api_version}"
        )
        content_understanding = await self._submit_and_poll(
            cu_url,
            json_body={
                "inputs": [
                    {
                        "name": filename,
                        "data": base64.b64encode(payload).decode("ascii"),
                        "mimeType": content_type,
                    }
                ]
            },
        )

        document_intelligence = None
        if is_document or content_type.startswith("image/"):
            model_id = (
                "prebuilt-idDocument"
                if is_identity_document
                else "prebuilt-document"
            )
            document_intelligence = await self._analyze_document(
                payload, content_type, model_id
            )
            if (
                not is_identity_document
                and _ocr_suggests_identity_document(document_intelligence)
            ):
                is_identity_document = True
                document_intelligence = await self._analyze_document(
                    payload, content_type, "prebuilt-idDocument"
                )

        return {
            "evidenceType": (
                "identity-document" if is_identity_document else "vehicle-evidence"
            ),
            "contentUnderstanding": content_understanding,
            "documentIntelligence": document_intelligence,
            "summary": _summarize_analysis(
                content_understanding,
                document_intelligence,
                is_identity_document=is_identity_document,
            ),
        }

    async def _analyze_document(
        self, payload: bytes, content_type: str, model_id: str
    ) -> dict[str, Any]:
        di_url = (
            f"{self.settings.document_intelligence_endpoint.rstrip('/')}"
            f"/formrecognizer/documentModels/{model_id}:analyze"
            f"?api-version={self.settings.document_intelligence_api_version}"
        )
        return await self._submit_and_poll(
            di_url,
            payload=payload,
            content_type=content_type,
        )


class MockAnalysisClient:
    async def analyze(
        self, payload: bytes, content_type: str, filename: str
    ) -> dict[str, Any]:
        is_document = "pdf" in content_type or any(
            word in filename.lower() for word in ("registration", "title", "form")
        )
        is_identity_document = _filename_suggests_identity_document(filename)
        if is_identity_document:
            fields = {
                "documentType": {"value": "Driver's License", "confidence": 0.98},
                "firstName": {"value": "Jordan", "confidence": 0.97},
                "lastName": {"value": "Lee", "confidence": 0.97},
                "dateOfBirth": {"value": "1990-04-12", "confidence": 0.95},
                "licenseNumber": {"value": "D1234567", "confidence": 0.96},
                "expirationDate": {"value": "2028-04-12", "confidence": 0.94},
                "issuingState": {"value": "Washington", "confidence": 0.98},
            }
            summary = "Driver's license document fields extracted successfully."
        elif is_document:
            fields = {
                "documentType": {"value": "Vehicle Registration", "confidence": 0.97},
                "state": {"value": "Washington", "confidence": 0.95},
                "registeredOwner": {"value": "Jordan Lee", "confidence": 0.93},
                "vin": {"value": "1HGBH41JXMN109186", "confidence": 0.99},
                "year": {"value": "2022", "confidence": 0.98},
                "make": {"value": "Honda", "confidence": 0.98},
                "model": {"value": "Accord", "confidence": 0.96},
                "expirationDate": {"value": "2027-03-31", "confidence": 0.94},
            }
            summary = "Vehicle registration extracted; all required fields are readable."
        else:
            fields = {
                "contentType": {"value": "Vehicle photo", "confidence": 0.99},
                "vehicleType": {"value": "Passenger car", "confidence": 0.97},
                "year": {"value": "2022", "confidence": 0.72},
                "make": {"value": "Honda", "confidence": 0.94},
                "model": {"value": "Accord", "confidence": 0.91},
                "color": {"value": "Blue", "confidence": 0.98},
                "visibleDamage": {"value": "None detected", "confidence": 0.88},
            }
            summary = "Passenger vehicle recognized; no obvious exterior damage detected."
        return {
            "evidenceType": (
                "identity-document" if is_identity_document else "vehicle-evidence"
            ),
            "contentUnderstanding": {"fields": fields},
            "documentIntelligence": {
                "textLength": len(payload),
                "pages": 1,
                "modelId": (
                    "prebuilt-idDocument"
                    if is_identity_document
                    else "prebuilt-document"
                ),
                "fields": fields,
            }
            if is_document or is_identity_document
            else None,
            "summary": summary,
        }


def _summarize_analysis(
    content_understanding: dict[str, Any],
    document_intelligence: dict[str, Any] | None,
    *,
    is_identity_document: bool = False,
) -> str:
    if is_identity_document:
        document_fields = _extract_document_fields(document_intelligence or {})
        field_names = ", ".join(document_fields)
        return (
            "Driver's license analyzed with Document Intelligence. "
            f"Extracted document fields: {field_names or 'OCR text only'}."
        )
    fields = (
        content_understanding.get("result", {}).get("contents", [{}])[0].get("fields")
        or content_understanding.get("fields")
        or {}
    )
    field_names = ", ".join(fields.keys()) if isinstance(fields, dict) else ""
    document_note = " Document OCR was also completed." if document_intelligence else ""
    return f"Analysis completed. Extracted fields: {field_names or 'see raw result'}.{document_note}"


def compact_case_context(case: dict[str, Any]) -> str:
    uploads = []
    for upload in case["uploads"]:
        analysis = upload["analysis"]
        document_intelligence = _compact_document_intelligence(
            analysis.get("documentIntelligence")
        )
        content_understanding_fields = _extract_fields(
            analysis.get("contentUnderstanding", {})
        )
        is_identity_document = (
            analysis.get("evidenceType") == "identity-document"
            or _is_identity_document(
                upload["filename"],
                content_understanding_fields,
                document_intelligence,
            )
        )
        uploads.append(
            {
                "filename": upload["filename"],
                "contentType": upload["contentType"],
                "evidenceType": (
                    "identity-document"
                    if is_identity_document
                    else analysis.get("evidenceType", "vehicle-evidence")
                ),
                "summary": analysis["summary"],
                "fields": (
                    {}
                    if is_identity_document
                    else content_understanding_fields
                ),
                "documentIntelligence": document_intelligence,
            }
        )
    safe_case = {
        "caseId": case["id"],
        "status": case["status"],
        "uploads": uploads,
    }
    return json.dumps(safe_case, ensure_ascii=True)


def _compact_document_intelligence(
    result: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    fields = _extract_document_fields(result)
    analyze_result = _document_intelligence_result(result)
    compact: dict[str, Any] = {}
    if fields:
        compact["fields"] = fields
    model_id = analyze_result.get("modelId")
    if isinstance(model_id, str):
        compact["modelId"] = model_id
    pages = analyze_result.get("pages")
    if isinstance(pages, list):
        compact["pages"] = len(pages)
    elif isinstance(pages, int):
        compact["pages"] = pages
    if "textLength" in result:
        compact["textLength"] = result["textLength"]
    content = analyze_result.get("content")
    if isinstance(content, str) and content:
        compact["textLength"] = len(content)
        compact["content"] = content[:4000]
    key_value_pairs = _compact_key_value_pairs(analyze_result.get("keyValuePairs"))
    if key_value_pairs:
        compact["keyValuePairs"] = key_value_pairs
    return compact or None


def _extract_document_fields(result: dict[str, Any]) -> dict[str, Any]:
    direct = result.get("fields")
    if isinstance(direct, dict):
        return _normalize_document_fields(direct)
    documents = _document_intelligence_result(result).get("documents", [])
    if isinstance(documents, list) and documents and isinstance(documents[0], dict):
        fields = documents[0].get("fields")
        if isinstance(fields, dict):
            return _normalize_document_fields(fields)
    return {}


def _document_intelligence_result(result: dict[str, Any]) -> dict[str, Any]:
    for key in ("analyzeResult", "result"):
        nested = result.get(key)
        if isinstance(nested, dict):
            return nested
    return result


def _compact_key_value_pairs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    pairs = []
    for pair in value[:40]:
        if not isinstance(pair, dict):
            continue
        key = pair.get("key")
        item_value = pair.get("value")
        key_content = key.get("content") if isinstance(key, dict) else None
        value_content = (
            item_value.get("content") if isinstance(item_value, dict) else None
        )
        if not key_content or not value_content:
            continue
        compact_pair: dict[str, Any] = {
            "key": key_content,
            "value": value_content,
        }
        if "confidence" in pair:
            compact_pair["confidence"] = pair["confidence"]
        pairs.append(compact_pair)
    return pairs


def _normalize_document_fields(fields: dict[str, Any]) -> dict[str, Any]:
    normalized = {}
    for name, field in fields.items():
        if not isinstance(field, dict):
            normalized[name] = field
            continue
        value = _document_field_value(field)
        if value is not None:
            normalized[name] = {
                "value": value,
                **({"confidence": field["confidence"]} if "confidence" in field else {}),
            }
    return normalized


def _document_field_value(field: dict[str, Any]) -> Any:
    preferred_keys = (
        "valueString",
        "valueDate",
        "valueTime",
        "valuePhoneNumber",
        "valueCountryRegion",
        "valueNumber",
        "valueInteger",
        "valueBoolean",
        "valueSelectionMark",
        "valueCurrency",
        "valueAddress",
        "valueObject",
        "valueArray",
        "content",
    )
    return next(
        (
            field[key]
            for key in preferred_keys
            if field.get(key) not in (None, "")
        ),
        None,
    )


def _extract_fields(result: dict[str, Any]) -> dict[str, Any]:
    direct = result.get("fields")
    if isinstance(direct, dict):
        return direct
    contents = result.get("result", {}).get("contents", [])
    if contents and isinstance(contents[0], dict):
        fields = contents[0].get("fields")
        if isinstance(fields, dict):
            return fields
    return {}
