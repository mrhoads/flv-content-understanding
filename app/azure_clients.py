from __future__ import annotations

import asyncio
import base64
import json
import os
from typing import Any

import httpx
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential

from app.config import Settings


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
        analyzer_id = (
            self.settings.content_understanding_document_analyzer_id
            if is_document
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
            di_url = (
                f"{self.settings.document_intelligence_endpoint.rstrip('/')}"
                "/formrecognizer/documentModels/prebuilt-document:analyze"
                f"?api-version={self.settings.document_intelligence_api_version}"
            )
            document_intelligence = await self._submit_and_poll(
                di_url,
                payload=payload,
                content_type=content_type,
            )

        return {
            "contentUnderstanding": content_understanding,
            "documentIntelligence": document_intelligence,
            "summary": _summarize_analysis(
                content_understanding, document_intelligence
            ),
        }


class MockAnalysisClient:
    async def analyze(
        self, payload: bytes, content_type: str, filename: str
    ) -> dict[str, Any]:
        is_document = "pdf" in content_type or any(
            word in filename.lower() for word in ("registration", "title", "form")
        )
        if is_document:
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
            "contentUnderstanding": {"fields": fields},
            "documentIntelligence": {
                "textLength": len(payload),
                "pages": 1,
            }
            if is_document
            else None,
            "summary": summary,
        }


def _summarize_analysis(
    content_understanding: dict[str, Any],
    document_intelligence: dict[str, Any] | None,
) -> str:
    fields = (
        content_understanding.get("result", {}).get("contents", [{}])[0].get("fields")
        or content_understanding.get("fields")
        or {}
    )
    field_names = ", ".join(fields.keys()) if isinstance(fields, dict) else ""
    document_note = " Document OCR was also completed." if document_intelligence else ""
    return f"Analysis completed. Extracted fields: {field_names or 'see raw result'}.{document_note}"


def compact_case_context(case: dict[str, Any]) -> str:
    safe_case = {
        "caseId": case["id"],
        "status": case["status"],
        "uploads": [
            {
                "filename": upload["filename"],
                "contentType": upload["contentType"],
                "summary": upload["analysis"]["summary"],
                "fields": _extract_fields(
                    upload["analysis"]["contentUnderstanding"]
                ),
            }
            for upload in case["uploads"]
        ],
    }
    return json.dumps(safe_case, ensure_ascii=True)


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
