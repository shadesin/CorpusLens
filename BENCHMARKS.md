# Benchmarks

These numbers are validation evidence, not a universal performance claim.
Runtime depends on record length, storage, enabled detectors, and SQLite
performance.

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
