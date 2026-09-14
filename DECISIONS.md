# Product and engineering decisions

## 1. Audit before cleaning

**Decision:** Provide separate `analyze` and `clean` commands.

**Rejected alternative:** A single command that immediately emits a cleaned
file.

**Why:** The highest-risk failure is a plausible rule silently deleting useful
language data. An audit must expose counts and representative examples before
the user commits to the policy.

## 2. Deterministic rules in the primary pipeline

**Decision:** Use transparent Unicode/statistical rules in version 0.1.

**Rejected alternative:** Send every record to an LLM for a binary quality
score.

**Why:** Per-record model scoring is expensive at corpus scale, is difficult to
reproduce across model versions, and performs unpredictably on low-resource
languages. Model scoring could later be an optional second-stage detector for
ambiguous records; it should not hide the primary decision process.

## 3. Disk-backed exact deduplication

**Decision:** Store SHA-256 digests in a SQLite primary-key table.

**Rejected alternative:** Store every digest in a Python `set`.

**Why:** A set is simpler and likely faster on small inputs, but its memory use
grows with the number of unique records. That contradicts the promise of
processing corpora larger than RAM. SQLite trades some throughput for bounded
application memory and exact results.

## 4. Script measurement is not language identification

**Decision:** Name and report the signal as target-script ratio.

**Rejected alternative:** Present the same number as language confidence.

**Why:** Devanagari does not distinguish Nepali from Hindi, and shared or mixed
scripts are common. Claiming language identity from Unicode blocks would be
misleading.

## 5. Low script ratio flags by default

**Decision:** Treat low expected-script coverage as `flag` unless the user
explicitly configures `reject`.

**Rejected alternative:** Automatically delete all records under a fixed
purity threshold.

**Why:** Technical writing, names, URLs, and conversational data often contain
legitimate code mixing. The appropriate policy depends on the model being
trained.

## 6. Retain all findings

**Decision:** Run all applicable detectors and attach every result to a rejected
record.

**Rejected alternative:** Stop at the first matched rule.

**Why:** First-match classification makes aggregate statistics dependent on
rule order and hides overlapping failures. Complete findings are more useful
for debugging policies and understanding the corpus.

## 7. Count Unicode categories correctly

**Decision:** Count only Unicode punctuation (`P*`) and symbol (`S*`)
categories in symbol density.

**Rejected alternative:** Treat every non-alphanumeric character as a symbol.

**Why:** Indic vowel signs are commonly Unicode marks (`M*`). The rejected
implementation classified normal Bengali spelling as junk and would have
removed a large fraction of valid data. This behavior is protected by a
regression test.

## 8. Bounded, reproducible descriptive statistics

**Decision:** Keep exact counts/min/max/mean and approximate quantiles from a
deterministic sample of at most 20,000 lengths.

**Rejected alternative:** Retain one statistics record for every corpus record.

**Why:** Full retention recreates the memory-scaling problem that streaming is
supposed to solve. Deterministic sampling keeps reruns comparable.
