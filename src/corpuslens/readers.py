from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from .models import Record


def infer_format(path: Path, requested: str) -> str:
    if requested != "auto":
        return requested
    return "jsonl" if path.suffix.casefold() in {".jsonl", ".ndjson"} else "txt"


def iter_records(path: Path, input_format: str, text_field: str) -> Iterator[Record]:
    with path.open("rb") as handle:
        for number, raw_bytes in enumerate(handle, 1):
            raw_line = raw_bytes.decode("utf-8", errors="replace")
            raw = raw_line.rstrip("\r\n")
            if input_format == "txt":
                yield Record(number=number, text=raw, raw=raw, byte_length=len(raw_bytes))
                continue
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as error:
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
