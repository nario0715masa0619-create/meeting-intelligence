# Architecture

## System context

Meeting Intelligence is a standalone Python application that transforms a completed MP4 meeting recording into a validated Canonical Transcript Record, a validated Canonical Meeting Record, and human-readable projections.

```text
Windows Game Bar
        ↓
MP4
        ↓
CLI
        ↓
Application Layer
        ↓
Media Layer
        ↓
TranscriptionProvider
        ↓
Transcript
        ↓
Validated immutable transcript.json
        ↓
AnalysisProvider
        ↓
Structured Analysis
        ↓
Validation
        ↓
meeting.json
        ↓
meeting.md
```

The MVP runtime technology direction is Python, ffmpeg, the OpenAI Python SDK, and the OpenAI API. Transcription uses OpenAI Speech-to-Text and analysis uses the OpenAI API. Structured extraction is designed for JSON Schema-based structured output. These choices belong to adapters and infrastructure; the Core Domain remains independent.

## Layers and responsibilities

- **CLI:** accepts the video path, initiates processing, and returns explicit outcome information.
- **Application:** orchestrates the use case and pipeline without containing Provider-specific logic.
- **Domain:** defines the canonical models, invariants, policies, and Provider-facing interfaces.
- **Media:** validates MP4 media and performs audio extraction, compression, and chunking through ffmpeg infrastructure.
- **Transcription:** coordinates transcription and normalization into the Canonical Transcript Record.
- **Analysis:** converts Transcript Segments into summaries, Topics, Decisions, Action Items, and Open Items.
- **Validation:** enforces schema, Evidence, null, collection, and quality rules.
- **Output:** writes canonical JSON and derives Markdown projections.
- **Configuration:** supplies runtime settings, Provider limits, selected model names, versions, and credentials references.
- **Provider Adapter:** implements Domain Interfaces for an external Provider.

## Dependency rule

```text
CLI
 ↓
Application
 ↓
Domain Interfaces
 ↑
Infrastructure / Provider Implementations
```

Dependencies point inward toward Domain Interfaces. The Domain layer must not depend on:

- the OpenAI SDK;
- ffmpeg implementation details; or
- a CLI framework.

The Application layer composes domain behavior with interface implementations. Infrastructure and Provider Adapters may depend on external SDKs while implementing inward-facing interfaces.

## Provider architecture

```text
Meeting Intelligence Core
        ↓
Domain Interfaces
        ↓
Provider Adapters
        ↓
OpenAI
```

The minimum conceptual interfaces and MVP implementations are:

```text
TranscriptionProvider
└─ OpenAITranscriptionProvider

AnalysisProvider
└─ OpenAIAnalysisProvider
```

Only OpenAI Adapters are planned for the MVP. Additional Providers are future extensions, not MVP work. API file-size limits and other Provider constraints are configuration or Provider concerns and must not be fixed as Core Domain rules. Concrete model names are runtime metadata rather than schema constants.

## Codex boundary

Codex is a development agent, not part of the Meeting Intelligence runtime.

Codex responsibilities may include repository understanding, source implementation, tests, refactoring, documentation, and review support. The production runtime consists of the Python application, ffmpeg, and OpenAI API integration. Runtime correctness must not depend on Codex.

## Target repository structure

The following is the intended future structure. Directories and files beyond the current documentation phase are shown as design targets only.

```text
meeting-intelligence/
├─ AGENTS.md
├─ README.md
├─ pyproject.toml
├─ .gitignore
├─ .env.example
├─ docs/
│  ├─ README.md
│  ├─ design/
│  │  ├─ PURPOSE_AND_SCOPE.md
│  │  ├─ ARCHITECTURE.md
│  │  ├─ PROCESSING_PIPELINE.md
│  │  ├─ DATA_MODEL.md
│  │  └─ QUALITY_AND_SAFETY.md
│  └─ adr/
│     └─ ADR-0001-openai-first-provider-strategy.md
├─ src/
│  └─ meeting_intelligence/
│     ├─ cli/
│     ├─ application/
│     ├─ domain/
│     ├─ media/
│     ├─ transcription/
│     ├─ analysis/
│     ├─ validation/
│     ├─ output/
│     ├─ schemas/
│     └─ config/
├─ tests/
│  ├─ unit/
│  ├─ integration/
│  └─ fixtures/
├─ input/
├─ output/
└─ .work/
```

## Architectural boundaries

- `meeting.json` is a historical Canonical Meeting Record and is not rewritten to reflect later downstream task or governance state.
- `transcript.json` is immutable Canonical Primary Derived Evidence; analysis reads it but never rewrites it.
- Markdown is derived from canonical JSON, never the reverse.
- The original recording stays at its source path and is not copied to the output directory.
- Meeting Intelligence remains independent of the Luvira OS runtime.
- A Meeting Intelligence Decision is not a Luvira OS Approved Decision.
- An Action Item is not a Luvira OS Managed Task.
