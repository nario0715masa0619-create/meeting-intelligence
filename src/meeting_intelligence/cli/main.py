"""Command-line composition root for the batch meeting pipeline."""

import argparse
from collections.abc import Sequence
from pathlib import Path
import re
import sys

from meeting_intelligence import __version__
from meeting_intelligence.analysis.openai import OpenAIAnalysisConfig, OpenAIAnalysisProvider
from meeting_intelligence.application.pipeline import run_pipeline
from meeting_intelligence.application.resume import load_transcript_record, migrate_analysis_minutes, resume_analysis
from meeting_intelligence.config.settings import Settings
from meeting_intelligence.domain.errors import ConfigurationError, MeetingIntelligenceError
from meeting_intelligence.sheets.google import GoogleSheetsConfig, GoogleSheetsMeetingSink
from meeting_intelligence.transcription.openai import OpenAITranscriptionConfig, OpenAITranscriptionProvider


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="meeting-process",
        description="Process one meeting recording, or resume analysis from a persisted transcript.",
        epilog="Resume: meeting-process analyze <transcript.json> [--meeting-id ID]. One-time migration: meeting-process migrate-minutes <transcript.json> --meeting-id ID.",
    )
    parser.add_argument("source", nargs="?", type=Path, help="Japanese meeting MP4 file")
    parser.add_argument("--meeting-id", help="Stable output and Sheets identifier; defaults to the source filename")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def build_analyze_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="meeting-process analyze",
        description="Resume Meeting Analysis and Google Sheets projection without transcription.",
    )
    parser.add_argument("transcript", type=Path, help="Persisted canonical transcript.json")
    parser.add_argument("--meeting-id", help="Optional assertion matching transcript meeting_id")
    return parser


def _default_meeting_id(source: Path) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", source.stem).strip("-.")
    if not value:
        raise ConfigurationError("source filename cannot produce a safe meeting ID; use --meeting-id")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    raw_args = list(argv) if argv is not None else sys.argv[1:]
    if raw_args and raw_args[0] == "analyze":
        return _main_analyze(raw_args[1:])
    if raw_args and raw_args[0] == "init-sheets":
        return _main_init_sheets(raw_args[1:])
    if raw_args and raw_args[0] == "migrate-minutes":
        return _main_migrate_minutes(raw_args[1:])
    parser = build_parser()
    args = parser.parse_args(raw_args)
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
    progress = lambda message: print(message, flush=True)
    try:
        if key is None or not key.get_secret_value():
            raise ConfigurationError("OPENAI_API_KEY is not configured")
        transcription = OpenAITranscriptionProvider(api_key=key.get_secret_value(), config=OpenAITranscriptionConfig(model=settings.transcription_model, response_format=settings.transcription_response_format, language=settings.transcription_language, timeout_seconds=settings.openai_timeout_seconds, max_retries=settings.openai_max_retries, max_upload_bytes=settings.openai_max_upload_bytes), progress_callback=progress)
        analysis = OpenAIAnalysisProvider(api_key=key.get_secret_value(), config=OpenAIAnalysisConfig(model=settings.analysis_model, reasoning_effort=settings.analysis_reasoning_effort, timeout_seconds=settings.openai_timeout_seconds, max_retries=settings.openai_max_retries))
        sink = GoogleSheetsMeetingSink(GoogleSheetsConfig(spreadsheet_id=settings.google_sheets_spreadsheet_id, service_account_file=settings.google_service_account_file, meetings_sheet=settings.google_meetings_sheet, decisions_sheet=settings.google_decisions_sheet, action_items_sheet=settings.google_action_items_sheet, open_items_sheet=settings.google_open_items_sheet))
        result = run_pipeline(source, args.meeting_id or _default_meeting_id(source), settings, transcription, analysis, sink, progress=progress)
    except KeyboardInterrupt:
        print("meeting-process interrupted by user", file=sys.stderr, flush=True)
        return 130
    except MeetingIntelligenceError as exc:
        print(f"meeting-process failed: {exc}", file=sys.stderr)
        return 1
    print(f"completed: {result.analysis.meeting_id}")
    print(f"transcript: {result.artifacts.transcript_json_path}")
    print(f"meeting minutes: {result.meeting_minutes_path}")
    return 0


def _main_init_sheets(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="meeting-process init-sheets", description="Safely initialize formal Google Sheets tabs and headers.")
    parser.parse_args(argv)
    settings = Settings(_env_file=Path.cwd() / ".env")
    try:
        sink = GoogleSheetsMeetingSink(GoogleSheetsConfig(spreadsheet_id=settings.google_sheets_spreadsheet_id, service_account_file=settings.google_service_account_file, meetings_sheet=settings.google_meetings_sheet, decisions_sheet=settings.google_decisions_sheet, action_items_sheet=settings.google_action_items_sheet, open_items_sheet=settings.google_open_items_sheet))
        sink.initialize_schema()
    except MeetingIntelligenceError as exc:
        print(f"meeting-process init-sheets failed: {exc}", file=sys.stderr)
        return 1
    print("Google Sheets schema initialized and verified")
    return 0


def _main_analyze(argv: Sequence[str]) -> int:
    args = build_analyze_parser().parse_args(argv)
    settings = Settings(_env_file=Path.cwd() / ".env")
    key = settings.openai_api_key
    progress = lambda message: print(message, flush=True)
    try:
        load_transcript_record(args.transcript)
        if key is None or not key.get_secret_value():
            raise ConfigurationError("OPENAI_API_KEY is not configured")
        analysis = OpenAIAnalysisProvider(
            api_key=key.get_secret_value(),
            config=OpenAIAnalysisConfig(
                model=settings.analysis_model,
                reasoning_effort=settings.analysis_reasoning_effort,
                timeout_seconds=settings.openai_timeout_seconds,
                max_retries=settings.openai_max_retries,
            ),
        )
        sink = GoogleSheetsMeetingSink(
            GoogleSheetsConfig(
                spreadsheet_id=settings.google_sheets_spreadsheet_id,
                service_account_file=settings.google_service_account_file,
                meetings_sheet=settings.google_meetings_sheet,
                decisions_sheet=settings.google_decisions_sheet,
                action_items_sheet=settings.google_action_items_sheet,
                open_items_sheet=settings.google_open_items_sheet,
            )
        )
        result = resume_analysis(
            args.transcript,
            analysis,
            sink,
            expected_meeting_id=args.meeting_id,
            max_attempts=settings.analysis_evidence_max_attempts,
            progress=progress,
        )
    except KeyboardInterrupt:
        print("meeting-process analyze interrupted by user", file=sys.stderr, flush=True)
        return 130
    except MeetingIntelligenceError as exc:
        print(f"meeting-process analyze failed: {exc}", file=sys.stderr)
        return 1
    print(f"completed: {result.analysis.meeting_id}")
    print(f"transcript: {result.transcript_path}")
    print(f"meeting minutes: {result.meeting_minutes_path}")
    return 0


def _main_migrate_minutes(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="meeting-process migrate-minutes",
        description="Explicitly create meeting-minutes.md and migrate one existing Sheets row.",
    )
    parser.add_argument("transcript", type=Path, help="Persisted canonical transcript.json")
    parser.add_argument("--meeting-id", required=True, help="Exact existing meeting ID to migrate")
    args = parser.parse_args(argv)
    settings = Settings(_env_file=Path.cwd() / ".env")
    key = settings.openai_api_key
    progress = lambda message: print(message, flush=True)
    try:
        if key is None or not key.get_secret_value():
            raise ConfigurationError("OPENAI_API_KEY is not configured")
        analysis = OpenAIAnalysisProvider(
            api_key=key.get_secret_value(),
            config=OpenAIAnalysisConfig(
                model=settings.analysis_model,
                reasoning_effort=settings.analysis_reasoning_effort,
                timeout_seconds=settings.openai_timeout_seconds,
                max_retries=settings.openai_max_retries,
            ),
        )
        sink = GoogleSheetsMeetingSink(GoogleSheetsConfig(
            spreadsheet_id=settings.google_sheets_spreadsheet_id,
            service_account_file=settings.google_service_account_file,
            meetings_sheet=settings.google_meetings_sheet,
            decisions_sheet=settings.google_decisions_sheet,
            action_items_sheet=settings.google_action_items_sheet,
            open_items_sheet=settings.google_open_items_sheet,
        ))
        result = migrate_analysis_minutes(
            args.transcript,
            analysis,
            sink,
            expected_meeting_id=args.meeting_id,
            max_attempts=settings.analysis_evidence_max_attempts,
            progress=progress,
        )
    except KeyboardInterrupt:
        print("meeting-process migrate-minutes interrupted by user", file=sys.stderr, flush=True)
        return 130
    except MeetingIntelligenceError as exc:
        print(f"meeting-process migrate-minutes failed: {exc}", file=sys.stderr)
        return 1
    print(f"completed: {result.analysis.meeting_id}")
    print(f"meeting minutes: {result.meeting_minutes_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
