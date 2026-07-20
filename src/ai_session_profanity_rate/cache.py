from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class LabelCache:
    def __init__(self, db_path: Path, secret_path: Path) -> None:
        self.db_path = db_path
        self.secret_path = secret_path
        db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(db_path.parent, 0o700)
        if not secret_path.exists():
            secret_path.write_bytes(secrets.token_bytes(32))
            os.chmod(secret_path, 0o600)
        self.secret = secret_path.read_bytes()
        self.conn = sqlite3.connect(db_path)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS labels (
                cache_key TEXT PRIMARY KEY,
                profanity_count INTEGER NOT NULL CHECK(profanity_count >= 0),
                profile TEXT NOT NULL,
                classified_at TEXT NOT NULL
            )
            """
        )
        self.conn.commit()
        os.chmod(db_path, 0o600)

    def key(self, text: str, profile: str, contract: str) -> str:
        payload = f"{contract}\0{profile}\0{text}".encode()
        return hmac.new(self.secret, payload, hashlib.sha256).hexdigest()

    def get(self, cache_key: str) -> int | None:
        row = self.conn.execute("SELECT profanity_count FROM labels WHERE cache_key = ?", (cache_key,)).fetchone()
        return int(row[0]) if row else None

    def put_many(self, values: list[tuple[str, int, str]]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.conn:
            self.conn.executemany(
                """
                INSERT INTO labels(cache_key, profanity_count, profile, classified_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    profanity_count = excluded.profanity_count,
                    profile = excluded.profile,
                    classified_at = excluded.classified_at
                """,
                [(key, count, profile, now) for key, count, profile in values],
            )

    def stats(self) -> dict[str, int]:
        count = int(self.conn.execute("SELECT count(*) FROM labels").fetchone()[0])
        return {"labels": count}

    def close(self) -> None:
        self.conn.close()
