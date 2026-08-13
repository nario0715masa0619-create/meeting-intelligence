import pytest
from pathlib import Path
from types import SimpleNamespace

from meeting_intelligence.cli import main as cli
from meeting_intelligence.cli.main import main
from meeting_intelligence.domain.errors import AnalysisProviderError


@pytest.mark.parametrize("argument,expected", [("--help", "meeting-process"), ("--version", "0.1.0")])
def test_cli_options(argument: str, expected: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main([argument])
    assert exc.value.code == 0
    assert expected in capsys.readouterr().out


class Secret:
    def get_secret_value(self) -> str:
        return "not-a-real-secret"


def fake_settings() -> SimpleNamespace:
    return SimpleNamespace(
        openai_api_key=Secret(), transcription_model="transcription", transcription_response_format="diarized_json",
        transcription_language="ja", openai_timeout_seconds=1, openai_max_retries=0, openai_max_upload_bytes=100,
        analysis_model="analysis", analysis_reasoning_effort="low", google_sheets_spreadsheet_id="sheet",
        analysis_evidence_max_attempts=2,
        google_service_account_file=Path("credential.json"), google_meetings_sheet="Meetings",
        google_decisions_sheet="Decisions", google_action_items_sheet="Action Items", google_open_items_sheet="Open Items",
    )


def test_cli_composes_pipeline_without_exposing_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "meeting.mp4"
    source.write_bytes(b"mp4")
    monkeypatch.setattr(cli, "Settings", lambda **_: fake_settings())
    monkeypatch.setattr(cli, "OpenAITranscriptionProvider", lambda **_: object())
    monkeypatch.setattr(cli, "OpenAIAnalysisProvider", lambda **_: object())
    monkeypatch.setattr(cli, "GoogleSheetsMeetingSink", lambda *_: object())
    monkeypatch.setattr(cli, "run_pipeline", lambda *args, **kwargs: SimpleNamespace(analysis=SimpleNamespace(meeting_id=args[1]), artifacts=SimpleNamespace(transcript_json_path=Path("output/transcript.json"))))
    assert main([str(source), "--meeting-id", "m1"]) == 0
    output = capsys.readouterr()
    assert "completed: m1" in output.out
    assert "not-a-real-secret" not in output.out + output.err


def test_cli_returns_failure_for_domain_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "meeting.mp4"
    source.write_bytes(b"mp4")
    monkeypatch.setattr(cli, "Settings", lambda **_: fake_settings())
    monkeypatch.setattr(cli, "OpenAITranscriptionProvider", lambda **_: object())
    monkeypatch.setattr(cli, "OpenAIAnalysisProvider", lambda **_: object())
    monkeypatch.setattr(cli, "GoogleSheetsMeetingSink", lambda *_: object())
    monkeypatch.setattr(cli, "run_pipeline", lambda *_, **__: (_ for _ in ()).throw(AnalysisProviderError("provider unavailable")))
    assert main([str(source)]) == 1
    assert "provider unavailable" in capsys.readouterr().err


def test_analyze_command_never_constructs_transcription_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    transcript = tmp_path / "transcript.json"
    transcript.write_text(
        '{"schema_version":"0.1.0","meeting_id":"m1","language":"ja","duration_seconds":1,'
        '"segments":[{"id":"seg_0001","start":0,"end":1,"speaker":null,"text":"日本語"}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "Settings", lambda **_: fake_settings())
    monkeypatch.setattr(cli, "OpenAITranscriptionProvider", lambda **_: pytest.fail("transcription provider constructed"))
    monkeypatch.setattr(cli, "OpenAIAnalysisProvider", lambda **_: object())
    monkeypatch.setattr(cli, "GoogleSheetsMeetingSink", lambda *_: object())
    monkeypatch.setattr(
        cli,
        "resume_analysis",
        lambda *args, **kwargs: SimpleNamespace(
            analysis=SimpleNamespace(meeting_id="m1"),
            transcript_path=transcript,
        ),
    )
    assert main(["analyze", str(transcript)]) == 0
