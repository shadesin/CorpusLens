"""Command-line interface and policy validation for CorpusLens."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .models import Policy
from .pipeline import run_pipeline
from .profiles import ALIASES, PROFILES, LanguageProfile, get_profile
from .readers import infer_format


def _load_config(path: Path | None) -> dict[str, Any]:
    """Load an optional policy object and turn parse failures into CLI errors."""
    if path is None:
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot load configuration {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError("Configuration must be a JSON object.")
    return value


def _policy(arguments: argparse.Namespace, config: dict[str, Any]) -> tuple[Policy, LanguageProfile]:
    """Resolve defaults, JSON configuration, and CLI overrides into a policy."""
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
    # Explicit command-line values have the highest precedence. ``None`` means
    # the option was omitted and must not erase a value from the JSON policy.
    overrides = {
        "min_characters": arguments.min_characters,
        "max_characters": arguments.max_characters,
        "min_script_ratio": arguments.min_script_ratio,
        "max_symbol_ratio": arguments.max_symbol_ratio,
        "max_unexpected_script_ratio": arguments.max_unexpected_script_ratio,
        "sample_limit": arguments.sample_limit,
        "low_script_action": arguments.low_script_action,
        "near_duplicate_threshold": arguments.near_duplicate_threshold,
        "shingle_size": arguments.shingle_size,
        "lsh_bands": arguments.lsh_bands,
        "lsh_rows": arguments.lsh_rows,
        "max_lsh_candidates": arguments.max_lsh_candidates,
    }
    values.update({key: value for key, value in overrides.items() if value is not None})
    if arguments.no_dedup:
        values["exact_dedup"] = False
    if arguments.near_dedup:
        values["near_dedup"] = True
    if arguments.no_mask_pii:
        values["mask_pii"] = False
    policy = Policy(**values)
    integer_fields = (
        "min_characters", "max_characters", "repeated_character_run",
        "consecutive_word_run", "sample_limit", "shingle_size", "lsh_bands",
        "lsh_rows", "max_lsh_candidates",
    )
    for name in integer_fields:
        value = getattr(policy, name)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer.")
    for name in ("exact_dedup", "near_dedup", "mask_pii"):
        if not isinstance(getattr(policy, name), bool):
            raise ValueError(f"{name} must be true or false.")
    if policy.min_characters < 0 or policy.max_characters < policy.min_characters:
        raise ValueError("Character thresholds are inconsistent.")
    for name in (
        "min_script_ratio", "max_symbol_ratio", "max_unexpected_script_ratio", "max_url_ratio",
        "max_repeated_word_ratio", "min_unique_trigram_ratio", "near_duplicate_threshold",
    ):
        value = getattr(policy, name)
        if value is not None:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be numeric.")
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1.")
    if policy.low_script_action not in {"flag", "reject"}:
        raise ValueError("low_script_action must be 'flag' or 'reject'.")
    if policy.sample_limit < 0:
        raise ValueError("sample_limit cannot be negative.")
    if policy.repeated_character_run < 2 or policy.consecutive_word_run < 2:
        raise ValueError("Repetition run thresholds must be at least 2.")
    if min(policy.shingle_size, policy.lsh_bands, policy.lsh_rows, policy.max_lsh_candidates) < 1:
        raise ValueError("Near-deduplication sizes must be positive.")
    if policy.near_duplicate_threshold <= 0:
        raise ValueError("near_duplicate_threshold must be greater than 0.")
    return policy, profile


def build_parser() -> argparse.ArgumentParser:
    """Construct the public CLI shared by the console script and tests."""
    parser = argparse.ArgumentParser(prog="corpuslens", description="Audit text-corpus cleaning decisions before trusting them.")
    parser.add_argument("--version", action="version", version="CorpusLens 0.1.0")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("profiles", help="List available language/script profiles.")
    for command in ("analyze", "clean"):
        child = subparsers.add_parser(command, help=("Report findings without writing a cleaned corpus." if command == "analyze" else "Apply a policy and write cleaned/rejected records."))
        child.add_argument("input", type=Path)
        child.add_argument("--output-dir", type=Path, default=None)
        child.add_argument("--format", choices=("auto", "txt", "jsonl"), default="auto")
        child.add_argument("--text-field", default="text", help="Text field for JSONL input.")
        child.add_argument(
            "--profile",
            choices=sorted(set(PROFILES) | set(ALIASES)),
            help="Language/script profile. Run `corpuslens profiles` to list them.",
        )
        child.add_argument("--config", type=Path, help="JSON policy file. CLI options override it.")
        child.add_argument("--min-characters", type=int)
        child.add_argument("--max-characters", type=int)
        child.add_argument("--min-script-ratio", type=float)
        child.add_argument("--low-script-action", choices=("flag", "reject"), help="Flag by default; reject only when explicitly requested.")
        child.add_argument("--max-symbol-ratio", type=float)
        child.add_argument("--max-unexpected-script-ratio", type=float)
        child.add_argument("--sample-limit", type=int)
        child.add_argument("--max-records", type=int, help="Stop after this many records; useful for a fast preview.")
        child.add_argument("--no-dedup", action="store_true")
        child.add_argument("--near-dedup", action="store_true", help="Enable MinHash/LSH near-deduplication.")
        child.add_argument("--near-duplicate-threshold", type=float)
        child.add_argument("--shingle-size", type=int)
        child.add_argument("--lsh-bands", type=int)
        child.add_argument("--lsh-rows", type=int)
        child.add_argument("--max-lsh-candidates", type=int)
        child.add_argument("--no-mask-pii", action="store_true")
        child.add_argument(
            "--work-dir",
            type=Path,
            help="Parent directory for temporary SQLite indexes; choose a disk with ample free space.",
        )
        child.add_argument("--force", action="store_true", help="Overwrite CorpusLens output files in the selected directory.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, execute one command, and return a shell exit status."""
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command == "profiles":
        for key, profile in PROFILES.items():
            scripts = ", ".join(profile.target_scripts) or "unrestricted"
            print(f"{key:8} {profile.name:20} {scripts}")
        return 0
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
            input_path=arguments.input,
            output_dir=output_dir,
            command=arguments.command,
            input_format=input_format,
            text_field=arguments.text_field,
            profile=profile,
            policy=policy,
            max_records=arguments.max_records,
            overwrite=arguments.force,
            show_progress=True,
            work_dir=arguments.work_dir,
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
