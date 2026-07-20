from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_session_profanity_rate.cache import LabelCache
from ai_session_profanity_rate.models import MessageRecord
from ai_session_profanity_rate.pipeline import CONTRACT, ingest_run, prepare_run, summarize, validate_response


def record(item_id: str, text: str, family: str = "GPT") -> MessageRecord:
    return MessageRecord(
        item_id=item_id,
        timestamp="2026-07-20T12:00:00Z",
        local_date="2026-07-20",
        source="opencode",
        session_id="session-example",
        source_message_id=item_id,
        model="example-model",
        model_family=family,
        model_attribution="native_user",
        text=text,
    )


def test_cache_is_hmac_and_profile_versioned(tmp_path: Path) -> None:
    cache = LabelCache(tmp_path / "cache.sqlite3", tmp_path / "secret")
    key = cache.key("private text", "profile-a", CONTRACT)
    assert "private" not in key
    cache.put_many([(key, 1, "profile-a")])
    assert cache.get(key) == 1
    assert cache.get(cache.key("private text", "profile-b", CONTRACT)) is None
    cache.close()


def test_validate_response_rejects_missing_duplicate_and_negative_count() -> None:
    request = {"batch_id": "batch-0001", "items": [{"item_id": "a"}, {"item_id": "b"}]}
    base = {"schema_version": "classification-response.v2", "batch_id": "batch-0001", "definition_version": "profanity.v3"}
    with pytest.raises(ValueError, match="exactly match"):
        validate_response(request, {**base, "results": [{"item_id": "a", "count": 0}]})
    with pytest.raises(ValueError, match="duplicate"):
        validate_response(request, {**base, "results": [{"item_id": "a", "count": 0}, {"item_id": "a", "count": 1}]})
    with pytest.raises(ValueError, match="invalid count"):
        validate_response(request, {**base, "results": [{"item_id": "a", "count": -1}, {"item_id": "b", "count": 0}]})


def test_prepare_ingest_and_cache_rerun(tmp_path: Path) -> None:
    cache = LabelCache(tmp_path / "cache" / "labels.sqlite3", tmp_path / "cache" / "secret")
    run = tmp_path / "run-1"
    manifest = prepare_run(
        [record("a", "synthetic neutral"), record("b", "synthetic profanity")],
        run,
        cache,
        profile="test-profile",
        batch_size=100,
        batch_max_bytes=10000,
        refresh=False,
        metadata={},
    )
    assert manifest["batch_count"] == 1
    response = {
        "schema_version": "classification-response.v2",
        "batch_id": "batch-0001",
        "definition_version": "profanity.v3",
        "results": [{"item_id": "a", "count": 0}, {"item_id": "b", "count": 2}],
    }
    (run / "labels" / "batch-0001.json").write_text(json.dumps(response))
    result = ingest_run(run, cache)
    assert result["summary"]["profanity_count"] == 2
    assert result["summary"]["messages_with_profanity"] == 1
    assert all("text" not in item for item in result["records"])

    second = prepare_run(
        [record("a2", "synthetic neutral"), record("b2", "synthetic profanity")],
        tmp_path / "run-2",
        cache,
        profile="test-profile",
        batch_size=100,
        batch_max_bytes=10000,
        refresh=False,
        metadata={},
    )
    assert second["batch_count"] == 0
    assert second["cache_hit_count"] == 2
    cache.close()


def test_summarize_math() -> None:
    rows = [
        {"profanity_count": 2, "local_date": "2026-07-19", "model_family": "GPT", "source": "opencode"},
        {"profanity_count": 0, "local_date": "2026-07-19", "model_family": "GPT", "source": "opencode"},
        {"profanity_count": 1, "local_date": "2026-07-20", "model_family": "Claude", "source": "claude_code"},
    ]
    summary = summarize(rows)
    assert summary["profanity_count"] == 3
    assert summary["messages_with_profanity"] == 2
    assert summary["message_count"] == 3
    assert summary["by_model_family"]["GPT"]["message_rate"] == 0.5
    assert summary["by_model_family"]["GPT"]["profanity_per_100_messages"] == 100


def test_duplicate_text_is_classified_once_and_reused(tmp_path: Path) -> None:
    cache = LabelCache(tmp_path / "cache" / "labels.sqlite3", tmp_path / "cache" / "secret")
    run = tmp_path / "run"
    manifest = prepare_run(
        [record("a", "same text"), record("b", "same text")],
        run,
        cache,
        profile="profile",
        batch_size=100,
        batch_max_bytes=10000,
        refresh=False,
        metadata={},
    )
    assert manifest["message_cache_miss_count"] == 2
    assert manifest["classification_count"] == 1
    request = json.loads((run / "requests" / "batch-0001.json").read_text())
    assert len(request["items"]) == 1
    response = {
        "schema_version": "classification-response.v2",
        "batch_id": "batch-0001",
        "definition_version": "profanity.v3",
        "results": [{"item_id": request["items"][0]["item_id"], "count": 2}],
    }
    (run / "labels" / "batch-0001.json").write_text(json.dumps(response))
    results = ingest_run(run, cache)
    assert [item["profanity_count"] for item in results["records"]] == [2, 2]
    cache.close()


def test_ingest_rejects_request_text_tampering(tmp_path: Path) -> None:
    cache = LabelCache(tmp_path / "cache" / "labels.sqlite3", tmp_path / "cache" / "secret")
    run = tmp_path / "run"
    prepare_run(
        [record("a", "original")],
        run,
        cache,
        profile="profile",
        batch_size=100,
        batch_max_bytes=10000,
        refresh=False,
        metadata={},
    )
    request_path = run / "requests" / "batch-0001.json"
    request = json.loads(request_path.read_text())
    request["items"][0]["text"] = "tampered"
    request_path.write_text(json.dumps(request))
    response = {
        "schema_version": "classification-response.v2",
        "batch_id": "batch-0001",
        "definition_version": "profanity.v3",
        "results": [{"item_id": "a", "count": 0}],
    }
    (run / "labels" / "batch-0001.json").write_text(json.dumps(response))
    with pytest.raises(ValueError, match="private manifest"):
        ingest_run(run, cache)
    cache.close()


def test_prepare_rejects_existing_run_and_oversized_item(tmp_path: Path) -> None:
    cache = LabelCache(tmp_path / "cache" / "labels.sqlite3", tmp_path / "cache" / "secret")
    run = tmp_path / "run"
    kwargs = {
        "profile": "profile",
        "batch_size": 100,
        "batch_max_bytes": 10000,
        "refresh": False,
        "metadata": {},
    }
    prepare_run([record("a", "short")], run, cache, **kwargs)
    with pytest.raises(FileExistsError):
        prepare_run([record("a", "short")], run, cache, **kwargs)
    with pytest.raises(ValueError, match="exceeds batch-max-bytes"):
        prepare_run([record("b", "x" * 20_000)], tmp_path / "large", cache, **kwargs)
    cache.close()
