"""Run the reproducible Bengali/Nepali CorpusLens benchmark on Kaggle.

The companion Kaggle dataset contains the two gzip-compressed raw corpora and
``corpuslens-source.zip``. The archive is unpacked at runtime so the benchmark
uses the exact repository snapshot uploaded with its inputs, without enabling
network access or installing an unpublished package.

Two workloads are deliberately reported separately:

* ``full_exact`` scans every record with heuristics and exact SHA-256 dedup.
* ``near_100k`` enables MinHash/LSH on the first 100,000 records. Near dedup is
  substantially more expensive per record, so calling this a full-corpus run
  would be misleading.
"""

from __future__ import annotations

import json
import os
import platform
import resource
import shutil
import sys
import time
import traceback
from pathlib import Path


DATASET_NAME = "corpuslens-full-corpus-benchmark"
NEAR_DEDUP_RECORDS = 100_000


def _prepare_source(dataset_root: Path, working_root: Path) -> None:
    """Unpack the pinned CorpusLens source snapshot and make it importable."""
    source_root = working_root / "source"
    shutil.unpack_archive(dataset_root / "corpuslens-source.zip", source_root)
    sys.path.insert(0, str(source_root / "src"))


def _write_json(value: object, path: Path) -> None:
    """Persist progress after every workload so partial evidence survives."""
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _run_workload(
    *,
    name: str,
    input_path: Path,
    profile_key: str,
    near_dedup: bool,
    max_records: int | None,
    output_root: Path,
    index_root: Path,
) -> dict[str, object]:
    """Execute one isolated audit and return its report plus environment data."""
    from corpuslens.models import Policy
    from corpuslens.pipeline import run_pipeline
    from corpuslens.profiles import get_profile

    started = time.perf_counter()
    report = run_pipeline(
        input_path=input_path,
        output_dir=output_root / name,
        command="analyze",
        input_format="txt",
        text_field="text",
        profile=get_profile(profile_key),
        policy=Policy(profile=profile_key, near_dedup=near_dedup),
        max_records=max_records,
        overwrite=True,
        show_progress=True,
        work_dir=index_root,
    ).to_dict()
    return {
        "workload": name,
        "wall_seconds_including_report_writes": round(time.perf_counter() - started, 3),
        "max_records": max_records,
        # On Kaggle's Linux runtime ru_maxrss is reported in KiB. It is a
        # process-wide high-water mark, so later workloads may repeat the peak.
        "process_peak_rss_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2),
        "report": report,
    }


def main() -> int:
    """Locate Kaggle inputs, run all workloads sequentially, and save evidence."""
    dataset_root = Path("/kaggle/input") / DATASET_NAME
    working_root = Path("/kaggle/working")
    result_root = working_root / "corpuslens-benchmark-results"
    index_root = working_root / "corpuslens-temporary-indexes"
    result_root.mkdir(parents=True, exist_ok=True)
    index_root.mkdir(parents=True, exist_ok=True)
    _prepare_source(dataset_root, working_root)

    environment = {
        "platform": platform.platform(),
        "python": sys.version,
        "logical_cpu_count": os.cpu_count(),
        "dataset": DATASET_NAME,
        "near_dedup_sample_records": NEAR_DEDUP_RECORDS,
    }
    summary: dict[str, object] = {"environment": environment, "workloads": [], "errors": []}
    summary_path = result_root / "benchmark-summary.json"
    _write_json(summary, summary_path)

    corpora = (
        ("bengali", dataset_root / "bengali_raw.txt.gz", "bn"),
        ("nepali", dataset_root / "nepali_raw.txt.gz", "ne"),
    )
    for language, input_path, profile_key in corpora:
        for suffix, near_dedup, max_records in (
            ("full_exact", False, None),
            ("near_100k", True, NEAR_DEDUP_RECORDS),
        ):
            name = f"{language}_{suffix}"
            print(f"\n=== Starting {name} ===", flush=True)
            try:
                workload = _run_workload(
                    name=name,
                    input_path=input_path,
                    profile_key=profile_key,
                    near_dedup=near_dedup,
                    max_records=max_records,
                    output_root=result_root,
                    index_root=index_root,
                )
                summary["workloads"].append(workload)
            except Exception as error:  # Keep later workloads and diagnostics.
                traceback.print_exc()
                summary["errors"].append({"workload": name, "error": repr(error)})
            _write_json(summary, summary_path)

    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
