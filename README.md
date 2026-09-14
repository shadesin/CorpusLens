# CorpusLens

**Audit corpus-cleaning decisions before trusting them.**

CorpusLens is a streaming command-line tool for people preparing text datasets
for language-model training. It explains what a cleaning policy would remove,
shows representative failures, and records every decision in a reproducible
report. It can then apply the same policy to produce a cleaned corpus and a
machine-readable rejection log.

The problem is not that text cannot be filtered with Python. The problem is
that a filter can run successfully while silently deleting useful data.
CorpusLens makes those decisions visible.

## Quick start

CorpusLens has no runtime dependencies and requires Python 3.10 or newer.

```bash
git clone https://github.com/YOUR_USERNAME/corpuslens.git
cd corpuslens
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Audit the included mixed-quality sample without creating a cleaned corpus:

```bash
corpuslens analyze examples/sample.txt \
  --profile bn \
  --output-dir corpuslens-analyze-report
```

Open `corpuslens-analyze-report/report.html` to inspect the result.

Apply a reviewed policy:

```bash
corpuslens clean examples/sample.txt \
  --config examples/bengali-policy.json \
  --output-dir corpuslens-clean-report
```

The clean run creates:

```text
corpuslens-clean-report/
├── cleaned.txt           normalized, accepted records (`cleaned.jsonl` for JSONL)
├── rejected.jsonl        rejected records and every applicable finding
├── report.html           portable report for human review
├── report.json           complete machine-readable run manifest
└── resolved-policy.json  exact policy used by the run
```

JSONL input is also supported:

```bash
corpuslens analyze dataset.jsonl --format jsonl --text-field content
```

When cleaning JSONL, CorpusLens preserves the complete object and replaces only
the configured text field with its normalized or masked value.

Use `--max-records 100000` for a fast representative audit before scanning a
large file.

CorpusLens refuses to overwrite an earlier report unless `--force` is supplied.

## What it detects

| Check | Default decision | Scope |
| --- | --- | --- |
| Empty or malformed records | Reject | Universal |
| Abnormal length | Reject | Universal |
| Broken Unicode/mojibake indicators | Reject | Universal |
| High punctuation/symbol density | Reject | Universal |
| URL-heavy text and boilerplate | Reject | Universal/profile-aware |
| Character, word, and n-gram repetition | Reject | Universal |
| Exact duplicates after NFC normalization | Reject | Universal |
| Low expected-script ratio | **Flag** | Profile-aware |
| Email and supported phone patterns | Transform/mask | Universal/profile-aware |

Low expected-script ratio is deliberately a flag by default. Code-mixed text
can be valuable, and script ranges are not language identification. Make it a
rejection only after reviewing examples:

```bash
corpuslens clean corpus.txt \
  --profile bn \
  --min-script-ratio 0.40 \
  --low-script-action reject
```

## Language support

Universal checks work without selecting a language:

```bash
corpuslens analyze corpus.txt --profile generic
```

Version 0.1 ships with profiles for Bengali (`bn`), Nepali (`ne`), Hindi
(`hi`), English (`en`), and Japanese (`ja`). Profiles define expected scripts,
permitted secondary scripts, default thresholds, local boilerplate, and phone
patterns. The generic analyzer also reports several other Unicode scripts.

CorpusLens intentionally reports **Bengali-script ratio**, not “probability
that this is Bengali.” Bengali script detection cannot prove language, just as
Devanagari alone cannot distinguish Nepali from Hindi.

## Why not just use Hugging Face Datasets?

Hugging Face Datasets is a useful ingestion and transformation layer.
CorpusLens addresses a different question: *what did this cleaning policy
remove, why, and can the decision be reproduced?*

It adds an opinionated audit layer:

- every applicable finding is retained rather than only the first match;
- `analyze` is separated from the destructive cleaning decision;
- representative records make false positives inspectable;
- the resolved policy travels with the output;
- exact deduplication is disk-backed rather than an unbounded Python set; and
- every run verifies `input = kept + rejected`.

Hugging Face dataset ingestion is a planned adapter, not a competing goal.

## Architecture

```text
TXT / JSONL
     │
     ▼
Streaming reader ── malformed-record findings
     │
     ▼
NFC + whitespace normalization
     │
     ├── universal detectors
     ├── language/script profile
     └── SQLite-backed exact deduplication
     │
     ▼
Policy: flag / transform / reject
     │
     ├── cleaned text
     ├── rejected JSONL with all reasons
     └── JSON + self-contained HTML reports
```

Records are processed one at a time. Exact hashes live in SQLite, and quantile
statistics use a deterministic bounded sample. The application therefore does
not need to hold the corpus or all unique hashes in RAM.

## Reproducible policy

Policies are ordinary JSON:

```json
{
  "profile": "bn",
  "min_characters": 5,
  "max_characters": 100000,
  "min_script_ratio": 0.2,
  "low_script_action": "flag",
  "max_symbol_ratio": 0.4,
  "exact_dedup": true,
  "mask_pii": true
}
```

CLI values override the configuration. The fully resolved policy is always
written to the output directory.

## Tests

```bash
python -m unittest discover -s tests -v
```

The suite includes a regression test for a real failure mode: Bengali vowel
signs are Unicode marks, not punctuation. A naive “not alphanumeric means
symbol” rule can therefore misclassify normal Bengali as symbol-heavy junk.

## Origin

CorpusLens grew out of preparing large Bengali and Nepali corpora for language
model training. That work required separate scripts for normalization,
heuristic filtering, exact and near deduplication, rejection auditing, and
manifest reconciliation. The repeated code and manual threshold inspection
revealed a broader product problem: corpus cleaning needed to be inspectable
and reproducible, not just executable.

See [DECISIONS.md](DECISIONS.md) for the main product and engineering choices,
[AI_USAGE.md](AI_USAGE.md) for how AI was used during development, and
[BENCHMARKS.md](BENCHMARKS.md) for a 100,000-record real-corpus run.

## Current limitations

- Input records are newline-delimited TXT or JSONL; multi-line document formats
  need an adapter.
- Script ratios are descriptive signals, not language identification.
- Exact deduplication is implemented; semantic/near deduplication is not yet in
  the productized pipeline.
- Quantiles are approximate after 20,000 records, although min, max, mean,
  counts, and reconciliation remain exact.
- PII detection covers email plus profile-specific phone formats, not every
  kind of personal information.
- Deterministic rules cannot judge semantic quality, factuality, toxicity, or
  translationese.

## License

MIT
