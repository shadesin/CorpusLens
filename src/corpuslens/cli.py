from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .models import Policy
from .pipeline import run_pipeline
from .profiles import get_profile
from .readers import infer_format


def _load_config(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot load configuration {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError("Configuration must be a JSON object.")
    return value


def _policy(arguments: argparse.Namespace, config: dict[str, Any]) -> tuple[Policy, object]:
    profile_name = arguments.profile or config.get("profile", "generic")
    profile = get_profile(profile_name)
    allowed = set(Policy.__dataclass_fields__) - {"profile"}
    unknown = set(config) - allowed - {"profile"}
    if unknown:
        raise ValueError("Unknown configuration keys: " + ", ".join(sorted(unknown)))
    values = {key: value for key, value in config.items() if key in allowed}
    values["profile"] = profile.key
    if "min_script_ratio" not in values:
        values["min_script_ratio"] = profile.default_min_script_ratio
    overrides = {
        "min_characters": arguments.min_characters,
        "max_characters": arguments.max_characters,
        "min_script_ratio": arguments.min_script_ratio,
        "max_symbol_ratio": arguments.max_symbol_ratio,
        "sample_limit": arguments.sample_limit,
        "low_script_action": arguments.low_script_action,
    }
    values.update({key: value for key, value in overrides.items() if value is not None})
    if arguments.no_dedup:
        values["exact_dedup"] = False
    if arguments.no_mask_pii:
        values["mask_pii"] = False
    policy = Policy(**values)
    if policy.min_characters < 0 or policy.max_characters < policy.min_characters:
        raise ValueError("Character thresholds are inconsistent.")
    for name in ("min_script_ratio", "max_symbol_ratio"):
        value = getattr(policy, name)
        if value is not None and not 0 <= value <= 1:
            raise ValueError(f"{name} must be between 0 and 1.")
    if policy.low_script_action not in {"flag", "reject"}:
        raise ValueError("low_script_action must be 'flag' or 'reject'.")
    if policy.sample_limit < 0:
        raise ValueError("sample_limit cannot be negative.")
    return policy, profile


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="corpuslens", description="Audit text-corpus cleaning decisions before trusting them.")
    parser.add_argument("--version", action="version", version="CorpusLens 0.1.0")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("analyze", "clean"):
        child = subparsers.add_parser(command, help=("Report findings without writing a cleaned corpus." if command == "analyze" else "Apply a policy and write cleaned/rejected records."))
        child.add_argument("input", type=Path)
        child.add_argument("--output-dir", type=Path, default=None)
        child.add_argument("--format", choices=("auto", "txt", "jsonl"), default="auto")
        child.add_argument("--text-field", default="text", help="Text field for JSONL input.")
        child.add_argument("--profile", help="generic, bn/bengali, ne/nepali, hi, en, or ja")
        child.add_argument("--config", type=Path, help="JSON policy file. CLI options override it.")
        child.add_argument("--min-characters", type=int)
        child.add_argument("--max-characters", type=int)
        child.add_argument("--min-script-ratio", type=float)
        child.add_argument("--low-script-action", choices=("flag", "reject"), help="Flag by default; reject only when explicitly requested.")
        child.add_argument("--max-symbol-ratio", type=float)
        child.add_argument("--sample-limit", type=int)
        child.add_argument("--max-records", type=int, help="Stop after this many records; useful for a fast preview.")
        child.add_argument("--no-dedup", action="store_true")
        child.add_argument("--no-mask-pii", action="store_true")
        child.add_argument("--force", action="store_true", help="Overwrite CorpusLens output files in the selected directory.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        if not arguments.input.is_file():
            raise ValueError(f"Input file does not exist: {arguments.input}")
        config = _load_config(arguments.config)
        if arguments.max_records is not None and arguments.max_records < 1:
            raise ValueError("--max-records must be positive.")
        policy, profile = _policy(arguments, config)
        input_format = infer_format(arguments.input, arguments.format)
        output_dir = arguments.output_dir or Path(f"corpuslens-{arguments.command}-report")
        result = run_pipeline(
            arguments.input,
            output_dir,
            arguments.command,
            input_format,
            arguments.text_field,
            profile,
            policy,
            arguments.max_records,
            arguments.force,
            True,
        )
    except (OSError, TypeError, ValueError) as error:
        parser.exit(2, f"error: {error}\n")
    print(json.dumps({
        "records_read": result.records_read,
        "kept": result.records_kept,
        "rejected": result.records_rejected,
        "reconciliation_ok": result.reconciliation_ok,
        "outputs": result.outputs,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
