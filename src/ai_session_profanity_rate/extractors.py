from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from .models import MessageRecord

SYSTEM_REMINDER_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL | re.IGNORECASE)
USER_REQUEST_RE = re.compile(r"<USER_REQUEST>(.*?)</USER_REQUEST>", re.DOTALL)
ARCHIVE_HEADING_RE = re.compile(r"^## (User|Assistant)(?: \[(\d{2}):(\d{2})\])?\s*$")


def parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def model_family(provider: str | None, model: str | None) -> str:
    provider_lower = (provider or "").lower()
    model_lower = (model or "").lower()
    if "claude" in model_lower or "anthropic" in provider_lower:
        return "Claude"
    if "gemini" in model_lower or "google" in provider_lower:
        return "Gemini"
    if "deepseek" in model_lower or "deepseek" in provider_lower or provider_lower == "ds4":
        return "DeepSeek"
    if "grok" in model_lower or provider_lower in {"xai", "x.ai"}:
        return "Grok"
    if model_lower.startswith(("glm", "zai-")) or "zai" in provider_lower:
        return "GLM"
    if model_lower.startswith(("gpt", "o1", "o3", "o4")) or provider_lower == "openai":
        return "GPT"
    if not model_lower:
        return "Unknown"
    return "Other"


def apply_source_model_assumptions(
    records: list[MessageRecord], assumptions: dict[str, str]
) -> list[MessageRecord]:
    output: list[MessageRecord] = []
    for record in records:
        assumed_model = assumptions.get(record.source)
        if record.model is None and assumed_model:
            output.append(
                replace(
                    record,
                    model=assumed_model,
                    model_family=model_family(None, assumed_model),
                    model_attribution="configured_source_default",
                )
            )
        else:
            output.append(record)
    return output


def clean_user_text(text: str) -> str:
    return SYSTEM_REMINDER_RE.sub("", text or "").strip()


def _record(
    *,
    source: str,
    session_id: str,
    message_id: str,
    timestamp: datetime,
    tz: ZoneInfo,
    text: str,
    provider: str | None,
    model: str | None,
    attribution: str,
) -> MessageRecord | None:
    cleaned = clean_user_text(text)
    if not cleaned:
        return None
    normalized_model = model.strip() if model and model.strip() else None
    return MessageRecord(
        item_id=f"{source}:{session_id}:{message_id}",
        timestamp=timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        local_date=timestamp.astimezone(tz).date().isoformat(),
        source=source,
        session_id=session_id,
        source_message_id=message_id,
        model=normalized_model,
        model_family=model_family(provider, normalized_model),
        model_attribution=attribution,
        text=cleaned,
    )


def extract_opencode(db_path: Path, start: datetime, end: datetime, tz: ZoneInfo) -> list[MessageRecord]:
    if not db_path.is_file():
        return []
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT m.id AS message_id, m.session_id, m.time_created, m.data
        FROM message m
        JOIN session s ON s.id = m.session_id
        WHERE s.parent_id IS NULL
          AND json_extract(m.data, '$.role') = 'user'
          AND m.time_created >= ? AND m.time_created <= ?
        ORDER BY m.time_created, m.id
        """,
        (int(start.timestamp() * 1000), int(end.timestamp() * 1000)),
    ).fetchall()
    records: list[MessageRecord] = []
    for row in rows:
        data = json.loads(row["data"])
        model_data = data.get("model") if isinstance(data.get("model"), dict) else {}
        texts = conn.execute(
            """
            SELECT COALESCE(json_extract(data, '$.text'), '')
            FROM part
            WHERE session_id = ? AND message_id = ? AND json_extract(data, '$.type') = 'text'
            ORDER BY time_created, id
            """,
            (row["session_id"], row["message_id"]),
        ).fetchall()
        record = _record(
            source="opencode",
            session_id=row["session_id"],
            message_id=row["message_id"],
            timestamp=datetime.fromtimestamp(row["time_created"] / 1000, timezone.utc),
            tz=tz,
            text="".join(item[0] for item in texts),
            provider=str(model_data.get("providerID") or ""),
            model=str(model_data.get("modelID") or ""),
            attribution="native_user",
        )
        if record:
            records.append(record)
    conn.close()
    return records


def _iter_jsonl(paths: Iterable[Path]) -> Iterable[tuple[Path, int, dict[str, Any]]]:
    for path in paths:
        if not path.is_file():
            continue
        with path.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                try:
                    value = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    yield path, line_number, value


def _text_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    texts = [str(item.get("text") or "").strip() for item in content if isinstance(item, dict) and item.get("type") == "text"]
    return "\n\n".join(text for text in texts if text)


def extract_claude(project_dirs: tuple[Path, ...], start: datetime, end: datetime, tz: ZoneInfo) -> list[MessageRecord]:
    files: list[Path] = []
    for root in project_dirs:
        if root.is_dir():
            files.extend(path for path in root.rglob("*.jsonl") if "subagents" not in path.parts)
    records: list[dict[str, Any]] = []
    pending_by_session: dict[str, list[int]] = {}
    for path, line_number, event in _iter_jsonl(sorted(set(files))):
        if event.get("isSidechain") is True:
            continue
        timestamp = parse_timestamp(str(event.get("timestamp") or ""))
        session_id = str(event.get("sessionId") or path.stem)
        if event.get("type") == "user" and timestamp and start <= timestamp <= end:
            text = _text_content((event.get("message") or {}).get("content"))
            if not clean_user_text(text):
                continue
            records.append(
                {
                    "session_id": session_id,
                    "message_id": str(event.get("uuid") or f"{path.stem}:{line_number}"),
                    "timestamp": timestamp,
                    "text": text,
                    "model": None,
                }
            )
            pending_by_session.setdefault(session_id, []).append(len(records) - 1)
        elif event.get("type") == "assistant":
            model = str((event.get("message") or {}).get("model") or "").strip()
            pending = pending_by_session.get(session_id, [])
            if model and pending:
                for index in pending:
                    records[index]["model"] = model
                pending.clear()
    output: list[MessageRecord] = []
    for item in records:
        record = _record(
            source="claude_code",
            session_id=item["session_id"],
            message_id=item["message_id"],
            timestamp=item["timestamp"],
            tz=tz,
            text=item["text"],
            provider="anthropic" if item["model"] else None,
            model=item["model"],
            attribution="next_response" if item["model"] else "unknown",
        )
        if record:
            output.append(record)
    return output


def extract_codex(session_dirs: tuple[Path, ...], start: datetime, end: datetime, tz: ZoneInfo) -> list[MessageRecord]:
    files: list[Path] = []
    for root in session_dirs:
        if root.is_dir():
            files.extend(root.rglob("rollout-*.jsonl"))
    output: list[MessageRecord] = []
    for path in sorted(set(files)):
        session_id = path.stem
        current_model: str | None = None
        pending: list[int] = []
        file_records: list[MessageRecord] = []
        raw_pending: list[dict[str, Any]] = []
        for _, line_number, event in _iter_jsonl([path]):
            timestamp = parse_timestamp(str(event.get("timestamp") or ""))
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            if event.get("type") == "session_meta":
                session_id = str(payload.get("id") or payload.get("session_id") or session_id)
            elif event.get("type") == "turn_context":
                current_model = str(payload.get("model") or "").strip() or None
                for index in pending:
                    raw_pending[index]["model"] = current_model
                pending.clear()
            elif (
                event.get("type") == "event_msg"
                and payload.get("type") == "user_message"
                and timestamp
                and start <= timestamp <= end
            ):
                text = str(payload.get("message") or "").strip()
                if not clean_user_text(text):
                    continue
                raw_pending.append(
                    {
                        "message_id": str(payload.get("id") or f"{path.stem}:{line_number}"),
                        "timestamp": timestamp,
                        "text": text,
                        "model": current_model,
                    }
                )
                pending.append(len(raw_pending) - 1)
            elif event.get("type") == "event_msg" and payload.get("type") == "agent_message":
                pending.clear()
        for item in raw_pending:
            record = _record(
                source="codex",
                session_id=session_id,
                message_id=item["message_id"],
                timestamp=item["timestamp"],
                tz=tz,
                text=item["text"],
                provider="openai" if item["model"] else None,
                model=item["model"],
                attribution="turn_context" if item["model"] else "unknown",
            )
            if record:
                file_records.append(record)
        output.extend(file_records)
    return output


def extract_antigravity(brain_dir: Path, start: datetime, end: datetime, tz: ZoneInfo) -> list[MessageRecord]:
    output: list[MessageRecord] = []
    if not brain_dir.is_dir():
        return output
    for session_dir in sorted(path for path in brain_dir.iterdir() if path.is_dir()):
        transcript = session_dir / ".system_generated" / "logs" / "transcript_full.jsonl"
        for _, line_number, event in _iter_jsonl([transcript]):
            if event.get("type") != "USER_INPUT" or event.get("source") != "USER_EXPLICIT":
                continue
            timestamp = parse_timestamp(str(event.get("created_at") or ""))
            if not timestamp or not (start <= timestamp <= end):
                continue
            content = str(event.get("content") or "")
            matches = USER_REQUEST_RE.findall(content)
            text = "\n\n".join(match.strip() for match in matches) if matches else content
            record = _record(
                source="antigravity",
                session_id=session_dir.name,
                message_id=str(event.get("id") or f"step-{line_number}"),
                timestamp=timestamp,
                tz=tz,
                text=text,
                provider=None,
                model=None,
                attribution="unknown",
            )
            if record:
                output.append(record)
    return output


def _frontmatter_value(lines: list[str], key: str) -> str | None:
    prefix = f"{key}:"
    for line in lines:
        if not line.startswith(prefix):
            continue
        value = line[len(prefix) :].strip()
        if value.startswith('"'):
            try:
                decoded = json.loads(value)
            except json.JSONDecodeError:
                return None
            return decoded if isinstance(decoded, str) else None
        return value or None
    return None


def extract_archive(archive_dir: Path, start: datetime, end: datetime, tz: ZoneInfo) -> list[MessageRecord]:
    """Read the stable Markdown contract produced by AI Session Export.

    The archive stores local HH:MM values rather than full per-turn timestamps,
    so callers must pass the timezone used on the exporting machine. A decrease
    in turn time advances the inferred date for sessions crossing midnight.
    """
    if not archive_dir.is_dir():
        return []
    output: list[MessageRecord] = []
    for path in sorted(archive_dir.rglob("*.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        if not lines or lines[0] != "---":
            continue
        try:
            frontmatter_end = lines.index("---", 1)
        except ValueError:
            continue
        frontmatter = lines[1:frontmatter_end]
        source = _frontmatter_value(frontmatter, "source")
        session_id = _frontmatter_value(frontmatter, "session_id")
        session_date_text = _frontmatter_value(frontmatter, "date")
        turn_models_present = any(line.startswith("turn_models:") for line in frontmatter)
        turn_models_text = _frontmatter_value(frontmatter, "turn_models")
        if not source or not session_id or not session_date_text:
            continue
        try:
            current_date = date.fromisoformat(session_date_text)
        except ValueError:
            continue

        turn_models: list[str | None] | None = None
        if turn_models_present:
            if turn_models_text is None:
                raise ValueError("invalid turn_models value in archive")
            try:
                parsed_turn_models = json.loads(turn_models_text)
            except json.JSONDecodeError as exc:
                raise ValueError("invalid turn_models JSON in archive") from exc
            if not isinstance(parsed_turn_models, list) or any(
                value is not None and (not isinstance(value, str) or not value.strip())
                for value in parsed_turn_models
            ):
                raise ValueError("invalid turn_models values in archive")
            turn_models = [value.strip() if isinstance(value, str) else None for value in parsed_turn_models]

        headings: list[tuple[int, str, time | None, date]] = []
        previous_time: time | None = None
        for index, line in enumerate(lines[frontmatter_end + 1 :], start=frontmatter_end + 1):
            match = ARCHIVE_HEADING_RE.fullmatch(line)
            if not match:
                continue
            turn_time = time(int(match.group(2)), int(match.group(3))) if match.group(2) else None
            if turn_time is not None and previous_time is not None and turn_time < previous_time:
                current_date += timedelta(days=1)
            if turn_time is not None:
                previous_time = turn_time
            headings.append((index, match.group(1), turn_time, current_date))

        if turn_models is not None and len(turn_models) != len(headings):
            raise ValueError("turn_models length mismatch in archive")

        for turn_index, (line_index, role, turn_time, turn_date) in enumerate(headings):
            if role != "User":
                continue
            content_end = headings[turn_index + 1][0] if turn_index + 1 < len(headings) else len(lines)
            text = "\n".join(lines[line_index + 1 : content_end]).strip()
            local_timestamp = datetime.combine(turn_date, turn_time or time.min, tzinfo=tz)
            timestamp = local_timestamp.astimezone(timezone.utc)
            if not (start <= timestamp <= end):
                continue
            turn_model = turn_models[turn_index] if turn_models is not None else None
            record = _record(
                source=source,
                session_id=session_id,
                message_id=f"archive-{turn_index + 1}",
                timestamp=timestamp,
                tz=tz,
                text=text,
                provider=None,
                model=turn_model,
                attribution="archive_turn_model" if turn_model else "archive_unavailable",
            )
            if record:
                output.append(record)
    unique: dict[str, MessageRecord] = {}
    for record in output:
        existing = unique.get(record.item_id)
        if existing is not None and existing != record:
            raise ValueError("conflicting archive records for duplicate item_id")
        unique.setdefault(record.item_id, record)
    return list(unique.values())
