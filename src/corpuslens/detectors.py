from __future__ import annotations

import re
import unicodedata
from collections import Counter

from .models import Finding, Policy
from .profiles import COMMON_BOILERPLATE, LanguageProfile, character_script


URL_RE = re.compile(r"(?:https?://|www\.|\b\w+\.(?:com|org|net|info|biz)\b)", re.IGNORECASE)
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
MOJIBAKE_RE = re.compile(r"(?:\ufffd|Ã.|Â.|â€|ðŸ)")
WORD_RE = re.compile(r"\S+")


def normalize_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def script_counts(text: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for character in text:
        category = unicodedata.category(character)
        if category[0] not in {"L", "M"}:
            continue
        counts[character_script(character)] += 1
    return counts


def target_script_ratio(text: str, profile: LanguageProfile) -> float | None:
    if not profile.target_scripts:
        return None
    counts = script_counts(text)
    denominator = sum(counts.values())
    if denominator == 0:
        return 0.0
    return sum(counts[script] for script in profile.target_scripts) / denominator


def symbol_ratio(text: str) -> float:
    characters = [character for character in text if not character.isspace()]
    if not characters:
        return 0.0
    symbols = sum(unicodedata.category(character)[0] in {"P", "S"} for character in characters)
    return symbols / len(characters)


def repetition_findings(text: str, policy: Policy) -> list[Finding]:
    findings: list[Finding] = []
    if len(text) >= 20:
        run_re = re.compile(rf"(.)\1{{{max(policy.repeated_character_run - 1, 1)},}}", re.DOTALL)
        longest = max((len(match.group(0)) for match in run_re.finditer(text)), default=0)
        if longest and longest / len(text) >= 0.10:
            findings.append(Finding("character_spam", "reject", "A single character repeats pathologically.", longest, policy.repeated_character_run))

    words = WORD_RE.findall(text.casefold())
    longest_word_run = 1 if words else 0
    current_run = 1
    for index in range(1, len(words)):
        current_run = current_run + 1 if words[index] == words[index - 1] else 1
        longest_word_run = max(longest_word_run, current_run)
    if longest_word_run >= policy.consecutive_word_run:
        findings.append(Finding("word_spam", "reject", "The same word repeats consecutively.", longest_word_run, policy.consecutive_word_run))

    if len(words) >= 20:
        counts = Counter(words)
        repeated = sum(count - 1 for count in counts.values() if count > 1) / len(words)
        if repeated >= policy.max_repeated_word_ratio:
            findings.append(Finding("high_word_repetition", "reject", "Most words are repetitions.", round(repeated, 4), policy.max_repeated_word_ratio))
        trigrams = [tuple(words[index:index + 3]) for index in range(len(words) - 2)]
        unique_ratio = len(set(trigrams)) / len(trigrams)
        if len(trigrams) >= 20 and unique_ratio < policy.min_unique_trigram_ratio:
            findings.append(Finding("repeated_ngram", "reject", "The record repeats the same word sequences.", round(unique_ratio, 4), policy.min_unique_trigram_ratio))
    return findings


def inspect_text(text: str, profile: LanguageProfile, policy: Policy, source_error: str | None = None) -> tuple[list[Finding], dict[str, int], float | None]:
    findings: list[Finding] = []
    if source_error:
        findings.append(Finding("malformed_record", "reject", source_error))
    if not text:
        findings.append(Finding("empty", "reject", "The normalized record is empty."))
        return findings, {}, target_script_ratio(text, profile)
    if len(text) < policy.min_characters:
        findings.append(Finding("too_short", "reject", "The record is shorter than the configured minimum.", len(text), policy.min_characters))
    if len(text) > policy.max_characters:
        findings.append(Finding("too_long", "reject", "The record exceeds the configured maximum.", len(text), policy.max_characters))

    counts = script_counts(text)
    ratio = target_script_ratio(text, profile)
    if ratio is not None and policy.min_script_ratio is not None and ratio < policy.min_script_ratio:
        findings.append(Finding("low_target_script_ratio", policy.low_script_action, f"Too little text uses the expected {', '.join(profile.target_scripts)} script.", round(ratio, 4), policy.min_script_ratio))

    ratio_symbols = symbol_ratio(text)
    if len(text) >= 50 and ratio_symbols > policy.max_symbol_ratio:
        findings.append(Finding("high_symbol_ratio", "reject", "Punctuation and symbols dominate the record.", round(ratio_symbols, 4), policy.max_symbol_ratio))
    if MOJIBAKE_RE.search(text):
        findings.append(Finding("broken_encoding", "reject", "The record contains replacement characters or common mojibake sequences."))

    lowered = text.casefold()
    markers = tuple(COMMON_BOILERPLATE) + profile.boilerplate_markers
    marker_count = sum(marker in lowered for marker in markers)
    if marker_count >= 2:
        findings.append(Finding("boilerplate", "reject", "The record contains multiple webpage boilerplate markers.", marker_count, 2))
    urls = URL_RE.findall(text)
    url_ratio = sum(len(url) for url in urls) / len(text) if text else 0.0
    if len(urls) >= 5 or (urls and url_ratio > policy.max_url_ratio):
        findings.append(Finding("url_spam", "reject", "URLs occupy too much of the record.", round(url_ratio, 4), policy.max_url_ratio))
    findings.extend(repetition_findings(text, policy))
    if policy.mask_pii and EMAIL_RE.search(text):
        findings.append(Finding("email_detected", "transform", "Email addresses will be masked."))
    if policy.mask_pii and any(re.search(pattern, text) for pattern in profile.phone_patterns):
        findings.append(Finding("phone_detected", "transform", "Phone numbers will be masked."))
    return findings, dict(counts), ratio


def mask_pii(text: str, profile: LanguageProfile) -> tuple[str, int, int]:
    masked, emails = EMAIL_RE.subn("<EMAIL>", text)
    phones = 0
    for pattern in profile.phone_patterns:
        masked, count = re.subn(pattern, "<PHONE>", masked)
        phones += count
    return masked, emails, phones
