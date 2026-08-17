"""Safe sequential discovery and orchestration for an unattended MP4 inbox."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import json
import os
from pathlib import Path
import re
from typing import Callable, Iterator
import uuid

from meeting_intelligence.domain.errors import ConfigurationError, OutputWriteError
from meeting_intelligence.media.tools import sha256_file
from meeting_intelligence.media.models import MeetingSource, MeetingSourcePart


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
    source: MeetingSource | SourceIdentity
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


def discover_meeting_directories(inbox_root: Path) -> list[Path]:
    root = inbox_root.expanduser().resolve()
    paths = discover_mp4(root)
    return sorted({path.parent for path in paths}, key=lambda path: ("." if path == root else path.relative_to(root).as_posix()).casefold())


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


def identify_meeting_source(directory: Path, inbox_root: Path) -> MeetingSource:
    root = inbox_root.expanduser().resolve()
    resolved = directory.resolve()
    paths = sorted((path for path in resolved.iterdir() if path.is_file() and path.suffix.lower() == ".mp4"), key=lambda path: path.name.casefold())
    parts = [MeetingSourcePart(sequence=index, path=path.resolve(), relative_path=path.resolve().relative_to(root).as_posix(), size_bytes=path.stat().st_size, sha256=sha256_file(path)) for index, path in enumerate(paths, start=1)]
    relative_directory = "." if resolved == root else resolved.relative_to(root).as_posix()
    return MeetingSource.from_parts(resolved, relative_directory, parts)


def meeting_source_is_stable(directory: Path, stable_age_seconds: float, folder_stable_age_seconds: float, *, now: float | None = None) -> tuple[bool, str]:
    current = datetime.now(timezone.utc).timestamp() if now is None else now
    try:
        paths = [path for path in directory.iterdir() if path.is_file() and path.suffix.lower() == ".mp4"]
        if not paths:
            return False, "meeting folder has no MP4 files"
        if current - directory.stat().st_mtime < folder_stable_age_seconds:
            return False, "meeting folder is newer than the folder stability window"
    except OSError:
        return False, "meeting folder is missing or unreadable"
    for path in paths:
        stable, reason = source_is_stable(path, stable_age_seconds, now=current)
        if not stable:
            return False, f"{path.name}: {reason}"
    return True, ""


def infer_meeting_id(relative_path: str, source_hash: str) -> str:
    stem = str(Path(relative_path).with_suffix("")).replace("\\", "-").replace("/", "-")
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-.") or "meeting"
    return slug[:96] if len(slug) <= 96 else f"{slug[:83]}-{source_hash[:12]}"


def infer_source_meeting_id(source: MeetingSource | SourceIdentity) -> str:
    if isinstance(source, SourceIdentity):
        return infer_meeting_id(source.relative_path, source.sha256)
    basis = source.relative_directory
    if basis == "." and len(source.parts) == 1:
        basis = source.parts[0].relative_path
    elif basis == ".":
        basis = "inbox"
    slug = str(Path(basis).with_suffix("")) if len(source.parts) == 1 and basis.endswith(".mp4") else basis
    return infer_meeting_id(slug, source.composite_sha256)


def _metadata_identity(directory: Path) -> dict | None:
    try:
        value = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
        return value.get("media", {})
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _source_directory(source: MeetingSource | SourceIdentity) -> Path:
    return source.directory if isinstance(source, MeetingSource) else source.path.parent


def _source_hash(source: MeetingSource | SourceIdentity) -> str:
    return source.composite_sha256 if isinstance(source, MeetingSource) else source.sha256


def _metadata_matches(media: dict, source: MeetingSource | SourceIdentity) -> bool:
    if isinstance(source, MeetingSource) and "composite_sha256" in media:
        return media.get("composite_sha256") == source.composite_sha256 and Path(str(media.get("source_path", ""))).resolve() == source.directory
    if isinstance(source, MeetingSource) and len(source.parts) == 1:
        part = source.parts[0]
        return media.get("source_sha256") == part.sha256 and Path(str(media.get("source_path", ""))).resolve() == part.path
    if isinstance(source, SourceIdentity):
        return media.get("source_sha256") == source.sha256 and Path(str(media.get("source_path", ""))).resolve() == source.path
    return False


def matching_outputs(source: MeetingSource | SourceIdentity, output_root: Path) -> list[Path]:
    root = output_root.expanduser().resolve()
    if not root.is_dir():
        return []
    matches = []
    for metadata in root.glob("*/metadata.json"):
        identity = _metadata_identity(metadata.parent)
        if identity and _metadata_matches(identity, source):
            matches.append(metadata.parent)
    return matches


def changed_source_outputs(source: MeetingSource, output_root: Path) -> list[Path]:
    root = output_root.expanduser().resolve()
    if not root.is_dir():
        return []
    changed = []
    for metadata in root.glob("*/metadata.json"):
        media = _metadata_identity(metadata.parent)
        if not media or _metadata_matches(media, source):
            continue
        stored_path = Path(str(media.get("source_path", ""))).resolve()
        if stored_path == source.directory or stored_path.parent == source.directory:
            changed.append(metadata.parent)
    return changed


def find_output(source: MeetingSource | SourceIdentity, output_root: Path) -> Path | None:
    matches = matching_outputs(source, output_root)
    if len(matches) == 1:
        return matches[0]
    completed = [directory for directory in matches if (directory / "meeting-minutes.md").is_file()]
    return completed[0] if len(completed) == 1 else None


def classify_item(
    source: MeetingSource | SourceIdentity,
    output_root: Path,
    *,
    stable: bool = True,
    stability_reason: str = "",
    sheet_exists: bool | None = None,
    failed_marker: bool = False,
) -> InboxItem:
    inferred = infer_source_meeting_id(source)
    if not stable:
        return InboxItem(source, inferred, InboxState.BLOCKED, output_root / inferred, stability_reason)
    matches = matching_outputs(source, output_root)
    directory = find_output(source, output_root)
    if directory is None:
        if matches:
            return InboxItem(source, inferred, InboxState.BLOCKED, output_root / inferred, "multiple outputs match this source without one unique completed result")
        if isinstance(source, MeetingSource) and changed_source_outputs(source, output_root):
            return InboxItem(source, inferred, InboxState.BLOCKED, output_root / inferred, "meeting folder source parts changed after an earlier output")
        candidate = output_root / inferred
        if candidate.exists():
            inferred = f"{inferred[:83]}-{_source_hash(source)[:12]}"
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
    folder_stable_age_seconds: float | None = None,
    dry_run: bool,
    continue_on_failure: bool,
    process_new: Callable[[MeetingSource, str], None] | None = None,
    resume: Callable[[Path, str], None] | None = None,
    sheet_contains: Callable[[str], bool] | None = None,
    progress: Callable[[str], None] | None = None,
) -> InboxSummary:
    notify = progress or (lambda _: None)
    directories = discover_meeting_directories(inbox_root)
    notify(f"Inbox scan: {len(directories)} meeting sources")
    summary = {"processed": 0, "resumed": 0, "skipped": 0, "failed": 0}
    records = []
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")

    def execute() -> None:
        for index, directory in enumerate(directories, start=1):
            stable, reason = meeting_source_is_stable(directory, stable_age_seconds, folder_stable_age_seconds if folder_stable_age_seconds is not None else stable_age_seconds)
            if stable:
                source = identify_meeting_source(directory, inbox_root)
            else:
                root = inbox_root.resolve()
                paths = sorted((path for path in directory.iterdir() if path.is_file() and path.suffix.lower() == ".mp4"), key=lambda path: path.name.casefold())
                parts = [MeetingSourcePart(sequence=i, path=path.resolve(), relative_path=path.resolve().relative_to(root).as_posix(), size_bytes=max(path.stat().st_size, 1), sha256="0" * 64) for i, path in enumerate(paths, start=1)]
                relative_directory = "." if directory.resolve() == root else directory.resolve().relative_to(root).as_posix()
                source = MeetingSource.from_parts(directory.resolve(), relative_directory, parts)
            local_item = classify_item(source, output_root, stable=stable, stability_reason=reason)
            item = local_item
            if not dry_run and local_item.state is InboxState.ANALYSIS_COMPLETE and sheet_contains is not None:
                item = classify_item(source, output_root, sheet_exists=sheet_contains(local_item.meeting_id))
            notify(f"[{index}/{len(directories)}] {item.state.value} {source.relative_directory} -> {item.meeting_id} parts={len(source.parts)}")
            initial = item.state
            final = initial
            error = ""
            try:
                if dry_run:
                    summary["skipped"] += 1
                elif initial is InboxState.NEW:
                    if process_new is None:
                        raise ConfigurationError("new-meeting processor is not configured")
                    notify(f"Meeting source: {len(source.parts)} MP4 parts")
                    process_new(source, item.meeting_id)
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
                    records.append({"source_paths": [str(part.path) for part in source.parts], "meeting_id": item.meeting_id, "initial_state": initial.value, "final_state": final.value, "error": error})
                    break
            records.append({"source_paths": [str(part.path) for part in source.parts], "meeting_id": item.meeting_id, "initial_state": initial.value, "final_state": final.value, "error": error})

    if dry_run:
        execute()
    else:
        started = datetime.now(timezone.utc)
        with inbox_lock(work_root):
            execute()
            _write_manifest(work_root, {"run_id": run_id, "started_at": started.isoformat(), "completed_at": datetime.now(timezone.utc).isoformat(), "items": records})
    return InboxSummary(**summary)
