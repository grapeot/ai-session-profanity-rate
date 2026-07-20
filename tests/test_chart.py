from __future__ import annotations

import json
import stat
from pathlib import Path

from ai_session_profanity_rate.chart import render_chart
from ai_session_profanity_rate.cli import main


def test_render_chart(tmp_path: Path) -> None:
    input_path = tmp_path / "results.json"
    input_path.write_text(
        json.dumps(
            {
                "records": [
                    {"local_date": "2026-07-20", "profanity_count": 2, "model_family": "GPT"},
                    {"local_date": "2026-07-20", "profanity_count": 0, "model_family": "Claude"},
                ]
            }
        )
    )
    output = render_chart(input_path, tmp_path / "chart.png")
    assert output.stat().st_size > 1000
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_visualize_does_not_create_cache(tmp_path: Path) -> None:
    input_path = tmp_path / "results.json"
    input_path.write_text(json.dumps({"records": []}))
    home = tmp_path / "unused-home"
    assert main(["--home", str(home), "visualize", "--input", str(input_path)]) == 0
    assert not home.exists()
