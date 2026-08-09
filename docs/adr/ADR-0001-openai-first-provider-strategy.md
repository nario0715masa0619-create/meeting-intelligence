# ADR-0001: OpenAI-first Provider Strategy

- **Status:** Accepted
- **Decision scope:** MVP transcription, meeting analysis, and structured output

## Context

Meeting Intelligence must transcribe Japanese meeting recordings, analyze meeting content, and generate a schema-conforming Canonical Meeting Record. The MVP needs a focused implementation path while keeping the Core Domain suitable for future integration as a Luvira OS capability.

The project currently needs only one Provider implementation. Adding multiple implementations during the MVP would expand scope and validation cost. At the same time, direct coupling between domain models and a vendor SDK would make future evolution and testing unnecessarily difficult.

## Decision

Use OpenAI as the MVP AI Provider for:

- Speech-to-Text transcription;
- meeting analysis; and
- JSON Schema-based structured output.

Define conceptual Domain Interfaces for `TranscriptionProvider` and `AnalysisProvider`. Implement them in the future through `OpenAITranscriptionProvider` and `OpenAIAnalysisProvider` Adapters. The Core Domain must not import or expose OpenAI SDK types, specific API payloads, or fixed model names.

Provider limits are configuration or Adapter concerns. The concrete Provider and model values used for a run are stored in processing metadata. Only the OpenAI Adapters are in MVP scope; this separation does not authorize implementation of additional Providers.

## Consequences

### Positive

- The MVP has one coherent Provider path for transcription, analysis, and structured output.
- Core models, validation rules, Evidence policy, and pipeline orchestration remain independent of the OpenAI SDK.
- Runtime Provider and model metadata preserve traceability without freezing model names into schemas.
- Future Provider replacement or Luvira OS integration can occur at the Adapter boundary.

### Negative and trade-offs

- The MVP depends operationally on OpenAI API availability, credentials, pricing, limits, and data handling.
- Adapter-level error mapping, retry behavior, and configuration will be required.
- The abstraction must remain minimal because only one implementation validates it during the MVP.

## Alternatives considered

### Local Whisper

Local Whisper could reduce cloud dependency and keep audio processing local, but it adds local model distribution, hardware variability, performance tuning, and operational complexity. It is not selected for the MVP.

### Multiple Providers such as Claude or Gemini

Supporting multiple Providers could improve portability, but it would expand configuration, integration, testing, capability normalization, and quality-comparison scope before the core product is validated. It is deferred.

### Direct OpenAI dependency without Provider abstraction

Calling the OpenAI SDK directly from Core Domain or application rules would be simpler initially, but it would violate the dependency rule, entangle canonical models with vendor payloads, and make future replacement or testing harder. This alternative is rejected.
