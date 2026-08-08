from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .cache import LabelCache
from .chart import render_chart
from .extractors import (
    apply_source_model_assumptions,
    extract_antigravity,
    extract_archive,
    extract_claude,
    extract_codex,
    extract_opencode,
    parse_timestamp,
)
from .pipeline import ingest_run, prepare_run


def default_home() -> Path:
    configured = os.environ.get("AI_SESSION_PROFANITY_RATE_HOME")
    if configured:
        return Path(configured).expanduser()
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "ai-session-profanity-rate"


def cache_paths(home: Path) -> tuple[Path, Path]:
    return home / "cache" / "labels.sqlite3", home / "cache" / "cache.secret"


def parse_as_of(value: str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    parsed = parse_timestamp(value)
    if parsed is None:
        raise ValueError("--as-of must be a valid RFC3339 timestamp")
    return parsed


def parse_model_assumptions(values: list[str]) -> dict[str, str]:
    assumptions: dict[str, str] = {}
    for value in values:
        source, separator, model = value.partition("=")
        source = source.strip()
        model = model.strip()
        if not separator or not source or not model:
            raise ValueError("--assume-source-model must use SOURCE=MODEL")
        if source in assumptions and assumptions[source] != model:
            raise ValueError(f"conflicting model assumptions for source: {source}")
        assumptions[source] = model
    return assumptions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-session-profanity-rate")
    parser.add_argument("--home", type=Path, default=default_home())
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="extract messages and create sub-agent request batches")
    prepare.add_argument("--days", type=int, default=7)
    prepare.add_argument("--timezone", default="UTC")
    prepare.add_argument("--as-of")
    prepare.add_argument("--source", default="opencode,claude_code,codex,antigravity")
    prepare.add_argument("--output", type=Path)
    prepare.add_argument("--batch-size", type=int, default=100)
    prepare.add_argument("--batch-max-bytes", type=int, default=80_000)
    prepare.add_argument("--classifier-profile", required=True)
    prepare.add_argument("--refresh", action="store_true")
    prepare.add_argument("--opencode-db", type=Path, default=Path.home() / ".local" / "share" / "opencode" / "opencode.db")
    prepare.add_argument("--claude-dir", type=Path, action="append")
    prepare.add_argument("--codex-dir", type=Path, action="append")
    prepare.add_argument("--antigravity-dir", type=Path, default=Path.home() / ".gemini" / "antigravity-ide" / "brain")
    prepare.add_argument("--archive-dir", type=Path, default=Path.home() / ".local" / "share" / "ai-session-export")
    prepare.add_argument(
        "--assume-source-model",
        action="append",
        default=[],
        metavar="SOURCE=MODEL",
        help="fill missing model metadata for a source using an explicit user-confirmed assumption",
    )

    ingest = subparsers.add_parser("ingest", help="validate labels, update cache, and emit JSON")
    ingest.add_argument("--run-dir", type=Path, required=True)

    visualize = subparsers.add_parser("visualize", help="render chart from results.json")
    visualize.add_argument("--input", type=Path, required=True)
    visualize.add_argument("--output", type=Path)

    subparsers.add_parser("cache-stats", help="show local label cache size")
    return parser


def command_prepare(args: argparse.Namespace, cache: LabelCache) -> int:
    if args.days < 1 or args.batch_size < 1 or args.batch_max_bytes < 1:
        raise ValueError("days, batch-size, and batch-max-bytes must be positive")
    tz = ZoneInfo(args.timezone)
    as_of = parse_as_of(args.as_of)
    local_as_of = as_of.astimezone(tz)
    start_date = local_as_of.date() - timedelta(days=args.days - 1)
    start = datetime.combine(start_date, time.min, tzinfo=tz).astimezone(timezone.utc)
    sources = {value.strip() for value in args.source.split(",") if value.strip()}
    records = []
    source_counts: dict[str, int] = {}
    source_status: dict[str, str] = {}

    def add(source: str, values: list) -> None:
        source_counts[source] = len(values)
        records.extend(values)

    if "opencode" in sources:
        source_status["opencode"] = "available" if args.opencode_db.expanduser().is_file() else "missing"
        add("opencode", extract_opencode(args.opencode_db.expanduser(), start, as_of, tz))
    if "claude_code" in sources:
        dirs = tuple(args.claude_dir or [Path.home() / ".claude" / "projects"])
        source_status["claude_code"] = "available" if any(path.is_dir() for path in dirs) else "missing"
        add("claude_code", extract_claude(dirs, start, as_of, tz))
    if "codex" in sources:
        dirs = tuple(args.codex_dir or [Path.home() / ".codex" / "sessions", Path.home() / ".codex" / "archived_sessions"])
        source_status["codex"] = "available" if any(path.is_dir() for path in dirs) else "missing"
        add("codex", extract_codex(dirs, start, as_of, tz))
    if "antigravity" in sources:
        source_status["antigravity"] = "available" if args.antigravity_dir.expanduser().is_dir() else "missing"
        add("antigravity", extract_antigravity(args.antigravity_dir.expanduser(), start, as_of, tz))
    if "archive" in sources:
        source_status["archive"] = "available" if args.archive_dir.expanduser().is_dir() else "missing"
        add("archive", extract_archive(args.archive_dir.expanduser(), start, as_of, tz))
    unknown = sources - {"opencode", "claude_code", "codex", "antigravity", "archive"}
    if unknown:
        raise ValueError(f"unsupported sources: {', '.join(sorted(unknown))}")
    model_assumptions = parse_model_assumptions(args.assume_source_model)
    records = apply_source_model_assumptions(records, model_assumptions)

    run_dir = args.output
    if run_dir is None:
        stamp = local_as_of.strftime("%Y%m%dT%H%M%S")
        run_dir = args.home / "runs" / f"{stamp}-{args.days}d"
    manifest = prepare_run(
        records,
        run_dir.expanduser(),
        cache,
        profile=args.classifier_profile,
        batch_size=args.batch_size,
        batch_max_bytes=args.batch_max_bytes,
        refresh=args.refresh,
        metadata={
            "days": args.days,
            "timezone": args.timezone,
            "as_of": as_of.isoformat(),
            "as_of_local_date": local_as_of.date().isoformat(),
            "window_start": start.isoformat(),
            "window_start_local_date": start_date.isoformat(),
            "sources": sorted(sources),
            "source_counts": source_counts,
            "source_status": source_status,
            "model_assumptions": model_assumptions,
        },
    )
    display_run_dir = str(run_dir).replace(str(Path.home()), "~", 1)
    print(
        json.dumps(
            {
                "run_dir": display_run_dir,
                "message_count": manifest["message_count"],
                "cache_hit_count": manifest["cache_hit_count"],
                "classification_count": manifest["classification_count"],
                "batch_count": manifest["batch_count"],
                "source_status": manifest["source_status"],
            },
            indent=2,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    home = args.home.expanduser()
    if args.command == "visualize":
        output = args.output or args.input.with_name("profanity_rate.png")
        render_chart(args.input.expanduser(), output.expanduser())
        print(str(output).replace(str(Path.home()), "~", 1))
        return 0
    db_path, secret_path = cache_paths(home)
    cache = LabelCache(db_path, secret_path)
    try:
        if args.command == "prepare":
            return command_prepare(args, cache)
        if args.command == "ingest":
            results = ingest_run(args.run_dir.expanduser(), cache)
            summary = results["summary"]
            print(
                json.dumps(
                    {
                        "results": str(args.run_dir / "results.json").replace(str(Path.home()), "~", 1),
                        "message_count": summary["message_count"],
                        "messages_with_profanity": summary["messages_with_profanity"],
                        "profanity_count": summary["profanity_count"],
                        "message_rate": summary["message_rate"],
                        "profanity_per_100_messages": summary["profanity_per_100_messages"],
                    },
                    indent=2,
                )
            )
            return 0
        if args.command == "cache-stats":
            print(json.dumps(cache.stats(), indent=2))
            return 0
    finally:
        cache.close()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
