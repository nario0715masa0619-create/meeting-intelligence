# Meeting Intelligence documentation

This documentation set defines Design v0.1 for Meeting Intelligence. Together, these documents are the approved basis for future implementation.

## Design documents

| Document | Responsibility |
| --- | --- |
| [Purpose and scope](design/PURPOSE_AND_SCOPE.md) | Product purpose, goals, MVP boundaries, and Luvira OS boundaries |
| [Architecture](design/ARCHITECTURE.md) | Layers, dependency rules, Provider architecture, Codex boundary, and target repository structure |
| [Processing pipeline](design/PROCESSING_PIPELINE.md) | Ordered batch stages, audio handling, processing states, failures, and retries |
| [Data model](design/DATA_MODEL.md) | Canonical Transcript Record, Canonical Meeting Record, Evidence, null, collections, and metadata |
| [Quality and safety](design/QUALITY_AND_SAFETY.md) | Validation, confidence, human review, security, privacy, and immutable history |

## Architecture decisions

- [ADR-0001: OpenAI-first Provider Strategy](adr/ADR-0001-openai-first-provider-strategy.md) — Accepted

## Reading order

Start with purpose and scope, then architecture and pipeline. Read the data model before implementing schemas or extraction prompts, and apply quality and safety requirements throughout. ADRs explain why selected architectural choices were made.

## Source-of-truth hierarchy

The approved design documentation governs implementation. At runtime, `transcript.json` is the Canonical Primary Derived Evidence; `meeting.json` is the later Canonical Meeting Record for structured analysis. Markdown output is a human-readable projection and must not become a source of truth.
