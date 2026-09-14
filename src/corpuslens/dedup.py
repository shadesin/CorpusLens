from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path


class ExactDeduplicator:
    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.connection = sqlite3.connect(database_path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.execute("CREATE TABLE seen (digest BLOB PRIMARY KEY, first_record INTEGER NOT NULL) WITHOUT ROWID")

    def observe(self, text: str, record_number: int) -> int | None:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        cursor = self.connection.execute(
            "INSERT OR IGNORE INTO seen(digest, first_record) VALUES (?, ?)",
            (digest, record_number),
        )
        if cursor.rowcount == 0:
            row = self.connection.execute("SELECT first_record FROM seen WHERE digest=?", (digest,)).fetchone()
            return int(row[0])
        if record_number % 50_000 == 0:
            self.connection.commit()
        return None

    def close(self) -> None:
        self.connection.commit()
        self.connection.close()
