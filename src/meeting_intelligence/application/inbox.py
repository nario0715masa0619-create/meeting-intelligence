"""Safe sequential discovery and orchestration for an unattended MP4 inbox."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Callable, Iterator
import uuid

from meeting_intelligence.domain.errors import ConfigurationError, OutputWriteError
from meeting_intelligence.media.tools import sha256_file


class InboxState(StrEnum):
    NEW = "NEW"
    TRANSCRIPT_COMPLETE = "TRANSCRIPT_COMPLETE"
    ANALYSIS_COMPLETE = "ANALYSIS_COMPLETE"
    COMPLETE = "COMPLETE"
    FAILED_RESUMABLE = "FAILED_RESUMABLE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    path: Path
    relative_path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class InboxItem:
    source: SourceIdentity
    meeting_id: str
    state: InboxState
    output_directory: Path
    reason: str = ""


@dataclass(frozen=True, slots=True)
class InboxSummary:
    processed: int = 0
    resumed: int = 0
    skipped: int = 0
    failed: int = 0


def discover_mp4(inbox_root: Path) -> list[Path]:
    root = inbox_root.expanduser().resolve()
    if not root.is_dir():
        raise ConfigurationError("MI_INBOX_ROOT must identify an existing directory")
    return sorted(
        (path.resolve() for path in root.rglob("*") if path.is_file() and path.suffix.lower() == ".mp4"),
        key=lambda path: path.relative_to(root).as_posix().casefold(),
    )


def source_is_stable(path: Path, stable_age_seconds: float, *, now: float | None = None) -> tuple[bool, str]:
    try:
        stat = path.stat()
    except OSError:
        return False, "source is missing or unreadable"
    if stat.st_size == 0:
        return False, "source is zero bytes"
    current = datetime.now(timezone.utc).timestamp() if now is None else now
    if current - stat.st_mtime < stable_age_seconds:
        return False, "source is newer than the stability window"
    return True, ""


def identify_source(path: Path, inbox_root: Path) -> SourceIdentity:
    resolved = path.resolve()
    stat = resolved.stat()
    return SourceIdentity(resolved, resolved.relative_to(inbox_root.resolve()).as_posix(), stat.st_size, sha256_file(resolved))


def infer_meeting_id(relative_path: str, source_hash: str) -> str:
    stem = str(Path(relative_path).with_suffix("")).replace("\\", "-").replace("/", "-")
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-.") or "meeting"
    return slug[:96] if len(slug) <= 96 else f"{slug[:83]}-{source_hash[:12]}"


def _metadata_identity(directory: Path) -> tuple[str, str] | None:
    try:
        value = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
        return str(value.get("media", {}).get("source_path", "")), str(value.get("media", {}).get("source_sha256", ""))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def matching_outputs(source: SourceIdentity, output_root: Path) -> list[Path]:
    root = output_root.expanduser().resolve()
    if not root.is_dir():
        return []
    matches = []
    for metadata in root.glob("*/metadata.json"):
        identity = _metadata_identity(metadata.parent)
        if identity and identity[1] == source.sha256 and Path(identity[0]).resolve() == source.path:
            matches.append(metadata.parent)
    return matches


def find_output(source: SourceIdentity, output_root: Path) -> Path | None:
    matches = matching_outputs(source, output_root)
    if len(matches) == 1:
        return matches[0]
    completed = [directory for directory in matches if (directory / "meeting-minutes.md").is_file()]
    return completed[0] if len(completed) == 1 else None


def classify_item(
    source: SourceIdentity,
    output_root: Path,
    *,
    stable: bool = True,
    stability_reason: str = "",
    sheet_exists: bool | None = None,
    failed_marker: bool = False,
) -> InboxItem:
    inferred = infer_meeting_id(source.relative_path, source.sha256)
    if not stable:
        return InboxItem(source, inferred, InboxState.BLOCKED, output_root / inferred, stability_reason)
    matches = matching_outputs(source, output_root)
    directory = find_output(source, output_root)
    if directory is None:
        if matches:
            return InboxItem(source, inferred, InboxState.BLOCKED, output_root / inferred, "multiple outputs match this source without one unique completed result")
        candidate = output_root / inferred
        if candidate.exists():
            inferred = f"{inferred[:83]}-{source.sha256[:12]}"
            candidate = output_root / inferred
            if candidate.exists():
                return InboxItem(source, inferred, InboxState.BLOCKED, candidate, "meeting ID and hash suffix collide with a different or unverifiable source")
        return InboxItem(source, inferred, InboxState.NEW, candidate)
    required = [directory / name for name in ("transcript.json", "transcript.md", "metadata.json")]
    if not all(path.is_file() for path in required):
        return InboxItem(source, directory.name, InboxState.BLOCKED, directory, "canonical transcript artifact set is inconsistent")
    if not (directory / "meeting-minutes.md").is_file():
        state = InboxState.FAILED_RESUMABLE if failed_marker else InboxState.TRANSCRIPT_COMPLETE
        return InboxItem(source, directory.name, state, directory)
    if sheet_exists is True:
        return InboxItem(source, directory.name, InboxState.COMPLETE, directory)
    return InboxItem(source, directory.name, InboxState.ANALYSIS_COMPLETE, directory, "Google Sheets registration is not locally provable")


@contextmanager
def inbox_lock(work_root: Path) -> Iterator[None]:
    lock = work_root.expanduser().resolve() / "inbox.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ConfigurationError("another inbox runner holds the lock") from exc
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode())
        os.close(descriptor)
        yield
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass
        lock.unlink(missing_ok=True)


def _write_manifest(work_root: Path, payload: dict) -> Path:
    directory = work_root.resolve() / "inbox-runs"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{payload['run_id']}.json"
    temporary = directory / f".{payload['run_id']}.{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as stream:
            stream.write((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        temporary.rename(target)
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        raise OutputWriteError("failed to finalize inbox run manifest") from exc
    return target


def run_inbox(
    inbox_root: Path,
    output_root: Path,
    work_root: Path,
    *,
    stable_age_seconds: float,
    dry_run: bool,
    continue_on_failure: bool,
    process_new: Callable[[Path, str], None] | None = None,
    resume: Callable[[Path, str], None] | None = None,
    sheet_contains: Callable[[str], bool] | None = None,
    progress: Callable[[str], None] | None = None,
) -> InboxSummary:
    notify = progress or (lambda _: None)
    paths = discover_mp4(inbox_root)
    notify(f"Inbox scan: {len(paths)} MP4 files")
    summary = {"processed": 0, "resumed": 0, "skipped": 0, "failed": 0}
    records = []
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")

    def execute() -> None:
        for index, path in enumerate(paths, start=1):
            stable, reason = source_is_stable(path, stable_age_seconds)
            if not stable and path.exists() and path.stat().st_size:
                relative = path.resolve().relative_to(inbox_root.resolve()).as_posix()
                source = SourceIdentity(path.resolve(), relative, path.stat().st_size, "not-computed")
            elif not stable:
                relative = path.name
                source = SourceIdentity(path, relative, 0, "not-computed")
            else:
                source = identify_source(path, inbox_root)
            local_item = classify_item(source, output_root, stable=stable, stability_reason=reason)
            item = local_item
            if not dry_run and local_item.state is InboxState.ANALYSIS_COMPLETE and sheet_contains is not None:
                item = classify_item(source, output_root, sheet_exists=sheet_contains(local_item.meeting_id))
            notify(f"[{index}/{len(paths)}] {item.state.value} {item.source.relative_path} -> {item.meeting_id}")
            initial = item.state
            final = initial
            error = ""
            try:
                if dry_run:
                    summary["skipped"] += 1
                elif initial is InboxState.NEW:
                    if process_new is None:
                        raise ConfigurationError("new-meeting processor is not configured")
                    process_new(item.source.path, item.meeting_id)
                    summary["processed"] += 1
                    final = InboxState.COMPLETE
                elif initial in {InboxState.TRANSCRIPT_COMPLETE, InboxState.FAILED_RESUMABLE}:
                    if resume is None:
                        raise ConfigurationError("analysis-resume processor is not configured")
                    resume(item.output_directory / "transcript.json", item.meeting_id)
                    summary["resumed"] += 1
                    final = InboxState.COMPLETE
                elif initial is InboxState.ANALYSIS_COMPLETE:
                    summary["failed"] += 1
                    final = InboxState.BLOCKED
                    error = item.reason
                else:
                    summary["skipped"] += 1
            except Exception as exc:
                summary["failed"] += 1
                final = InboxState.FAILED_RESUMABLE if (item.output_directory / "transcript.json").is_file() else InboxState.BLOCKED
                error = f"{type(exc).__name__}: {str(exc)[:500]}"
                if not continue_on_failure:
                    records.append({"source_path": str(source.path), "meeting_id": item.meeting_id, "initial_state": initial.value, "final_state": final.value, "error": error})
                    break
            records.append({"source_path": str(source.path), "meeting_id": item.meeting_id, "initial_state": initial.value, "final_state": final.value, "error": error})

    if dry_run:
        execute()
    else:
        started = datetime.now(timezone.utc)
        with inbox_lock(work_root):
            execute()
            _write_manifest(work_root, {"run_id": run_id, "started_at": started.isoformat(), "completed_at": datetime.now(timezone.utc).isoformat(), "items": records})
    return InboxSummary(**summary)
