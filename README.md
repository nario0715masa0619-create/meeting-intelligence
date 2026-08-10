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

`meeting.json` is the Canonical Meeting Record and source of truth. Markdown files are human-readable projections, not canonical data.

## Implementation status

Implementation Phase 3 adds an OpenAI Transcriptions API Adapter that converts Prepared Audio into a Canonical Transcript Record. Meeting analysis and full end-to-end CLI processing remain unimplemented.

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

The planned local outputs are:

```text
output/<meeting-id>/
├─ meeting.json
├─ meeting.md
├─ transcript.json
├─ transcript.md
└─ metadata.json
```

The original MP4 is not copied into the output directory. Its source path and SHA-256 hash are retained as metadata.

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
