# Purpose and Scope

## Purpose

Meeting Intelligence converts information produced in a meeting into structured knowledge usable by downstream systems. Its purpose is not merely to write polished minutes.

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

The Canonical Meeting Record is `meeting.json`. Markdown is a human-readable projection and is not the source of truth.

## MVP input and operation

- MP4 files, primarily recordings made with Windows Game Bar
- Japanese-language meetings
- One file equals one meeting
- Batch processing after recording has ended
- Final one-command UX goal: `meeting-process <video-file>`

Real-time meeting assistance is outside the MVP.

## MVP outputs

For each meeting, the target output is:

```text
output/<meeting-id>/
├─ meeting.json
├─ meeting.md
├─ transcript.json
├─ transcript.md
└─ metadata.json
```

- `meeting.json`: Canonical Meeting Record
- `meeting.md`: human-readable meeting record
- `transcript.json`: Canonical Transcript Record
- `transcript.md`: human-readable transcript
- `metadata.json`: processing metadata

The original MP4 must not be copied into the output directory. The original source path and SHA-256 hash are retained in metadata.

## Goals

### G-01 Automatic Transcription

Extract Japanese audio from an MP4 and produce a complete transcript.

### G-02 Meeting Summary

Summarize the meeting purpose, main discussion, conclusions, and important supplementary context.

### G-03 Decision Extraction

Distinguish `confirmed`, `proposed`, and `uncertain` Decisions. Inference alone must never promote a Decision to `confirmed`.

### G-04 Evidence Preservation

Make each Decision, Action Item, and Open Item traceable to one or more Transcript Segments where applicable.

### G-05 Action Item Extraction

Represent at least task, owner, due date, Evidence, and confidence. Never invent an owner or due date that was not stated.

### G-06 Open Item Extraction

Identify pending decisions, required investigation, missing information, pending approval, unresolved opinions, and follow-up needs.

### G-07 Structured Output

Generate machine-readable JSON in addition to Markdown projections.

### G-08 One-command Operation

Target a single command: `meeting-process <video-file>`.

### G-09 Reproducibility and Traceability

Track application, schema, and prompt versions plus transcription and analysis Provider/model values used at runtime.

### G-10 Future Luvira OS Integration

Keep the Core Domain independent of a specific AI Provider and the Luvira OS runtime.

## Non-goals

The MVP does not include:

- Real-time meeting assistance
- Recording functionality
- Complete speaker identification
- Calendar integration
- Automatic task registration in GitHub, Notion, Jira, or similar systems
- Automatic updates to repository specifications
- Autonomous AI decision-making
- A guarantee of 100% transcript accuracy
- Web UI
- Database
- Cloud storage
- Multiple Provider implementations

## Luvira OS boundaries

Meeting Intelligence is currently standalone because Luvira OS is not complete. No Luvira OS runtime dependency may be introduced at this stage.

Meeting Intelligence and Luvira OS have distinct governance meanings:

```text
Confirmed Meeting Decision
        ↓
Decision Candidate
        ↓
Human / Governance Approval
        ↓
Luvira OS Approved Decision
```

A confirmed Decision must not be emitted directly as an Approved Decision.

```text
Meeting Action Item
        ↓
Task Candidate
        ↓
Human / Policy Validation
        ↓
Luvira OS Managed Task
```

Meeting Intelligence does not own the Managed Task lifecycle.

