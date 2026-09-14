"""Exact and approximate duplicate indexes that keep their state on disk."""

from __future__ import annotations

import hashlib
import random
import sqlite3
import struct
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


class ExactDeduplicator:
    """Identify normalized duplicate strings using a SQLite SHA-256 index."""

    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.connection = sqlite3.connect(database_path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.execute("CREATE TABLE seen (digest BLOB PRIMARY KEY, first_record INTEGER NOT NULL) WITHOUT ROWID")
        self.documents_indexed = 0
        self.matches_found = 0

    def observe(self, text: str, record_number: int) -> int | None:
        """Index ``text`` or return the record number that first contained it."""
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        cursor = self.connection.execute(
            "INSERT OR IGNORE INTO seen(digest, first_record) VALUES (?, ?)",
            (digest, record_number),
        )
        if cursor.rowcount == 0:
            row = self.connection.execute("SELECT first_record FROM seen WHERE digest=?", (digest,)).fetchone()
            self.matches_found += 1
            return int(row[0])
        self.documents_indexed += 1
        if record_number % 50_000 == 0:
            self.connection.commit()
        return None

    def statistics(self) -> dict[str, int]:
        """Expose index counters without requiring callers to query SQLite."""
        return {
            "exact_documents_indexed": self.documents_indexed,
            "exact_duplicates_removed": self.matches_found,
        }

    def close(self) -> None:
        """Persist pending writes and release the temporary database."""
        self.connection.commit()
        self.connection.close()


MINHASH_PRIME = (1 << 61) - 1


def word_tokens(text: str) -> list[str]:
    """Tokenize Unicode letters/marks/numbers without assuming one script."""
    tokens: list[str] = []
    current: list[str] = []
    for character in unicodedata.normalize("NFC", text).casefold():
        if unicodedata.category(character)[0] in {"L", "M", "N"}:
            current.append(character)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return tokens


def shingle_hashes(text: str, size: int) -> set[int]:
    """Return stable 64-bit hashes of word or fallback character shingles.

    Character shingles keep near-dedup useful for unsegmented writing systems
    and very short records that do not contain enough whitespace-separated
    words to form a word shingle.
    """
    tokens = word_tokens(text)
    if len(tokens) >= size:
        shingles = ("\u241f".join(tokens[index:index + size]) for index in range(len(tokens) - size + 1))
    else:
        compact = "".join(character for character in unicodedata.normalize("NFC", text).casefold() if not character.isspace())
        character_size = max(3, size + 2)
        if len(compact) < character_size:
            return set()
        shingles = (compact[index:index + character_size] for index in range(len(compact) - character_size + 1))
    return {
        int.from_bytes(hashlib.blake2b(shingle.encode("utf-8"), digest_size=8).digest(), "big")
        for shingle in shingles
    }


@lru_cache(maxsize=32)
def _permutation_coefficients(permutations: int) -> tuple[tuple[int, int], ...]:
    """Build deterministic MinHash permutations once per signature size."""
    generator = random.Random(0)
    return tuple(
        (generator.randrange(1, MINHASH_PRIME), generator.randrange(0, MINHASH_PRIME))
        for _ in range(permutations)
    )


def minhash_signature(hashes: set[int], permutations: int) -> tuple[int, ...]:
    """Compress a shingle set into a deterministic MinHash signature."""
    if not hashes:
        return ()
    coefficients = _permutation_coefficients(permutations)
    signature = [MINHASH_PRIME] * permutations
    for value in hashes:
        reduced = value % MINHASH_PRIME
        for index, (multiplier, offset) in enumerate(coefficients):
            candidate = (multiplier * reduced + offset) % MINHASH_PRIME
            if candidate < signature[index]:
                signature[index] = candidate
    return tuple(signature)


def band_keys(signature: tuple[int, ...], rows: int):
    """Yield compact LSH bucket keys for consecutive signature bands."""
    for band, start in enumerate(range(0, len(signature), rows)):
        packed = struct.pack(f">{rows}Q", *signature[start:start + rows])
        yield band, hashlib.blake2b(packed, digest_size=8).digest()


def jaccard(first: set[int], second: set[int]) -> float:
    """Compute exact set similarity used for the final removal decision."""
    if not first and not second:
        return 1.0
    return len(first & second) / len(first | second) if first and second else 0.0


def _pack_hashes(hashes: set[int]) -> bytes:
    """Serialize a shingle set compactly for SQLite storage."""
    ordered = sorted(hashes)
    return struct.pack(f">{len(ordered)}Q", *ordered)


def _unpack_hashes(payload: bytes) -> set[int]:
    """Restore a set produced by :func:`_pack_hashes`."""
    if not payload:
        return set()
    return set(struct.unpack(f">{len(payload) // 8}Q", payload))


@dataclass(frozen=True)
class NearDuplicateMatch:
    """Evidence returned when a retained record passes exact verification."""

    first_record: int
    similarity: float
    candidate_comparisons: int


class NearDeduplicator:
    """Disk-backed MinHash/LSH candidate search with exact Jaccard checks."""

    def __init__(
        self,
        database_path: Path,
        threshold: float = 0.85,
        shingle_size: int = 3,
        bands: int = 8,
        rows: int = 4,
        max_candidates: int = 1_000,
    ):
        if not 0 < threshold <= 1:
            raise ValueError("Near-duplicate threshold must be in (0, 1].")
        if min(shingle_size, bands, rows, max_candidates) < 1:
            raise ValueError("Near-deduplication sizes must be positive.")
        self.threshold = threshold
        self.shingle_size = shingle_size
        self.bands = bands
        self.rows = rows
        self.permutations = bands * rows
        self.max_candidates = max_candidates
        self.candidate_comparisons = 0
        self.documents_indexed = 0
        self.documents_skipped = 0
        self.matches_found = 0
        self.connection = sqlite3.connect(database_path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.execute("CREATE TABLE documents (record INTEGER PRIMARY KEY, shingles BLOB NOT NULL)")
        self.connection.execute(
            "CREATE TABLE buckets (band INTEGER NOT NULL, bucket BLOB NOT NULL, record INTEGER NOT NULL, "
            "PRIMARY KEY (band, bucket, record)) WITHOUT ROWID"
        )

    def observe(self, text: str, record_number: int) -> NearDuplicateMatch | None:
        """Find a verified earlier match or add this record to the LSH index.

        LSH is used only to propose candidates. A candidate is never removed
        until its stored shingles meet the configured exact Jaccard threshold.
        """
        hashes = shingle_hashes(text, self.shingle_size)
        if not hashes:
            self.documents_skipped += 1
            return None
        signature = minhash_signature(hashes, self.permutations)
        keys = list(band_keys(signature, self.rows))
        candidates: set[int] = set()
        for band, key in keys:
            remaining = self.max_candidates - len(candidates)
            if remaining <= 0:
                break
            rows = self.connection.execute(
                "SELECT record FROM buckets WHERE band=? AND bucket=? ORDER BY record LIMIT ?",
                (band, key, remaining),
            )
            candidates.update(int(row[0]) for row in rows)

        for candidate in sorted(candidates):
            row = self.connection.execute("SELECT shingles FROM documents WHERE record=?", (candidate,)).fetchone()
            if row is None:
                continue
            self.candidate_comparisons += 1
            score = jaccard(hashes, _unpack_hashes(row[0]))
            if score >= self.threshold:
                self.matches_found += 1
                return NearDuplicateMatch(candidate, score, len(candidates))

        self.connection.execute("INSERT INTO documents(record, shingles) VALUES (?, ?)", (record_number, _pack_hashes(hashes)))
        self.connection.executemany(
            "INSERT INTO buckets(band, bucket, record) VALUES (?, ?, ?)",
            ((band, key, record_number) for band, key in keys),
        )
        self.documents_indexed += 1
        if self.documents_indexed % 10_000 == 0:
            self.connection.commit()
        return None

    def statistics(self) -> dict[str, int | float]:
        """Return counters and parameters needed to audit the LSH run."""
        return {
            "near_documents_indexed": self.documents_indexed,
            "near_documents_without_shingles": self.documents_skipped,
            "near_candidate_comparisons": self.candidate_comparisons,
            "near_duplicates_removed": self.matches_found,
            "near_threshold": self.threshold,
            "near_shingle_size": self.shingle_size,
            "lsh_bands": self.bands,
            "lsh_rows": self.rows,
            "lsh_signature_values": self.permutations,
            "max_lsh_candidates_per_record": self.max_candidates,
        }

    def close(self) -> None:
        """Persist pending writes and release the temporary database."""
        self.connection.commit()
        self.connection.close()
