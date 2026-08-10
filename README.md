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

`transcript.json` is the Canonical Primary Derived Evidence. The future `meeting.json` is the Canonical Meeting Record for structured analysis, not a replacement for or correction of the primary transcript. Markdown files are human-readable projections, not canonical data.

## Implementation status

Implementation Phase 5 reads the immutable Canonical Transcript Record, produces validated structured Meeting Understanding through the OpenAI Responses API, and projects operational rows to Google Sheets. Full end-to-end CLI processing remains unimplemented.

The final MVP UX goal is:

```text
meeting-process <video-file>
```

In Phase 1, only help and version behavior are implemented:

```powershell
meeting-process --help
meeting-process --version
```

Running the command without an option reports that the processing pipeline is not yet implemented.

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

## Media prerequisite

Install the system `ffmpeg` distribution so both `ffmpeg` and `ffprobe` are on PATH. Their executable paths can be overridden through `MI_FFMPEG_PATH` and `MI_FFPROBE_PATH`.

Phase 2 prepares mono 16 kHz MP3 audio at 64 kbit/s. Thresholds, encoding settings, executable paths, and subprocess timeout are configurable. Existing artifacts are never silently overwritten, and source MP4 files are preserved.

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
└─ metadata.json
```

- `transcript.json` is the Canonical Primary Derived Evidence and source for downstream analysis.
- `transcript.md` is a human-readable projection that does not correct or supplement the canonical transcript.
- `metadata.json` records completed processing context, source traceability, and artifact hashes.

The output directory must not already exist. Phase 4 never silently overwrites or edits a completed transcript record. All three files are prepared in a temporary sibling directory and the meeting directory is finalized only after the complete artifact set is ready. The original MP4 is not copied or modified; its absolute source path and SHA-256 hash are retained in metadata.

```text
Original MP4
  → transcript.json (Canonical Primary Derived Evidence)
  → transcript.md (human-readable projection)
  → future meeting.json (AI interpretation)
  → future meeting.md (human-readable projection)
```

Downstream meeting analysis must read but never rewrite `transcript.json` or `transcript.md`.

## Meeting analysis and Google Sheets

The default analysis model is `gpt-5.6-terra` with `low` reasoning effort. It returns a provider-independent structured result whose topics, decisions, action items, open items, and relationship-profile values reference canonical transcript segment IDs. The application rejects unknown or missing Evidence before any spreadsheet write. Phase 5 does not persist `meeting.json` and does not retain raw Provider responses.

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
