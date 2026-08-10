"""Command-line composition root for the batch meeting pipeline."""

import argparse
from collections.abc import Sequence
from pathlib import Path
import re
import sys

from meeting_intelligence import __version__
from meeting_intelligence.analysis.openai import OpenAIAnalysisConfig, OpenAIAnalysisProvider
from meeting_intelligence.application.pipeline import run_pipeline
from meeting_intelligence.config.settings import Settings
from meeting_intelligence.domain.errors import ConfigurationError, MeetingIntelligenceError
from meeting_intelligence.sheets.google import GoogleSheetsConfig, GoogleSheetsMeetingSink
from meeting_intelligence.transcription.openai import OpenAITranscriptionConfig, OpenAITranscriptionProvider


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="meeting-process", description="Process one meeting recording into canonical transcript artifacts and Google Sheets.")
    parser.add_argument("source", nargs="?", type=Path, help="Japanese meeting MP4 file")
    parser.add_argument("--meeting-id", help="Stable output and Sheets identifier; defaults to the source filename")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _default_meeting_id(source: Path) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", source.stem).strip("-.")
    if not value:
        raise ConfigurationError("source filename cannot produce a safe meeting ID; use --meeting-id")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.source is None:
        parser.print_help()
        return 0
    source = args.source.expanduser()
    if not source.is_file():
        parser.error("source must identify an existing file")
    if source.suffix.lower() != ".mp4":
        parser.error("source must be an MP4 file")
    settings = Settings(_env_file=Path.cwd() / ".env")
    key = settings.openai_api_key
    try:
        if key is None or not key.get_secret_value():
            raise ConfigurationError("OPENAI_API_KEY is not configured")
        transcription = OpenAITranscriptionProvider(api_key=key.get_secret_value(), config=OpenAITranscriptionConfig(model=settings.transcription_model, response_format=settings.transcription_response_format, language=settings.transcription_language, timeout_seconds=settings.openai_timeout_seconds, max_retries=settings.openai_max_retries, max_upload_bytes=settings.openai_max_upload_bytes))
        analysis = OpenAIAnalysisProvider(api_key=key.get_secret_value(), config=OpenAIAnalysisConfig(model=settings.analysis_model, reasoning_effort=settings.analysis_reasoning_effort, timeout_seconds=settings.openai_timeout_seconds, max_retries=settings.openai_max_retries))
        sink = GoogleSheetsMeetingSink(GoogleSheetsConfig(spreadsheet_id=settings.google_sheets_spreadsheet_id, service_account_file=settings.google_service_account_file, meetings_sheet=settings.google_meetings_sheet, decisions_sheet=settings.google_decisions_sheet, action_items_sheet=settings.google_action_items_sheet, open_items_sheet=settings.google_open_items_sheet))
        result = run_pipeline(source, args.meeting_id or _default_meeting_id(source), settings, transcription, analysis, sink)
    except MeetingIntelligenceError as exc:
        print(f"meeting-process failed: {exc}", file=sys.stderr)
        return 1
    print(f"completed: {result.analysis.meeting_id}")
    print(f"transcript: {result.artifacts.transcript_json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
