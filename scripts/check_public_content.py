from __future__ import annotations

import re
import subprocess
from pathlib import Path


TEXT_SUFFIXES = {".md", ".py", ".toml", ".yml", ".yaml", ".json", ".example", ".txt"}
PATTERNS = [
    ("personal absolute path", re.compile("/" + r"(?:Users|home)/[^/\s]+/")),
    ("secret-manager reference", re.compile("op:" + r"//")),
    ("private key", re.compile("BEGIN " + r"(?:RSA |OPENSSH )?PRIVATE KEY")),
    ("token-like value", re.compile(r"\b(?:sk|tvly)-[A-Za-z0-9_-]{16,}\b")),
    ("private network address", re.compile(r"\b(?:10\.\d+|192\.168\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d+)\.\d+\b")),
]
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
FAKE_EMAIL_DOMAINS = {"example.com", "example.net", "example.org"}


def public_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard", "-z"],
        check=True,
        capture_output=True,
    )
    return [Path(value.decode()) for value in result.stdout.split(b"\0") if value]


def main() -> int:
    findings: list[str] = []
    for path in public_files():
        if path.suffix not in TEXT_SUFFIXES and path.name not in {"LICENSE", ".gitignore"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            for name, pattern in PATTERNS:
                if pattern.search(line):
                    findings.append(f"{path}:{line_number}: {name}")
            for match in EMAIL_RE.finditer(line):
                if match.group(1).lower() not in FAKE_EMAIL_DOMAINS:
                    findings.append(f"{path}:{line_number}: non-example email")
    if findings:
        print("\n".join(findings))
        return 1
    print("Public-content checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
