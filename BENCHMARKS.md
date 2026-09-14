# Benchmarks

These numbers are validation evidence, not a universal performance claim.
Runtime depends on record length, storage, enabled detectors, and SQLite
performance.

## Full-corpus Kaggle methodology

The repository includes `benchmarks/kaggle_full_corpus.py`, the script used for
the final private Kaggle run on the raw Phase 1 Bengali and Nepali corpora from
Backup Plus. It produces four independently labeled workloads:

| Workload | Input coverage | Deduplication |
| --- | --- | --- |
| Bengali full exact | Every raw record | Disk-backed SHA-256 exact dedup |
| Nepali full exact | Every raw record | Disk-backed SHA-256 exact dedup |
| Bengali near sample | First 100,000 raw records | Exact + MinHash/LSH near dedup |
| Nepali near sample | First 100,000 raw records | Exact + MinHash/LSH near dedup |

The near-dedup workloads are intentionally not described as full-corpus runs.
They store shingles and LSH buckets and perform much more CPU and disk work per
record. LSH only proposes candidates; every removal is verified using exact
shingle Jaccard similarity. The Kaggle output records the input size, decoded
bytes, record counts, findings, dedup counters, throughput, configuration,
reconciliation result, Python/runtime details, and process peak memory.

The workloads use `analyze`, which executes the same normalization, heuristic,
policy, and deduplication decisions as `clean` but does not write tens of
gigabytes of accepted and rejected text into Kaggle's output volume. Clean-file
generation is covered separately by the end-to-end test suite.

Final Kaggle measurements will be added here from the generated JSON evidence;
no result will be estimated or copied from the older Phase 1 pipeline.

## Nepali Phase 1 pilot

- Input: 100,000 newline-delimited records from the project's real Nepali pilot
  corpus
- Input size: 63,217,399 bytes (63.2 MB decimal)
- Profile: `ne`
- Exact disk-backed deduplication: enabled
- Runtime: 12.819 seconds
- Throughput: 7,800.92 records/second
- Kept: 99,982
- Rejected: 18
- Findings: 11 broken-encoding, 6 word-spam, 1 character-spam
- Reconciliation: passed
- Environment: Python 3.12 on the developer's Apple laptop

This run led to a concrete optimization. The first implementation repeatedly
searched all configured Unicode ranges for every character and processed about
2,886 records/second. Caching the script classification of each Unicode
character increased measured throughput to roughly 7,800 records/second on the
same input while preserving identical findings.

The source corpus is not included in this repository. The small public fixture
under `examples/` exercises the same end-to-end path.

## Bengali near-deduplication validation

- Input: 4,977 records from the real Bengali Phase 1 sample (4.13 MB)
- Exact deduplication: enabled
- Near deduplication: enabled at Jaccard `0.85`
- LSH configuration: 32 MinHash values, 8 bands × 4 rows
- Runtime: 2.28 seconds
- LSH candidates verified with exact Jaccard: 4
- Near duplicates found: 0 (the input was already deduplicated)
- Reconciliation: passed

Detection itself is covered by integration tests containing known near pairs;
this already-cleaned sample validates that the optional stage operates on real
Bengali text without inventing matches.
