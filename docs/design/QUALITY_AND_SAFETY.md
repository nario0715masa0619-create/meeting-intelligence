# Quality and Safety

## Quality principles

Meeting Intelligence favors traceable, explicit records over polished but unsupported prose. Validation must protect canonical structure, Evidence, and unknown values. Confidence assists review but cannot replace factual support.

## Validation requirements

Before a Canonical Meeting Record is considered complete, validation must confirm:

- top-level schema version `0.1.0` and required objects and collections;
- required collections are present even when empty;
- unknown values use `null`, not invented placeholders;
- confidence values remain within `0.0` to `1.0`;
- enum values are allowed by the design;
- every Evidence reference resolves to an existing Transcript Segment;
- Transcript Segment timestamps are coherent;
- a `confirmed` Decision has at least one Evidence reference;
- an owner or due date was not inferred from unstated information; and
- canonical JSON is valid before Markdown projection.

## Evidence preservation

The canonical trace is:

```text
Decision / Action Item / Open Item
        ↓
Transcript Segment
        ↓
Timestamp
        ↓
Original MP4
```

Transcript normalization may reconcile chunks, timestamps, whitespace, and clear duplicates. It must not alter, supplement, or beautify speech in a way that changes Evidence.

## Confidence and human review

Initial confidence labels are:

- High: `>= 0.85`
- Medium: `0.60` through `0.849`
- Low: `< 0.60`

Low-confidence items remain in the record and normally require review. `review_required` is also `true` when Evidence is missing or contradictory, or when a Decision, owner, or due date is ambiguous. Confidence alone must not determine whether a statement is factual.

## Quality object and warnings

Quality status is one of:

- `pass`
- `pass_with_warnings`
- `failed`

Warnings have machine-readable codes so downstream systems can respond without parsing prose. The overall `quality.review_required` flag indicates whether any record-level condition needs human review.

## Explicit failure

The system must **Fail Explicitly**. It must never present a partial result as a completed Canonical Meeting Record. If transcription succeeds and analysis fails, the Canonical Transcript Record may be retained, but the meeting-processing result is failed and no incomplete `meeting.json` may be treated as complete.

Failures contain `error_code`, `stage`, `message`, and `retryable`. Retry is bounded and limited to temporary API, rate-limit, or network conditions. Invalid input, missing credentials, unsupported files, and invalid configuration are not retried.

## Security and privacy

- Never store an API key in the repository.
- Never write an API key to logs.
- Do not emit full transcripts casually in debug logs.
- Do not copy the source recording into the output directory.
- Make temporary audio and workspaces cleanable.
- Keep MVP output local.
- Cloud upload is outside the MVP.
- `.env` is intended to be ignored by Git.
- A future `.env.example` may document variable names but must contain no secret values.

## Historical record principle

`meeting.json` is a historical, immutable record of the meeting-processing result at processing time. Future downstream changes must not rewrite it. Application, schema, prompt, Provider, and model metadata make the result reproducible and traceable.

## Luvira OS governance boundary

A `confirmed` Meeting Intelligence Decision is not a Luvira OS Approved Decision. It may become a Decision Candidate for human or governance approval. Meeting Intelligence must not generate an Approved Decision directly.

An Action Item is not a Luvira OS Managed Task. It may become a Task Candidate for human or policy validation. Meeting Intelligence does not own the Managed Task lifecycle.

## Operational safety

- Preserve the original source file and record its path and SHA-256.
- Avoid infinite retries.
- Keep Provider limits configurable rather than embedding them as Domain rules.
- Do not silently discard low-confidence extracted items.
- Do not introduce cloud storage, a database, a Web UI, or additional Providers without an approved scope change.
