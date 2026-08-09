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

Implementation Phase 1 provides the Python project foundation, canonical Pydantic models, schema validation, Provider interfaces, configuration foundation, CLI skeleton, and unit tests. It does not process recordings or call OpenAI or ffmpeg.

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
