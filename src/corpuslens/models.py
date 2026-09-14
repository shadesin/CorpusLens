"""Shared data contracts passed between the CLI, detectors, and reports."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


Action = Literal["flag", "reject", "transform"]


@dataclass(frozen=True)
class Finding:
    """One explainable signal produced by a detector for a single record."""

    code: str
    action: Action
    message: str
    value: int | float | str | None = None
    threshold: int | float | str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a compact JSON-ready representation."""
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass(frozen=True)
class Record:
    """A decoded input record plus enough source context to audit it."""

    number: int
    text: str
    raw: str
    byte_length: int
    source_error: str | None = None


@dataclass
class Policy:
    """Fully resolved cleaning thresholds and feature switches for one run."""

    profile: str = "generic"
    min_characters: int = 5
    max_characters: int = 100_000
    min_script_ratio: float | None = None
    low_script_action: Action = "flag"
    max_unexpected_script_ratio: float = 0.10
    max_symbol_ratio: float = 0.40
    max_url_ratio: float = 0.30
    repeated_character_run: int = 15
    consecutive_word_run: int = 5
    max_repeated_word_ratio: float = 0.70
    min_unique_trigram_ratio: float = 0.35
    exact_dedup: bool = True
    near_dedup: bool = False
    near_duplicate_threshold: float = 0.85
    shingle_size: int = 3
    lsh_bands: int = 8
    lsh_rows: int = 4
    max_lsh_candidates: int = 1_000
    mask_pii: bool = True
    sample_limit: int = 5

    def to_dict(self) -> dict[str, Any]:
        """Serialize every resolved value so a run can be reproduced."""
        return asdict(self)


@dataclass
class RunResult:
    """Aggregate evidence written to both JSON and the human-readable report."""

    command: str
    input_path: str
    input_format: str
    policy: dict[str, Any]
    input_compression: str = "none"
    source_file_bytes: int = 0
    profile_details: dict[str, Any] = field(default_factory=dict)
    records_read: int = 0
    records_kept: int = 0
    records_transformed: int = 0
    records_rejected: int = 0
    findings_by_code: dict[str, int] = field(default_factory=dict)
    action_counts: dict[str, int] = field(default_factory=dict)
    examples_by_code: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    script_totals: dict[str, int] = field(default_factory=dict)
    script_ratio_buckets: dict[str, int] = field(default_factory=dict)
    script_threshold_preview: dict[str, dict[str, int | float]] = field(default_factory=dict)
    length_statistics: dict[str, float | int] = field(default_factory=dict)
    characters_read: int = 0
    bytes_read: int = 0
    emails_masked: int = 0
    phone_numbers_masked: int = 0
    deduplication_statistics: dict[str, int | float] = field(default_factory=dict)
    elapsed_seconds: float = 0.0
    throughput_records_per_second: float = 0.0
    reconciliation_ok: bool = False
    outputs: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert nested dataclass state into JSON-ready built-in types."""
        return asdict(self)
