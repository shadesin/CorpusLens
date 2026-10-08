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

### Completed Kaggle measurements

All four workloads completed on Kaggle Linux with Python 3.12.13 and four
logical CPUs. The private input dataset was
`hailbipbap/corpuslens-full-corpus-benchmark`; the [private benchmark kernel](https://www.kaggle.com/code/hailbipbap/corpuslens-bengali-nepali-benchmark)
finished with no reported workload errors. These figures come from its
`benchmark-summary.json` and individual `report.json` files.

| Workload | Records read | Kept | Rejected | Exact duplicates | Verified near duplicates | Runtime | Throughput |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Bengali full exact | 41,004,792 | 19,342,812 | 21,661,980 | 1,115,568 | Not enabled | 15,729.6 s (4 h 22 m) | 2,606.85 records/s |
| Bengali near sample | 100,000 | 49,428 | 50,572 | 450 | 5 | 84.2 s | 1,187.76 records/s |
| Nepali full exact | 20,321,968 | 20,315,247 | 6,721 | 3,966 | Not enabled | 19,631.8 s (5 h 27 m) | 1,035.16 records/s |
| Nepali near sample | 100,000 | 99,980 | 20 | 0 | 2 | 132.5 s | 754.79 records/s |

The full Bengali scan read 15,992,871,652 bytes. Its raw file contained
20,502,396 empty physical lines, accounting for most rejections; the first
100,000-line near-dedup sample therefore contained only 50,000 nonempty
records. The full Nepali scan read 25,430,815,636 bytes. Every workload passed
the `records_read = records_kept + records_rejected` reconciliation check.

For the near-dedup samples, LSH proposed candidates and CorpusLens verified
them with exact shingle Jaccard at threshold `0.85`. It made 272 candidate
comparisons for Bengali and 122 for Nepali before removing 5 and 2 near
duplicates respectively. The samples are file prefixes, not random or
representative samples, and these counts must not be extrapolated to the
complete corpora.

The recorded process peak resident memory was 48.38 MiB. This measures the
Python process high-water mark across sequential workloads; it excludes the
temporary SQLite indexes, filesystem cache, and Kaggle's other processes.
Disk use was not measured. The raw corpora remain private because their
upstream usage conditions differ; the public repository contains the runner
and aggregate measurements only.

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
