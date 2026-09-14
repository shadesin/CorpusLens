"""Streaming readers for plain or gzip-compressed TXT and JSONL corpora."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Iterator

from .models import Record


def infer_format(path: Path, requested: str) -> str:
    """Infer record encoding from the filename while allowing an explicit override."""
    if requested != "auto":
        return requested
    # Remove only the compression suffix before inspecting the record-format
    # suffix, so ``data.jsonl.gz`` is inferred as JSONL rather than TXT.
    suffixes = [suffix.casefold() for suffix in path.suffixes]
    if suffixes and suffixes[-1] == ".gz":
        suffixes.pop()
    return "jsonl" if suffixes and suffixes[-1] in {".jsonl", ".ndjson"} else "txt"


def iter_records(path: Path, input_format: str, text_field: str) -> Iterator[Record]:
    """Yield one record at a time without loading the corpus into memory.

    Invalid UTF-8 is decoded with the replacement character so downstream
    detectors can reject it with evidence instead of aborting the whole run.
    For JSONL, ``raw`` preserves the original object for metadata-preserving
    clean output.
    """
    opener = gzip.open if path.suffix.casefold() == ".gz" else Path.open
    with opener(path, "rb") as handle:
        for number, raw_bytes in enumerate(handle, 1):
            raw_line = raw_bytes.decode("utf-8", errors="replace")
            raw = raw_line.rstrip("\r\n")
            if input_format == "txt":
                yield Record(number=number, text=raw, raw=raw, byte_length=len(raw_bytes))
                continue
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as error:
                # Malformed records are yielded as evidence. A single bad line
                # should not abort a multi-gigabyte corpus audit.
                yield Record(number=number, text="", raw=raw, byte_length=len(raw_bytes), source_error=f"invalid_json: {error.msg}")
                continue
            if not isinstance(value, dict):
                yield Record(number=number, text="", raw=raw, byte_length=len(raw_bytes), source_error="json_record_is_not_an_object")
                continue
            text = value.get(text_field)
            if not isinstance(text, str):
                yield Record(number=number, text="", raw=raw, byte_length=len(raw_bytes), source_error=f"missing_string_field:{text_field}")
                continue
            yield Record(number=number, text=text, raw=raw, byte_length=len(raw_bytes))
