# Processing Pipeline

## Batch pipeline

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
| 7 | Meeting Analysis | Analyze the Canonical Transcript Record through `AnalysisProvider`. |
| 8 | Structured Extraction | Produce summaries, Topics, Decisions, Action Items, and Open Items. |
| 9 | Validation | Validate schema, invariants, Evidence references, quality, and unknown-value handling. |
| 10 | Canonical Record Generation | Write the completed `meeting.json` and associated canonical records. |
| 11 | Markdown Projection | Derive `meeting.md` and `transcript.md` from canonical data. |
| 12 | Finalize / Cleanup | Finalize metadata and safely clean temporary audio and workspace artifacts. |

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

## Processing states

The processing lifecycle uses these conceptual states:

```text
pending
validating
extracting_audio
transcribing
analyzing
validating_output
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

On successful completion, write all required collections even when empty and use `null` for unknown scalar or object values. Validate canonical JSON before generating Markdown projections. Temporary audio must be cleanable, while the original source recording remains untouched and un-copied.
