# Repository Instructions for Codex

## Scope

Follow the approved and documented Meeting Intelligence design. During the current documentation phase, do not implement application code, tests, packaging, dependencies, schemas, runtime integrations, CI/CD, Docker, a Web UI, a database, or cloud storage.

## Core rules

1. Approved and documented design is the source of truth.
2. Do not introduce major architecture changes without updating and reviewing the design first.
3. Do not introduce unnecessary dependencies.
4. Do not add a Web UI, database, cloud storage, or additional AI providers unless explicitly approved.
5. Core Domain code must not depend directly on the OpenAI SDK.
6. AI-extracted facts must not invent missing information; represent unknown values as `null`.
7. Preserve Evidence traceability from extracted items to Transcript Segments, timestamps, and the original recording.
8. `meeting.json` is canonical; Markdown is a human-readable projection.
9. Meeting Intelligence Decisions are not automatically Luvira OS Approved Decisions.
10. Meeting Intelligence Action Items are not automatically Luvira OS Managed Tasks.
11. Prefer a simple MVP implementation over speculative abstractions.
12. Never commit secrets or API keys, and never expose them in logs.

## Architecture constraints

- Keep dependency direction aligned with `CLI → Application → Domain Interfaces`, with Infrastructure and Provider Adapters implementing inward-facing interfaces.
- The Domain layer must not depend on the OpenAI SDK, ffmpeg implementation details, or a CLI framework.
- Keep Provider limits and model names in configuration and runtime metadata, not fixed as Core Domain rules or schema constants.
- Treat the Canonical Meeting Record as a historical, immutable record of processing time.
- Do not silently treat partial pipeline failure as successful completion.

