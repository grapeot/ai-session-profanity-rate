from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from ai_session_profanity_rate.extractors import (
    clean_user_text,
    extract_antigravity,
    extract_claude,
    extract_codex,
    extract_opencode,
    model_family,
)

START = datetime(2026, 7, 19, tzinfo=timezone.utc)
END = datetime(2026, 7, 21, tzinfo=timezone.utc)
TZ = ZoneInfo("America/Los_Angeles")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def test_model_family() -> None:
    assert model_family("openai", "gpt-example") == "GPT"
    assert model_family("anthropic", "claude-example") == "Claude"
    assert model_family("zai-coding-plan", "glm-example") == "GLM"
    assert model_family(None, None) == "Unknown"


def test_clean_user_text_strips_transport_reminder() -> None:
    assert clean_user_text("hello<system-reminder>private transport metadata</system-reminder>") == "hello"


def test_extract_opencode_top_level_and_native_model(tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE session(id TEXT PRIMARY KEY, parent_id TEXT);
        CREATE TABLE message(id TEXT PRIMARY KEY, session_id TEXT, time_created INTEGER, data TEXT);
        CREATE TABLE part(id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT, time_created INTEGER, data TEXT);
        """
    )
    ts = int(datetime(2026, 7, 20, 12, tzinfo=timezone.utc).timestamp() * 1000)
    conn.execute("INSERT INTO session VALUES ('top', NULL)")
    conn.execute("INSERT INTO session VALUES ('child', 'top')")
    data = json.dumps({"role": "user", "model": {"providerID": "openai", "modelID": "gpt-example"}})
    conn.execute("INSERT INTO message VALUES ('m1', 'top', ?, ?)", (ts, data))
    conn.execute("INSERT INTO message VALUES ('m2', 'child', ?, ?)", (ts, data))
    conn.execute("INSERT INTO part VALUES ('p1', 'm1', 'top', ?, ?)", (ts, json.dumps({"type": "text", "text": "synthetic"})))
    conn.execute("INSERT INTO part VALUES ('p2', 'm2', 'child', ?, ?)", (ts, json.dumps({"type": "text", "text": "subagent"})))
    conn.commit()
    conn.close()
    records = extract_opencode(db, START, END, TZ)
    assert len(records) == 1
    assert records[0].model_family == "GPT"
    assert records[0].model_attribution == "native_user"


def test_extract_claude_uses_next_response_model(tmp_path: Path) -> None:
    file_path = tmp_path / "project" / "session.jsonl"
    write_jsonl(
        file_path,
        [
            {"type": "user", "sessionId": "s1", "uuid": "u1", "timestamp": "2026-07-20T12:00:00Z", "message": {"content": "synthetic"}},
            {"type": "assistant", "sessionId": "s1", "timestamp": "2026-07-20T12:00:01Z", "message": {"model": "claude-example", "content": "reply"}},
        ],
    )
    records = extract_claude((tmp_path,), START, END, TZ)
    assert len(records) == 1
    assert records[0].model == "claude-example"
    assert records[0].model_attribution == "next_response"


def test_extract_codex_uses_turn_context(tmp_path: Path) -> None:
    file_path = tmp_path / "sessions" / "rollout-2026-07-20T00-00-00-example.jsonl"
    write_jsonl(
        file_path,
        [
            {"timestamp": "2026-07-20T12:00:00Z", "type": "session_meta", "payload": {"id": "s1"}},
            {"timestamp": "2026-07-20T12:00:01Z", "type": "turn_context", "payload": {"model": "gpt-example"}},
            {"timestamp": "2026-07-20T12:00:02Z", "type": "event_msg", "payload": {"type": "user_message", "message": "synthetic"}},
        ],
    )
    records = extract_codex((tmp_path / "sessions",), START, END, TZ)
    assert len(records) == 1
    assert records[0].model_family == "GPT"


def test_extract_codex_updates_model_when_context_follows_user(tmp_path: Path) -> None:
    file_path = tmp_path / "sessions" / "rollout-2026-07-20T00-00-00-switch.jsonl"
    write_jsonl(
        file_path,
        [
            {"timestamp": "2026-07-20T12:00:00Z", "type": "session_meta", "payload": {"id": "s1"}},
            {"timestamp": "2026-07-20T12:00:01Z", "type": "turn_context", "payload": {"model": "gpt-old"}},
            {"timestamp": "2026-07-20T12:00:02Z", "type": "event_msg", "payload": {"type": "user_message", "message": "first"}},
            {"timestamp": "2026-07-20T12:00:03Z", "type": "event_msg", "payload": {"type": "agent_message", "message": "reply"}},
            {"timestamp": "2026-07-20T12:00:04Z", "type": "event_msg", "payload": {"type": "user_message", "message": "second"}},
            {"timestamp": "2026-07-20T12:00:05Z", "type": "turn_context", "payload": {"model": "gpt-new"}},
        ],
    )
    records = extract_codex((tmp_path / "sessions",), START, END, TZ)
    assert [record.model for record in records] == ["gpt-old", "gpt-new"]


def test_extract_antigravity_keeps_explicit_request_only(tmp_path: Path) -> None:
    transcript = tmp_path / "brain" / "s1" / ".system_generated" / "logs" / "transcript_full.jsonl"
    write_jsonl(
        transcript,
        [
            {"type": "USER_INPUT", "source": "USER_EXPLICIT", "created_at": "2026-07-20T12:00:00Z", "content": "<USER_REQUEST>synthetic</USER_REQUEST>"},
            {"type": "USER_INPUT", "source": "SYSTEM", "created_at": "2026-07-20T12:00:01Z", "content": "ignored"},
        ],
    )
    records = extract_antigravity(tmp_path / "brain", START, END, TZ)
    assert len(records) == 1
    assert records[0].text == "synthetic"
    assert records[0].model_family == "Unknown"
