# Processing Pipeline

## Batch pipeline

Phase 5 begins only after canonical `transcript.json` exists. It loads that record without mutation, requests schema-constrained Meeting Understanding, validates every required Evidence reference against transcript segment IDs, then projects the validated result to Google Sheets. Schema verification and duplicate detection precede data writes; child rows and the `Meetings` marker are appended in one atomic batch, with the marker request last.

Phase 6 exposes this sequence through `meeting-process <MP4>`. The CLI is only the composition root: media, transcription, persistence, analysis, validation, and Sheets behavior remain in their existing Application and Adapter boundaries. Transcript artifacts are finalized before analysis and Sheets projection so a downstream failure cannot destroy Primary Evidence; such a failure still produces a nonzero command result and is not reported as full pipeline success.

One MP4 file is processed as one meeting after recording has ended.

| Stage | Name | Responsibility |
| --- | --- | --- |
| 0 | Input | Receive the source MP4 path. |
| 1 | Input Validation | Verify the file exists, is supported, and can be processed. |
| 2 | Workspace Creation | Create an isolated temporary workspace without copying the source into final output. |
| 3 | Audio Extraction | Extract audio using the Media layer and ffmpeg infrastructure. |
| 4 | Audio Preparation | Compress or chunk audio when required by configured Provider constraints. |
| 5 | Transcription | Submit prepared audio through `TranscriptionProvider`. |
| 6 | Transcript Normalization | Merge chunks and normalize segments without changing Evidence meaning. |
| 7 | Transcript Validation | Validate the Canonical Transcript Record before persistence. |
| 8 | Primary Transcript Persistence | Atomically finalize immutable `transcript.json`, its `transcript.md` projection, and completed `metadata.json`. |
| 9 | Meeting Analysis | Analyze the persisted Canonical Transcript Record through `AnalysisProvider`. |
| 10 | Structured Extraction | Produce summaries, Topics, Decisions, Action Items, and Open Items. |
| 11 | Meeting Validation | Validate schema, invariants, Evidence references, quality, and unknown-value handling. |
| 12 | Canonical Meeting Generation | Write the completed `meeting.json`. |
| 13 | Meeting Markdown Projection | Derive `meeting.md` from canonical data. |
| 14 | Finalize / Cleanup | Finalize processing and safely clean temporary audio and workspace artifacts. |

Stage completion must be explicit. A later-stage failure must not retroactively label the overall run as completed.

## Media and audio preparation

The Media layer is responsible for:

- MP4 validation;
- audio extraction;
- compression; and
- chunking.

Chunking supports Provider file-size or duration constraints. Exact limits are configuration and Provider concerns, not Domain rules. Each chunk should retain, where possible:

- `chunk_id`;
- `start_time`; and
- `end_time`.

These values support deterministic segment reconciliation and Evidence timestamps across chunk boundaries.

## Transcript normalization

Allowed normalization operations are:

- joining chunk results;
- reconciling timestamps;
- whitespace cleanup; and
- removing clearly duplicated segments.

Normalization must not:

- change what a participant said;
- fill in missing speech;
- add meaning; or
- beautify wording in a way that changes Evidence.

The transcript is Evidence, not editable narrative prose.

## Primary transcript persistence

After normalization, `transcript.json` is validated and persisted as the Canonical Primary Derived Evidence. `transcript.md` is derived only from that record, and `metadata.json` links both artifacts to the original MP4 and the actual runtime Provider configuration. A completed primary transcript record is immutable: downstream analysis, summarization, grammar correction, speaker naming, and reprocessing must not rewrite it.

For the MVP, `output/<meeting-id>/` must not already exist. The complete three-file artifact set is written to a temporary sibling directory and finalized by an atomic directory rename. A write failure must not create a completed meeting directory or completed metadata. Reprocessing run versioning is deferred.

## Processing states

The processing lifecycle uses these conceptual states:

```text
pending
validating
extracting_audio
transcribing
analyzing
validating_output
writing_output
completed
failed
```

State names are stable concepts; implementation may map internal sub-stages to them while preserving explicit progress and failure reporting.

## Failure model

Failures carry at least:

```text
error_code
stage
message
retryable
```

The governing principle is **Fail Explicitly**. Partial failure must not be reported as successful completion. For example, if transcription succeeds and analysis fails, the transcript may be preserved, but `meeting.json` must not be represented as a valid completed Canonical Meeting Record.

## Retry policy

Bounded retries may apply to:

- temporary API errors;
- rate limits; and
- temporary network failures.

Retries do not apply to:

- invalid input;
- a missing API key;
- an unsupported file; or
- invalid configuration.

Infinite retry is prohibited. Retry decisions must be stage-aware, bounded, and reflected in processing metadata or failure reporting as appropriate.

## Output finalization

On successful transcript persistence, `transcript.json`, `transcript.md`, and `metadata.json` must all exist before the primary output is reported as completed. Write all required collections even when empty and use `null` for unknown scalar or object values. Validate canonical JSON before generating Markdown projections. Temporary audio must be cleanable, while the original source recording remains untouched and un-copied.
