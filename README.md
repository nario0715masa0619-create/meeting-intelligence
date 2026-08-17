# Meeting Intelligence

Meeting Intelligence is a standalone batch-processing tool design for converting a recorded meeting into structured knowledge that downstream systems can consume.

The MVP accepts one Japanese-language MP4 recording (primarily a Windows Game Bar recording) as one meeting. Its target flow is:

```text
Meeting Recording
        ↓
Transcript
        ↓
Meeting Understanding
        ↓
Canonical Structured Meeting Record
        ↓
Human-readable Output
```

`transcript.json` is the Canonical Primary Derived Evidence. The future `meeting.json` is the Canonical Meeting Record for structured analysis, not a replacement for or correction of the primary transcript. `meeting-minutes.md` is the human-readable detailed minutes artifact; Google Sheets is an operational index rather than the minutes store.

## Implementation status

Implementation Phase 6 composes media preparation, OpenAI transcription, immutable Transcript persistence, structured Meeting Understanding, Evidence validation, and Google Sheets projection behind one batch CLI command.

Run one Japanese MP4 meeting with:

```text
meeting-process <video-file>
```

Use an explicit stable identifier when the filename is unsuitable or when operational naming must be controlled:

```powershell
meeting-process .\input\meeting.mp4 --meeting-id customer-meeting-2026-08-10
```

Help and version remain available:

```powershell
meeting-process --help
meeting-process --version
```

Running without a source prints help and performs no processing. A failed downstream analysis or Sheets projection returns a nonzero exit code and is never reported as completed. Canonical Transcript artifacts finalized before a downstream failure remain immutable Primary Evidence.

Resume analysis from a persisted transcript without repeating media processing or paid transcription:

```powershell
meeting-process analyze `
  "output\<meeting-id>\transcript.json"
```

Add `--meeting-id <meeting-id>` to assert that the CLI input matches the Canonical Transcript. Analysis failure does not require retranscription. Resume validates the UTF-8 Canonical Transcript, performs only Meeting Analysis and Evidence validation, atomically creates `meeting-minutes.md`, and writes Google Sheets only after all Evidence IDs pass strict validation. An unknown Evidence ID triggers at most one complete analysis correction retry (two total attempts); a second failure writes nothing.

## Development setup

Python 3.11 or newer is required. Use a repository-local virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

Run the unit tests with:

```powershell
.\.venv\Scripts\python -m pytest
```

## Inbox automation

Set the formal recursive MP4 Inbox in the ignored Repository-root `.env`:

```text
MI_INBOX_ROOT=D:\work\.meeting-intelligence
MI_INBOX_STABLE_AGE_SECONDS=120
MI_INBOX_FOLDER_STABLE_AGE_SECONDS=120
MI_INBOX_CONTINUE_ON_MEETING_FAILURE=true
```

Preview deterministic meeting IDs and local processing state without filesystem mutation, ffmpeg, OpenAI, or Google API calls:

```powershell
meeting-process inbox --dry-run
```

Process stable files sequentially with:

```powershell
meeting-process inbox
```

Discovery is recursive, case-insensitive for the `.mp4` suffix, Unicode-safe, and deterministically ordered by relative path. Identity uses absolute source path, size, and SHA-256. Meeting IDs are derived from the relative path; a hash suffix is added only when an existing output collides. Files newer than the configured stability window and zero-byte files are blocked.

Phase 8.2 uses **one folder = one meeting**. One MP4 remains the compatible single-file flow; two or more MP4 files directly inside the same folder are processed as ordered parts of one meeting:

```text
260817_single/
└─ meeting.mp4

260817_multi/
├─ 01.mp4
└─ 02.mp4
```

Parts are ordered lexically by filename, prepared and transcribed separately, then combined into one global timeline, one Canonical Transcript, one detailed minutes file, and one Google Sheets meeting. Original MP4 files are never physically merged or modified. The folder and every MP4 must remain unchanged for the configured stability window. This reduces but cannot eliminate a very late-arriving part; wait until all recording parts have been copied before running Inbox. A future explicit `.ready` marker can close that remaining ambiguity.

Meeting source identity includes each ordered relative path, byte size, and SHA-256. Adding or changing a part after an earlier output blocks automatic processing instead of silently creating a replacement meeting.

The state model is `NEW`, `TRANSCRIPT_COMPLETE`, `ANALYSIS_COMPLETE`, `COMPLETE`, `FAILED_RESUMABLE`, and `BLOCKED`. Existing canonical Transcript artifacts always take the resume path and are never retranscribed. `COMPLETE` requires both local minutes and a read-only Google Sheets meeting-ID match; normal Inbox processing then performs zero paid/API processing calls. Because dry-run forbids every API call, local minutes without an Inbox completion receipt are conservatively shown as `ANALYSIS_COMPLETE` rather than guessed to be complete.

One runner-wide Windows-compatible exclusive lock prevents concurrent processing. Locks are never automatically declared stale because PID reuse and slow paid calls make automatic deletion unsafe; after confirming no runner exists, an operator may remove `.work/inbox.lock`. Non-dry runs write content-free manifests under `.work/inbox-runs/`. They contain source paths, meeting IDs, states, timestamps, and sanitized errors, never Transcript text or credentials. Sources and completed artifacts are never moved, overwritten, or deleted. The default isolates a meeting failure and continues sequentially; configuration/setup failures use exit code `2`, meeting failures use `1`, and safe all-processed/skipped completion uses `0`.

## Media prerequisite

Install the system `ffmpeg` distribution so both `ffmpeg` and `ffprobe` are on PATH. Their executable paths can be overridden through `MI_FFMPEG_PATH` and `MI_FFPROBE_PATH`.

Phase 2 prepares mono 16 kHz MP3 audio at 64 kbit/s. Long audio is split into five-minute (300-second) chunks. This is comfortably below the 1,400-second Provider limit and was live-validated against a real meeting recording. Thresholds, encoding settings, executable paths, and subprocess timeout are configurable. Existing artifacts are never silently overwritten, and source MP4 files are preserved.

The CLI prints each pipeline stage and, while waiting for a transcription response, emits a heartbeat every 15 seconds with the chunk number, duration, byte size, elapsed time, and configured timeout. The default OpenAI timeout is 300 seconds per five-minute chunk. `Ctrl+C` reports an explicit interruption and exits with code 130.

## OpenAI transcription

Set `OPENAI_API_KEY` in the ignored local Repository-root `.env` file. Never commit its value. The default model is `gpt-4o-transcribe-diarize` with `diarized_json`, Japanese language configuration, and automatic server chunking.

For one audio artifact, Provider speaker labels are preserved. For multiple Media chunks, labels are scoped such as `chunk_0001:A` because speaker identity is not assumed to remain stable across independent API calls. Normal tests use an injected fake client and never call a paid API. Live API acceptance is opt-in and is not run by the regular test suite.

To run the live OpenAI transcription acceptance test, put the following local-only values in the ignored Repository-root `.env` file. The audio must be a short Japanese WAV file outside the Repository:

```text
OPENAI_API_KEY=<set-locally>
MEETING_INTELLIGENCE_LIVE_AUDIO=C:\path\to\short-japanese-speech.wav
```

Then explicitly select the `live` marker:

```powershell
.\.venv\Scripts\python -m pytest -m live -v -p no:cacheprovider
```

The test skips when either `.env` setting is absent. A regular `python -m pytest` run always skips tests marked `live`, even when both values are configured.

Phase 4 creates the following local outputs for one meeting:

```text
output/<meeting-id>/
├─ transcript.json
├─ transcript.md
├─ metadata.json
└─ meeting-minutes.md
```

- `transcript.json` is the Canonical Primary Derived Evidence and source for downstream analysis.
- `transcript.md` is a human-readable projection that does not correct or supplement the canonical transcript.
- `metadata.json` records completed processing context, source traceability, and artifact hashes.
- `meeting-minutes.md` is the structured, human-readable account of the entire meeting. It is created once after Evidence validation and is never silently overwritten.

The output directory must not already exist. Phase 4 never silently overwrites or edits a completed transcript record. All three files are prepared in a temporary sibling directory and the meeting directory is finalized only after the complete artifact set is ready. The original MP4 is not copied or modified; its absolute source path and SHA-256 hash are retained in metadata.

```text
Original MP4
  → transcript.json (Canonical Primary Derived Evidence)
  → transcript.md (human-readable projection)
  → meeting-minutes.md (human-readable detailed minutes)
  → future meeting.json (AI interpretation)
  → Google Sheets (operational index and management projection)
```

Downstream meeting analysis must read but never rewrite `transcript.json` or `transcript.md`.

## Meeting analysis and Google Sheets

The default analysis model is `gpt-5.6-terra` with `low` reasoning effort. It returns a provider-independent structured result whose topics, decisions, action items, open items, and relationship-profile values reference canonical transcript segment IDs. The application rejects unknown or missing Evidence before any spreadsheet write. Phase 5 does not persist `meeting.json` and does not retain raw Provider responses.

Phase 7 separates the operational projection into four non-overlapping views:

- `Meetings`: one row per meeting with relationship fields, a 3–5 line `ショート要約`, a `議事録` reference/path, and concise `主要論点`. The reference remains abstract so a future Google Drive URL can replace the local path without changing projection semantics.
- `Decisions`: decision details only.
- `Action Items`: executable task details only.
- `Open Items`: unresolved and confirmation items only.

Initialize or safely migrate empty formal sheets with `meeting-process init-sheets`. If any sheet has data rows and its header differs, initialization fails without rewriting it. Resume remains `meeting-process analyze "output\<meeting-id>\transcript.json"`; analysis failure never requires retranscription.

Formal headers are:

```text
Meetings: ミーティングID, 日時, タイトル, お相手の名前, 紹介者名, その人のビジネス, ショート要約, 議事録, 主要論点, 具体的にギブしてくれる内容, ギブできる（こちらが紹介できる）人, 元動画, 文字起こし, 処理日時
Decisions: ミーティングID, 決定事項, ステータス, Confidence, Review Required, Evidence
Action Items: ミーティングID, アクション, 担当者, 期限, ステータス, Confidence, Review Required, Evidence
Open Items: ミーティングID, 未決・確認事項, 理由, Confidence, Review Required, Evidence
```

The analysis prompt presents each segment as an explicit `[segment_id]`, speaker, timestamp, and text block. The model may use only IDs explicitly present in that input. `MI_ANALYSIS_EVIDENCE_MAX_ATTEMPTS` defaults to `2` and is capped at two total attempts.

Configure local-only credentials and the target spreadsheet in the ignored Repository-root `.env` file:

```text
OPENAI_API_KEY=
GOOGLE_SERVICE_ACCOUNT_FILE=C:\path\to\service-account.json
GOOGLE_SHEETS_SPREADSHEET_ID=
MI_ANALYSIS_MODEL=gpt-5.6-terra
MI_ANALYSIS_REASONING_EFFORT=low
```

To set up Google Sheets:

1. Create a Google Cloud project and enable the Google Sheets API.
2. Create a service account and save its JSON credential outside the Repository.
3. Create the target spreadsheet.
4. Share that spreadsheet with the service-account email as an editor.
5. Put the credential path and spreadsheet ID in `.env` as shown above.

The integration creates or validates `Meetings`, `Decisions`, `Action Items`, and `Open Items` tabs. A meeting already present in `Meetings` produces no writes. Data rows are sent in one atomic `spreadsheets.batchUpdate`, with every value written as a string to prevent formula injection. Keep service-account JSON outside the Repository; matching filenames are ignored as an additional safeguard.

The Google Sheets live acceptance test writes a uniquely identified row set to the spreadsheet configured in `.env`, reads it back, and leaves it in place. Use a dedicated test spreadsheet. Select only this live test with:

```powershell
.\.venv\Scripts\python -m pytest -m "live and google_sheets_live" -v -rs -p no:cacheprovider
```

Regular pytest runs force-skip it even when credentials are configured.

## Documentation

- [Documentation index](docs/README.md)
- [Purpose and scope](docs/design/PURPOSE_AND_SCOPE.md)
- [Architecture](docs/design/ARCHITECTURE.md)
- [Processing pipeline](docs/design/PROCESSING_PIPELINE.md)
- [Data model](docs/design/DATA_MODEL.md)
- [Quality and safety](docs/design/QUALITY_AND_SAFETY.md)
- [ADR-0001: OpenAI-first Provider Strategy](docs/adr/ADR-0001-openai-first-provider-strategy.md)

## Current boundary

Meeting Intelligence is independent of Luvira OS. It is designed so that it may later become a Luvira OS capability, but it has no Luvira OS runtime dependency. A confirmed meeting `Decision` is only a future decision candidate, not a Luvira OS `Approved Decision`. Likewise, an `Action Item` is only a future task candidate, not a Luvira OS `Managed Task`.
