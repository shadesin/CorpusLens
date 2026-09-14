from __future__ import annotations

import json
import math
import random
import tempfile
import time
import sys
from collections import Counter
from pathlib import Path

from .dedup import ExactDeduplicator, NearDeduplicator
from .detectors import inspect_text, mask_pii, normalize_text
from .models import Finding, Policy, RunResult
from .profiles import LanguageProfile
from .readers import iter_records
from .reporting import write_html_report, write_json_report


SCRIPT_THRESHOLDS = (0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90)


class LengthSketch:
    """Deterministic bounded sample used for approximate quantiles."""

    def __init__(self, limit: int = 20_000):
        self.limit = limit
        self.values: list[int] = []
        self.count = 0
        self.minimum: int | None = None
        self.maximum: int | None = None
        self.total = 0
        self.random = random.Random(0)

    def add(self, value: int) -> None:
        self.count += 1
        self.total += value
        self.minimum = value if self.minimum is None else min(self.minimum, value)
        self.maximum = value if self.maximum is None else max(self.maximum, value)
        if len(self.values) < self.limit:
            self.values.append(value)
        else:
            # Seeded reservoir sampling keeps memory bounded and reruns reproducible.
            slot = self.random.randrange(self.count)
            if slot < self.limit:
                self.values[slot] = value

    def summary(self) -> dict[str, float | int]:
        if not self.count:
            return {"count": 0}
        ordered = sorted(self.values)

        def percentile(fraction: float) -> float:
            position = (len(ordered) - 1) * fraction
            lower = math.floor(position)
            upper = math.ceil(position)
            if lower == upper:
                return float(ordered[lower])
            return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)

        return {
            "count": self.count,
            "minimum": self.minimum or 0,
            "p05_approx": round(percentile(0.05), 2),
            "median_approx": round(percentile(0.50), 2),
            "p95_approx": round(percentile(0.95), 2),
            "p99_approx": round(percentile(0.99), 2),
            "maximum": self.maximum or 0,
            "mean": round(self.total / self.count, 2),
            "quantile_sample_size": len(ordered),
        }


def _ratio_bucket(ratio: float) -> str:
    upper = min(100, (int(ratio * 10) + 1) * 10)
    lower = max(0, upper - 10)
    return f"{lower:02d}-{upper:02d}%"


def run_pipeline(
    input_path: Path,
    output_dir: Path,
    command: str,
    input_format: str,
    text_field: str,
    profile: LanguageProfile,
    policy: Policy,
    max_records: int | None = None,
    overwrite: bool = False,
    show_progress: bool = False,
) -> RunResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    result = RunResult(
        command=command,
        input_path=str(input_path),
        input_format=input_format,
        policy=policy.to_dict(),
        profile_details={
            "name": profile.name,
            "target_scripts": list(profile.target_scripts),
            "allowed_secondary_scripts": list(profile.allowed_secondary_scripts),
        },
    )
    findings_count: Counter[str] = Counter()
    action_count: Counter[str] = Counter()
    scripts: Counter[str] = Counter()
    ratio_buckets: Counter[str] = Counter()
    threshold_counts: Counter[str] = Counter()
    ratios_observed = 0
    examples: dict[str, list[dict[str, object]]] = {}
    lengths = LengthSketch()
    started = time.perf_counter()

    cleaned_path = output_dir / ("cleaned.jsonl" if input_format == "jsonl" else "cleaned.txt")
    rejected_path = output_dir / "rejected.jsonl"
    target_paths = [output_dir / "report.json", output_dir / "report.html", output_dir / "resolved-policy.json"]
    if command == "clean":
        target_paths.extend((cleaned_path, rejected_path))
    existing = [path for path in target_paths if path.exists()]
    if existing and not overwrite:
        raise ValueError("Refusing to overwrite existing outputs: " + ", ".join(str(path) for path in existing))
    cleaned_handle = cleaned_path.open("w", encoding="utf-8") if command == "clean" else None
    rejected_handle = rejected_path.open("w", encoding="utf-8") if command == "clean" else None

    with tempfile.TemporaryDirectory(prefix="corpuslens-") as temp_dir:
        deduplicator = ExactDeduplicator(Path(temp_dir) / "exact.sqlite3") if policy.exact_dedup else None
        near_deduplicator = NearDeduplicator(
            Path(temp_dir) / "near.sqlite3",
            threshold=policy.near_duplicate_threshold,
            shingle_size=policy.shingle_size,
            bands=policy.lsh_bands,
            rows=policy.lsh_rows,
            max_candidates=policy.max_lsh_candidates,
        ) if policy.near_dedup else None
        try:
            for record in iter_records(input_path, input_format, text_field):
                if max_records is not None and result.records_read >= max_records:
                    break
                result.records_read += 1
                result.bytes_read += record.byte_length
                if show_progress and result.records_read % 100_000 == 0:
                    elapsed = time.perf_counter() - started
                    total_bytes = input_path.stat().st_size
                    percentage = result.bytes_read / total_bytes * 100 if total_bytes else 100.0
                    rate = result.records_read / elapsed if elapsed else 0.0
                    print(f"\r{percentage:5.1f}% | {result.records_read:,} records | {rate:,.0f} records/s", end="", file=sys.stderr, flush=True)
                normalized = normalize_text(record.text)
                result.characters_read += len(normalized)
                lengths.add(len(normalized))
                findings, record_scripts, script_ratio = inspect_text(normalized, profile, policy, record.source_error)
                scripts.update(record_scripts)
                if script_ratio is not None:
                    ratios_observed += 1
                    ratio_buckets[_ratio_bucket(script_ratio)] += 1
                    for threshold in SCRIPT_THRESHOLDS:
                        if script_ratio < threshold:
                            threshold_counts[f"{threshold:.2f}"] += 1
                has_rejection = any(finding.action == "reject" for finding in findings)
                if deduplicator is not None and normalized and record.source_error is None and not has_rejection:
                    first_record = deduplicator.observe(normalized, record.number)
                    if first_record is not None:
                        findings.append(Finding("exact_duplicate", "reject", "The normalized record was seen earlier.", first_record, "first_record"))
                        has_rejection = True
                if near_deduplicator is not None and normalized and record.source_error is None and not has_rejection:
                    match = near_deduplicator.observe(normalized, record.number)
                    if match is not None:
                        findings.append(Finding(
                            "near_duplicate",
                            "reject",
                            f"The record is near-duplicate of retained record {match.first_record}.",
                            round(match.similarity, 4),
                            policy.near_duplicate_threshold,
                        ))

                for finding in findings:
                    findings_count[finding.code] += 1
                    action_count[finding.action] += 1
                    bucket = examples.setdefault(finding.code, [])
                    if len(bucket) < policy.sample_limit:
                        bucket.append({"record": record.number, "text": normalized[:500], "finding": finding.to_dict()})

                rejected = any(finding.action == "reject" for finding in findings)
                if rejected:
                    result.records_rejected += 1
                    if rejected_handle is not None:
                        rejected_handle.write(json.dumps({
                            "record": record.number,
                            "text": normalized,
                            "findings": [finding.to_dict() for finding in findings],
                        }, ensure_ascii=False) + "\n")
                    continue

                output_text = normalized
                transformed = False
                if policy.mask_pii:
                    output_text, emails, phones = mask_pii(output_text, profile)
                    result.emails_masked += emails
                    result.phone_numbers_masked += phones
                    transformed = bool(emails or phones)
                if transformed:
                    result.records_transformed += 1
                result.records_kept += 1
                if cleaned_handle is not None:
                    if input_format == "jsonl":
                        output_record = json.loads(record.raw)
                        output_record[text_field] = output_text
                        cleaned_handle.write(json.dumps(output_record, ensure_ascii=False) + "\n")
                    else:
                        cleaned_handle.write(output_text + "\n")
        finally:
            if deduplicator is not None:
                deduplicator.close()
            result.deduplication_statistics = {
                "exact_dedup_enabled": int(policy.exact_dedup),
                "near_dedup_enabled": int(policy.near_dedup),
            }
            if near_deduplicator is not None:
                result.deduplication_statistics.update(near_deduplicator.statistics())
                near_deduplicator.close()
            if cleaned_handle is not None:
                cleaned_handle.close()
            if rejected_handle is not None:
                rejected_handle.close()

    result.findings_by_code = dict(findings_count.most_common())
    if show_progress and result.records_read >= 100_000:
        print(file=sys.stderr)
    result.action_counts = dict(action_count)
    result.examples_by_code = examples
    result.script_totals = dict(scripts.most_common())
    result.script_ratio_buckets = dict(sorted(ratio_buckets.items()))
    for threshold in SCRIPT_THRESHOLDS:
        key = f"{threshold:.2f}"
        count = threshold_counts[key]
        result.script_threshold_preview[key] = {
            "records_below": count,
            "percentage": round(count / ratios_observed * 100, 3) if ratios_observed else 0.0,
        }
    result.length_statistics = lengths.summary()
    result.elapsed_seconds = round(time.perf_counter() - started, 3)
    result.throughput_records_per_second = round(result.records_read / result.elapsed_seconds, 2) if result.elapsed_seconds else 0.0
    result.reconciliation_ok = result.records_read == result.records_kept + result.records_rejected
    json_path = output_dir / "report.json"
    html_path = output_dir / "report.html"
    policy_path = output_dir / "resolved-policy.json"
    result.outputs = {"json_report": str(json_path), "html_report": str(html_path), "resolved_policy": str(policy_path)}
    if command == "clean":
        result.outputs.update({"cleaned_corpus": str(cleaned_path), "rejected_records": str(rejected_path)})
    report = result.to_dict()
    write_json_report(policy.to_dict(), policy_path)
    write_json_report(report, json_path)
    write_html_report(report, html_path)
    return result
