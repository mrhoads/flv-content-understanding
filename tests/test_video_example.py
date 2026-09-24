import json
from pathlib import Path

import pytest

from examples.analyze_video import (
    DEFAULT_ANALYZER_ID,
    StagedVideo,
    analyze_video,
    build_analysis_input,
    combined_markdown,
    prepare_video_for_content_understanding,
    segment_report,
    write_artifacts,
)


class _Credential:
    def get_token(self, scope: str):
        return type("Token", (), {"token": "test-token"})()


class _Poller:
    def __init__(self, result):
        self._result = result

    def result(self, timeout=None):
        if isinstance(self._result, BaseException):
            raise self._result
        return self._result


class _ContentUnderstandingClient:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def begin_analyze(self, **kwargs):
        self.calls.append(kwargs)
        return _Poller(self.result)


class _SdkResult(dict):
    def as_dict(self):
        return dict(self)


def _analysis_input(**kwargs):
    return kwargs


class _BlobClient:
    def __init__(self):
        self.deleted = False

    def delete_blob(self):
        self.deleted = True


def test_build_analysis_input_uses_quickstart_url_shape():
    assert build_analysis_input(
        video_url="https://example.com/commercial.webm",
        analysis_input_factory=_analysis_input,
    ) == {"url": "https://example.com/commercial.webm"}


def test_prepare_video_leaves_supported_video_unchanged(tmp_path: Path):
    video = tmp_path / "commercial.mp4"
    video.write_bytes(b"mp4-data")

    assert prepare_video_for_content_understanding(video, tmp_path / "output") == video


def test_analyze_video_uses_sdk_begin_analyze_with_video_url():
    client = _ContentUnderstandingClient(
        _SdkResult(status="Succeeded", contents=[{"markdown": "# Video"}])
    )

    result = analyze_video(
        endpoint="https://cu.example",
        credential=_Credential(),
        video_url="https://example.com/commercial.webm?sas=1",
        poll_interval_seconds=0,
        timeout_seconds=42,
        client=client,
        analysis_input_factory=_analysis_input,
    )

    assert result["status"] == "Succeeded"
    assert client.calls == [
        {
            "analyzer_id": DEFAULT_ANALYZER_ID,
            "inputs": [{"url": "https://example.com/commercial.webm?sas=1"}],
        }
    ]


def test_default_api_version_matches_python_quickstart():
    from examples.analyze_video import DEFAULT_API_VERSION

    assert DEFAULT_API_VERSION == "2025-11-01"


def test_commercial_video_analyzer_extracts_advertising_fields():
    analyzer_path = Path("infra/analyzers/commercial-video.json")

    analyzer = json.loads(analyzer_path.read_text())
    fields = analyzer["fieldSchema"]["fields"]

    assert analyzer["baseAnalyzerId"] == "prebuilt-video"
    assert analyzer["config"]["enableSegment"] is False
    assert {
        "AdvertiserBrand",
        "VisibleProducts",
        "Characters",
        "MusicAndAudio",
        "OnScreenText",
        "CommercialMessage",
    }.issubset(fields)


def test_analyze_video_stages_local_webm_as_quickstart_url_input(tmp_path: Path):
    video = tmp_path / "commercial.webm"
    video.write_bytes(b"webm-data")
    blob_client = _BlobClient()
    client = _ContentUnderstandingClient(
        _SdkResult(status="Succeeded", contents=[{"markdown": "# Video"}])
    )

    def stager(**kwargs):
        assert kwargs["video_path"] == video
        assert kwargs["storage_account_url"] == "https://storage.example"
        assert kwargs["container_name"] == "stage"
        return StagedVideo(
            url="https://storage.example/stage/commercial.webm?sas=1",
            blob_client=blob_client,
        )

    result = analyze_video(
        endpoint="https://cu.example",
        credential=_Credential(),
        video_path=video,
        storage_account_url="https://storage.example",
        staging_container="stage",
        poll_interval_seconds=0,
        timeout_seconds=42,
        client=client,
        analysis_input_factory=_analysis_input,
        video_stager=stager,
    )

    assert result["status"] == "Succeeded"
    assert blob_client.deleted
    assert client.calls == [
        {
            "analyzer_id": DEFAULT_ANALYZER_ID,
            "inputs": [{"url": "https://storage.example/stage/commercial.webm?sas=1"}],
        }
    ]


def test_analyze_video_surfaces_failed_operation(tmp_path: Path):
    video = tmp_path / "commercial.webm"
    video.write_bytes(b"webm-data")
    client = _ContentUnderstandingClient(RuntimeError("Unsupported video"))

    with pytest.raises(RuntimeError, match="Unsupported video"):
        analyze_video(
            endpoint="https://cu.example",
            credential=_Credential(),
            video_url="https://example.com/commercial.webm?sas=1",
            poll_interval_seconds=0,
            client=client,
            analysis_input_factory=_analysis_input,
        )


def test_analyze_video_rejects_empty_video_result():
    client = _ContentUnderstandingClient(_SdkResult(status="Succeeded", contents=[]))

    with pytest.raises(RuntimeError, match="returned no video segments"):
        analyze_video(
            endpoint="https://cu.example",
            credential=_Credential(),
            video_url="https://example.com/commercial.webm?sas=1",
            poll_interval_seconds=0,
            client=client,
            analysis_input_factory=_analysis_input,
        )


def test_video_outputs_include_all_segments(tmp_path: Path):
    result = {
        "status": "Succeeded",
        "contents": [
            {
                "start_time_ms": 0,
                "end_time_ms": 5000,
                "markdown": "# Video: 00:00.000 => 00:05.000",
                "fields": {"Summary": {"valueString": "Opening scene"}},
                "frames": [{"timestampMs": 1000}],
            },
            {
                "startTimeMs": 5000,
                "endTimeMs": 10000,
                "markdown": "## Video: 00:05.000 => 00:10.000",
                "fields": {"Summary": {"value": "Closing scene"}},
                "frames": [],
            },
        ],
    }

    assert "# Video" in combined_markdown(result)
    assert "## Video" in combined_markdown(result)
    assert segment_report(result) == [
        {
            "segment": 1,
            "startTimeMs": 0,
            "endTimeMs": 5000,
            "summary": "Opening scene",
            "keyFrameCount": 1,
        },
        {
            "segment": 2,
            "startTimeMs": 5000,
            "endTimeMs": 10000,
            "summary": "Closing scene",
            "keyFrameCount": 0,
        },
    ]

    json_path, markdown_path = write_artifacts(result, tmp_path / "output")
    assert json.loads(json_path.read_text()) == result
    assert markdown_path.read_text().endswith("\n")
