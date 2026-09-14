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
git clone https://github.com/shadesin/CorpusLens.git
cd CorpusLens
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

Enable near-duplicate discovery when repeated documents differ only slightly:

```bash
corpuslens analyze corpus.txt \
  --profile bn \
  --near-dedup \
  --near-duplicate-threshold 0.85
```

An inspectable near-duplicate pair is included for a quick demonstration:

```bash
corpuslens analyze examples/near-duplicates.txt --profile bn --near-dedup
```

Near deduplication is optional because it is more computationally expensive
than exact hashing. Locality-sensitive hashing proposes likely pairs; CorpusLens
then computes exact shingle Jaccard similarity before rejecting a record.

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

Plain gzip compression is detected automatically, so `corpus.txt.gz`,
`dataset.jsonl.gz`, and `dataset.ndjson.gz` can be read without first creating a
large decompressed copy.

Use `--max-records 100000` for a fast representative audit before scanning a
large file.

CorpusLens refuses to overwrite an earlier report unless `--force` is supplied.

## Analyze your own corpus, step by step

### 1. Check the record format

CorpusLens treats one physical line as one record.

- TXT input contains one text sample per line.
- JSONL/NDJSON input contains one JSON object per line. Use `--text-field` when
  the text is stored under a key other than `text`.
- Either format may be gzip-compressed. The inner extension still determines
  the format, for example `articles.jsonl.gz`.

Pretty-printed JSON arrays and documents containing literal multi-line text are
not newline-delimited corpora and need to be converted first. Invalid UTF-8 and
malformed JSONL lines do not crash the scan: CorpusLens records them as rejected
examples in the report.

### 2. Choose a profile

Run `corpuslens profiles` to list the installed profiles. Use the language key
when one matches your data:

```bash
corpuslens analyze my-nepali-corpus.txt.gz --profile ne
```

Use `--profile generic` for an unsupported language or a deliberately
multilingual corpus. Universal heuristics and deduplication still run; only the
target-script measurement and localized phone patterns are omitted.

### 3. Preview before processing everything

Start with a representative prefix and a new output directory:

```bash
corpuslens analyze my-nepali-corpus.txt.gz \
  --profile ne \
  --max-records 100000 \
  --output-dir runs/nepali-preview
```

Open `runs/nepali-preview/report.html`. Check the finding counts, length
distribution, target-script threshold preview, and—most importantly—the
representative text under each finding. Finding counts can be larger than the
number rejected because CorpusLens deliberately keeps every applicable reason
for a record.

`analyze` applies the complete decision pipeline in dry-run form. Its “would
keep” and “would reject” numbers include exact or enabled near-duplicate
decisions, but it does not write the large cleaned and rejected corpora.

### 4. Adjust and save the policy

Start from `examples/bengali-policy.json` or copy the
`resolved-policy.json` produced by the preview. Edit the JSON and analyze again:

```bash
corpuslens analyze my-nepali-corpus.txt.gz \
  --config policies/nepali.json \
  --output-dir runs/nepali-policy-check
```

Command-line options override values from the JSON file. Script-ratio findings
are flags by default and therefore do not remove records. If reviewed examples
show that a cutoff is appropriate, opt into rejection explicitly with
`--low-script-action reject`.

### 5. Run the complete audit

Remove `--max-records` only after the preview looks sensible. Exact and near
deduplication use temporary SQLite indexes. For a very large corpus, point them
at a disk with sufficient free space:

```bash
corpuslens analyze my-nepali-corpus.txt.gz \
  --config policies/nepali.json \
  --work-dir /path/to/large-temporary-disk \
  --output-dir runs/nepali-full-audit
```

The work directory contains temporary state only and is cleaned automatically
after a successful run. Reports are written to `--output-dir`.

### 6. Produce cleaned data

Once the full report has been reviewed, change `analyze` to `clean` and use the
same policy:

```bash
corpuslens clean my-nepali-corpus.txt.gz \
  --config runs/nepali-full-audit/resolved-policy.json \
  --work-dir /path/to/large-temporary-disk \
  --output-dir runs/nepali-clean
```

Keep the report, resolved policy, and rejection log with the cleaned corpus.
Together they answer how many records were removed, why they were removed, and
which exact settings produced the result.

## Frequently used options

| Option | Purpose |
| --- | --- |
| `--format auto|txt|jsonl` | Override extension-based format detection |
| `--text-field FIELD` | Select the string field in JSONL objects |
| `--profile KEY` | Enable script-aware measurements and localized patterns |
| `--config POLICY.json` | Load a reusable cleaning policy |
| `--max-records N` | Audit only the first `N` records |
| `--no-dedup` | Disable exact deduplication |
| `--near-dedup` | Enable MinHash/LSH candidate search and verification |
| `--near-duplicate-threshold 0.85` | Set exact shingle-Jaccard removal threshold |
| `--work-dir PATH` | Place temporary SQLite indexes on a chosen disk |
| `--force` | Replace CorpusLens-owned files in an existing output directory |

Use `corpuslens analyze --help` for every threshold and LSH tuning option.
Near deduplication is intentionally opt-in because it consumes considerably
more CPU and temporary disk than exact hashing. For initial runs, keep the
default LSH parameters and change only the verified Jaccard threshold after
inspecting known pairs and false positives.

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
| Near duplicates using MinHash/LSH + exact Jaccard verification | Reject when enabled | Universal |
| Low expected-script ratio | **Flag** | Profile-aware |
| Unexpected-script contamination | **Flag** | Profile-aware |
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

List every installed profile with:

```bash
corpuslens profiles
```

Version 0.1 includes the following Indic profiles:

| Group | Languages |
| --- | --- |
| Widely represented | Bengali (`bn`), Gujarati (`gu`), Hindi (`hi`), Kannada (`kn`), Malayalam (`ml`), Marathi (`mr`), Odia (`or`), Punjabi (`pa`), Tamil (`ta`), Telugu (`te`), Urdu (`ur`) |
| Lower-resource | Assamese (`as`), Bhojpuri (`bho`), Bodo (`brx`), Dogri (`doi`), Konkani (`kok`), Maithili (`mai`), Manipuri/Meitei (`mni`), Mizo (`lus`), Nepali (`ne`), Sindhi (`sd`) |
| Additional Indic | Kashmiri (`ks`), Sanskrit (`sa`), Santali (`sat`) |

Profiles cover the scripts currently or historically relevant to these
languages, including Bengali-Assamese, Devanagari, Gujarati, Gurmukhi, Odia,
Tamil, Telugu, Kannada, Malayalam, Perso-Arabic, Meetei Mayek, Ol Chiki,
Kaithi, Tirhuta, Takri, and Khudawadi. Generic, English, and Japanese profiles
are also available.

“Profile support” means script-aware measurements, configurable thresholds,
and appropriate defaults. It does not mean that CorpusLens can distinguish
languages sharing a script or judge their semantic quality.

CorpusLens intentionally reports **target-script ratio**, not “language
probability.” Bengali script detection cannot distinguish Bengali from
Assamese, Devanagari cannot distinguish Hindi from Nepali or Bhojpuri, and a
Latin-script profile cannot distinguish Mizo from English. Optional language
identification can be added later as a separate signal.

## Why build another corpus cleaner?

Corpus-cleaning libraries and applications already exist. CorpusLens was not
built because filtering, deduplication, or Unicode analysis had never been
implemented before. It was built after preparing Bengali and Nepali training
corpora exposed a repeated workflow problem.

The available building blocks still left the researcher to join together
language-specific scripts, choose thresholds without seeing their consequences,
inspect rejected text manually, and reconstruct later why a record disappeared.
That burden is especially visible for lower-resource languages, where a default
developed for English—or even another language using the same script—can remove
valuable data without producing an obvious software error.

CorpusLens concentrates on that decision gap:

- every applicable finding is retained rather than only the first match;
- `analyze` is separated from the destructive cleaning decision;
- representative records make false positives inspectable;
- threshold previews show how many records fall below several possible
  target-script cutoffs before a user chooses one;
- the resolved policy travels with the output;
- exact deduplication is disk-backed rather than an unbounded Python set; and
- every run verifies `input = kept + rejected`.

The aim is not to replace every existing cleaning framework. It is to provide a
small, local, audit-first layer for researchers who otherwise end up with a
directory of one-off scripts and no reliable account of what those scripts
removed. Adapters for other dataset ecosystems can be added without changing
that purpose.

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
     ├── SQLite-backed exact deduplication
     └── optional disk-backed MinHash/LSH near deduplication
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
  "near_dedup": false,
  "near_duplicate_threshold": 0.85,
  "shingle_size": 3,
  "lsh_bands": 8,
  "lsh_rows": 4,
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

See [DECISIONS.md](DECISIONS.md) for the main product and engineering choices
and [BENCHMARKS.md](BENCHMARKS.md) for a 100,000-record real-corpus run.

## Current limitations

- Input records are newline-delimited TXT or JSONL; multi-line document formats
  need an adapter.
- Script ratios are descriptive signals, not language identification.
- Near deduplication uses probabilistic LSH candidate discovery, followed by
  exact Jaccard verification. Candidate searches are bounded to avoid
  pathological buckets, so the process can miss some near duplicates.
- Quantiles are approximate after 20,000 records, although min, max, mean,
  counts, and reconciliation remain exact.
- PII detection covers email plus profile-specific phone formats, not every
  kind of personal information.
- Deterministic rules cannot judge semantic quality, factuality, toxicity, or
  translationese.

## License

MIT
