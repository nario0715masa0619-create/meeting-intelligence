# Data Model

## Canonical data philosophy

`meeting.json` is the Canonical Meeting Record. `transcript.json` is the Canonical Transcript Record. `meeting.md` and `transcript.md` are human-readable projections and must not be treated as sources of truth.

The Canonical Meeting Record schema version for Design v0.1 is `0.1.0`.

## Canonical Transcript Record

A transcript must not be stored only as one large string. Its conceptual structure is:

```text
Transcript
├─ language
├─ duration_seconds
└─ segments[]
   ├─ id
   ├─ start
   ├─ end
   ├─ speaker
   └─ text
```

`speaker` may be `null` in the MVP.

```json
{
  "id": "seg_0042",
  "start": 132.4,
  "end": 139.8,
  "speaker": null,
  "text": "ではこの方式で進めましょう"
}
```

Transcript Segment IDs are stable canonical Evidence references within the meeting output.

## Canonical Meeting Record

Required top-level shape:

```json
{
  "schema_version": "0.1.0",
  "meeting": {},
  "summary": {},
  "topics": [],
  "decisions": [],
  "action_items": [],
  "open_items": [],
  "processing": {},
  "quality": {}
}
```

### Meeting

The `meeting` object contains:

- `id`
- `title`
- `source`
- `language`
- `started_at`
- `duration_seconds`
- `participants`

The `source` object contains:

- `file_name`
- `file_path`
- `sha256`

Values that cannot be obtained must be `null`; AI must not infer them. The source path and SHA-256 link the record to the original MP4 without copying it into output.

### Summary

The `summary` object contains:

- `overview`
- `key_points[]`

Summary supports human understanding. It is not the source of truth for Decisions.

### Topic

Each Topic contains:

- `id`
- `title`
- `summary`
- `evidence_segment_ids[]`

### Decision

Each Decision contains:

- `id`
- `statement`
- `status`
- `evidence_segment_ids[]`
- `confidence`
- `review_required`

Allowed status values are:

- `confirmed`
- `proposed`
- `uncertain`

A `confirmed` Decision requires, as a rule, at least one Evidence reference. A Decision must never be marked `confirmed` from inference alone or without Evidence.

### Action Item

Each Action Item contains:

- `id`
- `task`
- `owner`
- `due_date`
- `status`
- `evidence_segment_ids[]`
- `confidence`
- `review_required`

The only MVP status is `open`. Meeting Intelligence does not own a task lifecycle.

An owner is a structured reference, not an untyped string:

```json
{
  "type": "named",
  "value": "田中"
}
```

or:

```json
{
  "type": "speaker",
  "value": "speaker_2"
}
```

An unknown owner is `null`. AI must not infer an owner. A due date is set only when explicitly stated and safely interpretable; otherwise it is `null`. Ambiguous dates must not be forced into a normalized value.

### Open Item

Each Open Item contains:

- `id`
- `statement`
- `reason`
- `evidence_segment_ids[]`
- `confidence`
- `review_required`

Allowed reason values are:

- `decision_pending`
- `investigation_required`
- `information_missing`
- `approval_required`
- `opinion_unresolved`
- `follow_up_required`
- `other`

## Evidence architecture

Transcript Segment ID is the canonical Evidence reference.

```text
Decision / Action Item / Open Item
        ↓
Transcript Segment
        ↓
Timestamp
        ↓
Original MP4
```

Example:

```json
{
  "statement": "認証方式はOAuth 2.0を採用する",
  "status": "confirmed",
  "evidence_segment_ids": ["seg_0042"]
}
```

Every referenced segment ID must exist in the Canonical Transcript Record.

## Confidence and review

Confidence is in the inclusive range `0.0` to `1.0`.

| Range | Label |
| --- | --- |
| `>= 0.85` | High |
| `0.60`–`0.849` | Medium |
| `< 0.60` | Low |

Confidence is supporting information, not the sole test of truth. Low-confidence items must not be silently deleted. `review_required` is set to `true` when human review may be needed, including low confidence, insufficient or conflicting Evidence, or an ambiguous Decision, owner, or due date.

## Null and collection policies

Unknown data is represented by JSON `null`, not placeholder strings such as `"不明"`. This preserves the difference between missing data and literal text.

Collections are always present. An absent set of Decisions is represented as:

```json
{
  "decisions": []
}
```

The field must not be omitted.

## Processing metadata

Processing metadata records at least:

- `processed_at`
- `application_version`
- `schema_version`
- `prompt_version`
- `transcription.provider`
- `transcription.model`
- `analysis.provider`
- `analysis.model`

Provider and model values are the actual runtime values. Model names are not fixed into the schema.

## Quality

The `quality` object conceptually contains:

```json
{
  "status": "pass",
  "warnings": [],
  "review_required": false
}
```

Allowed status values are `pass`, `pass_with_warnings`, and `failed`. Each warning carries a machine-readable code.
