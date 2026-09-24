from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from azure.identity import DefaultAzureCredential, ManagedIdentityCredential


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VIDEO = (
    REPOSITORY_ROOT
    / "data"
    / "Dr._Rick_Tuning_In_Progressive_Insurance_Commercial [Ufzt44z-Ng0].webm"
)
DEFAULT_OUTPUT_DIR = REPOSITORY_ROOT / "output" / "video-analysis"
DEFAULT_ANALYZER_ID = "flvCommercialVideoAnalyzer"
DEFAULT_API_VERSION = "2025-11-01"
DEFAULT_STAGING_CONTAINER = "cu-video-staging"
SUPPORTED_VIDEO_SUFFIXES = {".mp4", ".m4v", ".flv", ".wmv", ".asf", ".avi", ".mkv", ".mov"}


def _video_content_type(video_path: Path) -> str:
    return {
        ".mp4": "video/mp4",
        ".m4v": "video/x-m4v",
        ".flv": "video/x-flv",
        ".wmv": "video/x-ms-wmv",
        ".asf": "video/x-ms-asf",
        ".avi": "video/x-msvideo",
        ".mkv": "video/x-matroska",
        ".mov": "video/quicktime",
    }.get(video_path.suffix.lower(), "application/octet-stream")


def prepare_video_for_content_understanding(
    video_path: Path,
    output_dir: Path,
) -> Path:
    if video_path.suffix.lower() in SUPPORTED_VIDEO_SUFFIXES:
        return video_path
    output_dir.mkdir(parents=True, exist_ok=True)
    converted_path = output_dir / f"{video_path.stem}.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(converted_path),
        ],
        check=True,
    )
    return converted_path


def build_credential(app_env: str) -> object:
    if app_env == "development":
        return DefaultAzureCredential()
    return ManagedIdentityCredential(client_id=os.getenv("AZURE_CLIENT_ID"))


def build_content_understanding_client(
    endpoint: str,
    credential: object,
    *,
    api_version: str,
    polling_interval_seconds: float,
) -> object:
    from azure.ai.contentunderstanding import ContentUnderstandingClient

    return ContentUnderstandingClient(
        endpoint=endpoint,
        credential=credential,
        api_version=api_version,
        polling_interval=int(polling_interval_seconds),
    )


@dataclass
class StagedVideo:
    url: str
    blob_client: object

    def cleanup(self) -> None:
        self.blob_client.delete_blob()  # type: ignore[attr-defined]


def _storage_account_name(account_url: str) -> str:
    host = urlparse(account_url).netloc
    if not host:
        raise ValueError("Storage account URL must include a host name.")
    return host.split(".", maxsplit=1)[0]


def stage_video_for_analysis(
    *,
    video_path: Path,
    storage_account_url: str,
    container_name: str,
    credential: object,
    sas_ttl_minutes: int = 60,
) -> StagedVideo:
    from azure.core.exceptions import ResourceExistsError
    from azure.storage.blob import (
        BlobSasPermissions,
        BlobServiceClient,
        ContentSettings,
        generate_blob_sas,
    )

    if not video_path.is_file():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    service = BlobServiceClient(account_url=storage_account_url, credential=credential)
    container = service.get_container_client(container_name)
    try:
        container.create_container()
    except ResourceExistsError:
        pass

    blob_name = f"content-understanding-video/{uuid4().hex}/{video_path.name}"
    blob_client = container.get_blob_client(blob_name)
    blob_client.upload_blob(
        video_path.read_bytes(),
        overwrite=True,
        content_settings=ContentSettings(content_type=_video_content_type(video_path)),
    )

    now = datetime.now(timezone.utc)
    starts_on = now - timedelta(minutes=5)
    expires_on = now + timedelta(minutes=sas_ttl_minutes)
    delegation_key = service.get_user_delegation_key(starts_on, expires_on)
    sas = generate_blob_sas(
        account_name=_storage_account_name(storage_account_url),
        container_name=container_name,
        blob_name=blob_name,
        user_delegation_key=delegation_key,
        permission=BlobSasPermissions(read=True),
        start=starts_on,
        expiry=expires_on,
    )
    return StagedVideo(url=f"{blob_client.url}?{sas}", blob_client=blob_client)


def build_analysis_input(
    *,
    video_url: str,
    analysis_input_factory: object | None = None,
) -> object:
    if analysis_input_factory is None:
        from azure.ai.contentunderstanding.models import AnalysisInput

        analysis_input_factory = AnalysisInput

    return analysis_input_factory(url=video_url)


def _to_json_compatible(value: Any) -> Any:
    if hasattr(value, "as_dict"):
        return _to_json_compatible(value.as_dict())
    if isinstance(value, Mapping):
        return {str(key): _to_json_compatible(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_to_json_compatible(item) for item in value]
    return value


def analyze_video(
    *,
    endpoint: str,
    credential: object,
    video_path: Path | None = None,
    video_url: str | None = None,
    storage_account_url: str | None = None,
    staging_container: str = DEFAULT_STAGING_CONTAINER,
    analyzer_id: str = DEFAULT_ANALYZER_ID,
    api_version: str = DEFAULT_API_VERSION,
    poll_interval_seconds: float = 2,
    timeout_seconds: float = 1800,
    client: object | None = None,
    analysis_input_factory: object | None = None,
    video_stager: Callable[..., StagedVideo] = stage_video_for_analysis,
) -> dict[str, Any]:
    if not endpoint.strip():
        raise ValueError("A Content Understanding endpoint is required.")
    if poll_interval_seconds < 0:
        raise ValueError("poll_interval_seconds cannot be negative.")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than zero.")

    if bool(video_path) == bool(video_url):
        raise ValueError("Provide exactly one of video_path or video_url.")

    staged_video: StagedVideo | None = None
    if video_path:
        if not storage_account_url:
            raise ValueError(
                "Local video input must be staged to Blob Storage. Set "
                "AZURE_STORAGE_ACCOUNT_URL, pass --storage-account-url, or use "
                "--video-url with a public or SAS URL."
            )
        staged_video = video_stager(
            video_path=video_path,
            storage_account_url=storage_account_url,
            container_name=staging_container,
            credential=credential,
        )
        video_url = staged_video.url

    assert video_url is not None
    analysis_input = build_analysis_input(
        video_url=video_url,
        analysis_input_factory=analysis_input_factory,
    )
    owns_client = client is None
    sdk_client = client or build_content_understanding_client(
        endpoint,
        credential,
        api_version=api_version,
        polling_interval_seconds=poll_interval_seconds,
    )

    try:
        poller = sdk_client.begin_analyze(
            analyzer_id=analyzer_id,
            inputs=[analysis_input],
        )
        result = _to_json_compatible(poller.result(timeout=timeout_seconds))
        if not _contents(result):
            raise RuntimeError(
                "Content Understanding returned no video segments. Verify the video "
                "format is supported and the resource's model deployment defaults "
                "have available quota."
            )
        return result
    finally:
        if staged_video is not None:
            staged_video.cleanup()
        if owns_client and hasattr(sdk_client, "close"):
            sdk_client.close()


def _contents(result: dict[str, Any]) -> list[dict[str, Any]]:
    contents = result.get("contents") or result.get("result", {}).get("contents", [])
    return [content for content in contents if isinstance(content, dict)]


def combined_markdown(result: dict[str, Any]) -> str:
    sections = [
        str(content["markdown"]).strip()
        for content in _contents(result)
        if content.get("markdown")
    ]
    return "\n\n".join(sections) + ("\n" if sections else "")


def segment_report(result: dict[str, Any]) -> list[dict[str, Any]]:
    report = []
    for index, content in enumerate(_contents(result), start=1):
        fields = content.get("fields", {})
        summary_field = fields.get("Summary", {}) if isinstance(fields, dict) else {}
        summary = (
            summary_field.get("valueString")
            or summary_field.get("value")
            if isinstance(summary_field, dict)
            else None
        )
        report.append(
            {
                "segment": index,
                "startTimeMs": content.get("startTimeMs")
                or content.get("start_time_ms"),
                "endTimeMs": content.get("endTimeMs") or content.get("end_time_ms"),
                "summary": summary,
                "keyFrameCount": len(content.get("frames", [])),
            }
        )
    return report


def write_artifacts(
    result: dict[str, Any],
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "analysis.json"
    markdown_path = output_dir / "analysis.md"
    json_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(combined_markdown(result), encoding="utf-8")
    return json_path, markdown_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze a video with the Content Understanding Python SDK and "
            f"{DEFAULT_ANALYZER_ID}."
        )
    )
    parser.add_argument(
        "--endpoint",
        default=os.getenv("CONTENT_UNDERSTANDING_ENDPOINT"),
        help="Content Understanding endpoint. Defaults to CONTENT_UNDERSTANDING_ENDPOINT.",
    )
    parser.add_argument("--video", type=Path, default=DEFAULT_VIDEO)
    parser.add_argument(
        "--video-url",
        help=(
            "Public or SAS URL to a video. When provided, the example follows the "
            "quickstart URL input shape exactly and ignores --video."
        ),
    )
    parser.add_argument(
        "--storage-account-url",
        default=os.getenv("AZURE_STORAGE_ACCOUNT_URL"),
        help=(
            "Blob account URL used to stage local --video input with a temporary "
            "user-delegation SAS. Defaults to AZURE_STORAGE_ACCOUNT_URL."
        ),
    )
    parser.add_argument(
        "--staging-container",
        default=os.getenv("CONTENT_UNDERSTANDING_VIDEO_STAGING_CONTAINER")
        or DEFAULT_STAGING_CONTAINER,
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--analyzer-id", default=DEFAULT_ANALYZER_ID)
    parser.add_argument(
        "--api-version",
        default=os.getenv("CONTENT_UNDERSTANDING_API_VERSION", DEFAULT_API_VERSION),
    )
    parser.add_argument(
        "--app-env",
        default=os.getenv("APP_ENV", "development"),
        choices=("development", "production"),
        help="Development uses DefaultAzureCredential; production uses managed identity.",
    )
    parser.add_argument("--poll-interval", type=float, default=2)
    parser.add_argument("--timeout", type=float, default=1800)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.endpoint:
        raise SystemExit("Set CONTENT_UNDERSTANDING_ENDPOINT or pass --endpoint.")

    result = analyze_video(
        endpoint=args.endpoint,
        credential=build_credential(args.app_env),
        video_path=None
        if args.video_url
        else prepare_video_for_content_understanding(args.video, args.output_dir),
        video_url=args.video_url,
        storage_account_url=args.storage_account_url,
        staging_container=args.staging_container,
        analyzer_id=args.analyzer_id,
        api_version=args.api_version,
        poll_interval_seconds=args.poll_interval,
        timeout_seconds=args.timeout,
    )
    json_path, markdown_path = write_artifacts(result, args.output_dir)

    print(f"Analyzed: {args.video_url or args.video}")
    for segment in segment_report(result):
        print(
            f"Segment {segment['segment']}: "
            f"{segment['startTimeMs']} ms -> {segment['endTimeMs']} ms, "
            f"{segment['keyFrameCount']} key frame(s)"
        )
        if segment["summary"]:
            print(f"  Summary: {segment['summary']}")
    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")


if __name__ == "__main__":
    main()
