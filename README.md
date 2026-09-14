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

See [DECISIONS.md](DECISIONS.md) for the main product and engineering choices
and [BENCHMARKS.md](BENCHMARKS.md) for a 100,000-record real-corpus run.

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
