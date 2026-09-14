"""Language profiles and Unicode script ranges used by profile-aware checks."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class ScriptRange:
    """One named script represented by inclusive Unicode code-point ranges."""

    name: str
    ranges: tuple[tuple[int, int], ...]

    def contains(self, character: str) -> bool:
        """Return whether a character belongs to one of this script's ranges."""
        point = ord(character)
        return any(start <= point <= end for start, end in self.ranges)


SCRIPTS: dict[str, ScriptRange] = {
    "Bengali": ScriptRange("Bengali", ((0x0980, 0x09FF),)),
    "Devanagari": ScriptRange("Devanagari", ((0x0900, 0x097F), (0xA8E0, 0xA8FF))),
    "Gujarati": ScriptRange("Gujarati", ((0x0A80, 0x0AFF),)),
    "Gurmukhi": ScriptRange("Gurmukhi", ((0x0A00, 0x0A7F),)),
    "Odia": ScriptRange("Odia", ((0x0B00, 0x0B7F),)),
    "Tamil": ScriptRange("Tamil", ((0x0B80, 0x0BFF),)),
    "Telugu": ScriptRange("Telugu", ((0x0C00, 0x0C7F),)),
    "Kannada": ScriptRange("Kannada", ((0x0C80, 0x0CFF),)),
    "Malayalam": ScriptRange("Malayalam", ((0x0D00, 0x0D7F),)),
    "Meetei Mayek": ScriptRange("Meetei Mayek", ((0xAAE0, 0xAAFF), (0xABC0, 0xABFF))),
    "Ol Chiki": ScriptRange("Ol Chiki", ((0x1C50, 0x1C7F),)),
    "Kaithi": ScriptRange("Kaithi", ((0x11080, 0x110CF),)),
    "Tirhuta": ScriptRange("Tirhuta", ((0x11480, 0x114DF),)),
    "Takri": ScriptRange("Takri", ((0x11680, 0x116CF),)),
    "Khudawadi": ScriptRange("Khudawadi", ((0x112B0, 0x112FF),)),
    "Latin": ScriptRange(
        "Latin",
        ((0x0041, 0x005A), (0x0061, 0x007A), (0x00C0, 0x024F), (0x1E00, 0x1EFF)),
    ),
    "Arabic": ScriptRange("Arabic", ((0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF))),
    "Cyrillic": ScriptRange("Cyrillic", ((0x0400, 0x052F),)),
    "Greek": ScriptRange("Greek", ((0x0370, 0x03FF),)),
    "Hebrew": ScriptRange("Hebrew", ((0x0590, 0x05FF),)),
    "Han": ScriptRange("Han", ((0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF))),
    "Hiragana": ScriptRange("Hiragana", ((0x3040, 0x309F),)),
    "Katakana": ScriptRange("Katakana", ((0x30A0, 0x30FF), (0x31F0, 0x31FF))),
    "Hangul": ScriptRange("Hangul", ((0x1100, 0x11FF), (0x3130, 0x318F), (0xAC00, 0xD7AF))),
}


@dataclass(frozen=True)
class LanguageProfile:
    """Script expectations and localized patterns for a corpus language."""

    key: str
    name: str
    target_scripts: tuple[str, ...] = ()
    allowed_secondary_scripts: tuple[str, ...] = ()
    default_min_script_ratio: float | None = None
    phone_patterns: tuple[str, ...] = ()
    boilerplate_markers: tuple[str, ...] = ()


COMMON_BOILERPLATE = (
    "privacy policy",
    "terms and conditions",
    "all rights reserved",
    "cookie policy",
    "skip to content",
    "sign in",
    "log in",
    "subscribe now",
    "© copyright",
)

INDIA_PHONE_PATTERNS = (r"(?<!\d)(?:\+?91[- ]?)?[6-9]\d{9}(?!\d)",)
NEPAL_PHONE_PATTERNS = (r"(?<!\d)(?:\+?977[- ]?)?(?:9[678]\d{8}|0?1\d{7})(?!\d)",)
BANGLADESH_PHONE_PATTERNS = (
    r"(?<!\d)(?:(?:\+?88)?01[3-9]\d{8})(?!\d)",
    r"(?<![০-৯])(?:\+?৮৮)?০১[৩-৯][০-৯]{8}(?![০-৯])",
)


def _indic_profile(
    key: str,
    name: str,
    target_scripts: tuple[str, ...],
    allowed_secondary: tuple[str, ...] = ("Latin",),
    phone_patterns: tuple[str, ...] = INDIA_PHONE_PATTERNS,
    boilerplate: tuple[str, ...] = (),
) -> LanguageProfile:
    """Create an Indic profile with conservative, review-first defaults."""
    return LanguageProfile(
        key,
        name,
        target_scripts,
        allowed_secondary,
        0.20,
        phone_patterns,
        boilerplate,
    )


PROFILES: dict[str, LanguageProfile] = {
    "generic": LanguageProfile("generic", "Language-agnostic"),
    # Widely represented Indic languages.
    "bn": _indic_profile(
        "bn",
        "Bengali",
        ("Bengali",),
        ("Latin",),
        BANGLADESH_PHONE_PATTERNS + INDIA_PHONE_PATTERNS,
        ("গোপনীয়তা নীতি", "সর্বস্বত্ব সংরক্ষিত", "লগ ইন", "সাইন ইন", "সাবস্ক্রাইব"),
    ),
    "gu": _indic_profile("gu", "Gujarati", ("Gujarati",)),
    "hi": _indic_profile("hi", "Hindi", ("Devanagari",)),
    "kn": _indic_profile("kn", "Kannada", ("Kannada",)),
    "ml": _indic_profile("ml", "Malayalam", ("Malayalam",)),
    "mr": _indic_profile("mr", "Marathi", ("Devanagari",)),
    "or": _indic_profile("or", "Odia", ("Odia",)),
    "pa": _indic_profile("pa", "Punjabi", ("Gurmukhi",), ("Latin", "Arabic")),
    "ta": _indic_profile("ta", "Tamil", ("Tamil",)),
    "te": _indic_profile("te", "Telugu", ("Telugu",)),
    "ur": _indic_profile("ur", "Urdu", ("Arabic",)),
    # Lower-resource languages and languages with multiple living/historic scripts.
    "as": _indic_profile("as", "Assamese", ("Bengali",)),
    "bho": _indic_profile("bho", "Bhojpuri", ("Devanagari", "Kaithi")),
    "brx": _indic_profile("brx", "Bodo", ("Devanagari",)),
    "doi": _indic_profile("doi", "Dogri", ("Devanagari", "Takri")),
    "kok": _indic_profile("kok", "Konkani", ("Devanagari", "Latin", "Kannada", "Malayalam"), ()),
    "mai": _indic_profile("mai", "Maithili", ("Devanagari", "Tirhuta")),
    "mni": _indic_profile("mni", "Manipuri", ("Meetei Mayek", "Bengali")),
    "lus": _indic_profile("lus", "Mizo", ("Latin",), ()),
    "ne": _indic_profile(
        "ne", "Nepali", ("Devanagari",), ("Latin",), NEPAL_PHONE_PATTERNS,
        ("गोपनीयता नीति", "सर्वाधिकार सुरक्षित", "लग इन", "साइन इन", "सदस्यता लिनुहोस्"),
    ),
    "sd": _indic_profile("sd", "Sindhi", ("Arabic", "Devanagari", "Khudawadi")),
    # Additional Indic profiles.
    "ks": _indic_profile("ks", "Kashmiri", ("Arabic", "Devanagari")),
    "sa": _indic_profile("sa", "Sanskrit", ("Devanagari",)),
    "sat": _indic_profile("sat", "Santali", ("Ol Chiki", "Devanagari", "Bengali", "Odia")),
    # Non-Indic profiles demonstrate that the engine is not tied to one region.
    "en": LanguageProfile("en", "English", ("Latin",), (), 0.50),
    "ja": LanguageProfile("ja", "Japanese", ("Han", "Hiragana", "Katakana"), ("Latin",), 0.50),
}

ALIASES = {
    "auto": "generic", "assamese": "as", "bengali": "bn", "bangla": "bn",
    "bhojpuri": "bho", "bodo": "brx", "dogri": "doi", "english": "en",
    "gujarati": "gu", "hindi": "hi", "japanese": "ja", "kannada": "kn",
    "kashmiri": "ks", "konkani": "kok", "maithili": "mai", "malayalam": "ml",
    "manipuri": "mni", "meitei": "mni", "marathi": "mr", "mizo": "lus",
    "nepali": "ne", "odia": "or", "oriya": "or", "punjabi": "pa",
    "sanskrit": "sa", "santali": "sat", "sindhi": "sd", "tamil": "ta",
    "telugu": "te", "urdu": "ur",
}


def get_profile(name: str) -> LanguageProfile:
    """Resolve a profile key or human-readable alias."""
    key = ALIASES.get(name.casefold(), name.casefold())
    if key not in PROFILES:
        choices = ", ".join(sorted(PROFILES))
        raise ValueError(f"Unknown profile {name!r}. Available profiles: {choices}")
    return PROFILES[key]


@lru_cache(maxsize=8192)
def character_script(character: str) -> str:
    """Classify one character, caching the result for corpus-scale scans."""
    for name, script in SCRIPTS.items():
        if script.contains(character):
            return name
    # Unicode names give useful coverage for scripts that do not yet have a
    # first-class cleaning profile. This is descriptive, not language ID.
    import unicodedata

    name = unicodedata.name(character, "")
    for script_name in ("ARMENIAN", "GEORGIAN", "THAI"):
        if script_name in name:
            return "Odia" if script_name in {"ORIYA", "ODIA"} else script_name.title()
    return "Other"
