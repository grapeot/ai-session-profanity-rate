from __future__ import annotations

import json

import pytest

from ai_session_profanity_rate.cli import main, parse_model_assumptions


def test_parse_model_assumptions() -> None:
    assert parse_model_assumptions(["antigravity=gemini", "custom=grok-4.5"]) == {
        "antigravity": "gemini",
        "custom": "grok-4.5",
    }


@pytest.mark.parametrize("value", ["antigravity", "=gemini", "antigravity="])
def test_parse_model_assumptions_rejects_invalid_value(value: str) -> None:
    with pytest.raises(ValueError, match="SOURCE=MODEL"):
        parse_model_assumptions([value])


def test_prepare_and_ingest_preserve_model_assumption_provenance(tmp_path) -> None:
    home = tmp_path / "home"
    run = tmp_path / "run"
    prepare_args = [
        "--home",
        str(home),
        "prepare",
        "--source",
        "",
        "--output",
        str(run),
        "--classifier-profile",
        "synthetic-profile",
        "--assume-source-model",
        "antigravity=gemini",
    ]

    assert main(prepare_args) == 0
    assert main(["--home", str(home), "ingest", "--run-dir", str(run)]) == 0

    results = json.loads((run / "results.json").read_text(encoding="utf-8"))
    assert results["provenance"]["model_assumptions"] == {"antigravity": "gemini"}
