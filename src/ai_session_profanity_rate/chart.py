from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

MODEL_FAMILIES = ["GPT", "Claude", "Gemini", "Grok", "GLM", "DeepSeek", "Other", "Unknown"]


def render_chart(input_path: Path, output_path: Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    payload = json.loads(input_path.read_text(encoding="utf-8"))
    records = payload.get("records", [])
    provenance = payload.get("provenance", {})
    if provenance.get("window_start_local_date") and provenance.get("as_of_local_date"):
        start_date = date.fromisoformat(str(provenance["window_start_local_date"]))
        end_date = date.fromisoformat(str(provenance["as_of_local_date"]))
        dates = []
        cursor = start_date
        while cursor <= end_date:
            dates.append(cursor.isoformat())
            cursor += timedelta(days=1)
    else:
        dates = sorted({record["local_date"] for record in records})
    totals = Counter(record["local_date"] for record in records)
    positives = Counter(record["local_date"] for record in records if record["profanity_count"] > 0)
    composition: dict[str, Counter[str]] = defaultdict(Counter)
    for record in records:
        if record["profanity_count"] > 0:
            composition[record["local_date"]][record["model_family"]] += int(record["profanity_count"])

    fig, (rate_ax, composition_ax) = plt.subplots(2, 1, figsize=(max(10, len(dates) * 0.55), 8), sharex=True)
    rates = [100 * positives[date] / totals[date] if totals[date] else 0 for date in dates]
    bars = rate_ax.bar(dates, rates, color="#8B1E3F")
    rate_ax.set_ylabel("Profanity rate (%)")
    rate_ax.set_title("Messages containing profanity (daily incidence)")
    rate_ax.grid(axis="y", alpha=0.2)
    for bar, date_value in zip(bars, dates, strict=True):
        rate_ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{bar.get_height():.1f}%\n{positives[date_value]}/{totals[date_value]}",
            ha="center",
            va="bottom",
            fontsize=7,
        )
    rate_ax.set_ylim(0, max(rates, default=0) * 1.35 + 0.5)
    rate_ax.tick_params(axis="x", labelbottom=True, rotation=45, labelsize=8)

    colors = {
        "GPT": "#3A7D6B",
        "Claude": "#C76D3B",
        "Gemini": "#00A6A6",
        "Grok": "#D1495B",
        "GLM": "#7A5AF8",
        "DeepSeek": "#277DA1",
        "Other": "#8D99AE",
        "Unknown": "#C7C7C7",
    }
    bottoms = [0] * len(dates)
    for family in MODEL_FAMILIES:
        values = [composition[date][family] for date in dates]
        if not any(values):
            continue
        composition_ax.bar(dates, values, bottom=bottoms, label=family, color=colors[family])
        bottoms = [left + value for left, value in zip(bottoms, values, strict=True)]
    composition_ax.set_ylabel("Profanity units")
    composition_ax.set_title("Composition of profanity units by target model family (absolute counts, not model rates)")
    composition_ax.grid(axis="y", alpha=0.2)
    if any(bottoms):
        composition_ax.legend(
            ncol=len([value for value in MODEL_FAMILIES if any(composition[date][value] for date in dates)]),
            frameon=False,
        )
        composition_ax.set_ylim(0, max(bottoms) * 1.12 + 0.5)
    composition_ax.tick_params(axis="x", rotation=45, labelsize=8)
    fig.text(
        0.01,
        0.01,
        "Composition bars show where counted units occurred, not which model caused them. Model selection, usage volume, and task difficulty confound comparisons.",
        fontsize=9,
        color="#333333",
    )
    fig.tight_layout(rect=(0, 0.055, 1, 1))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    os.chmod(output_path, 0o600)
    plt.close(fig)
    return output_path
