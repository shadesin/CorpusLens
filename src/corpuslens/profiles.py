from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class ScriptRange:
    name: str
    ranges: tuple[tuple[int, int], ...]

    def contains(self, character: str) -> bool:
        point = ord(character)
        return any(start <= point <= end for start, end in self.ranges)


SCRIPTS: dict[str, ScriptRange] = {
    "Bengali": ScriptRange("Bengali", ((0x0980, 0x09FF),)),
    "Devanagari": ScriptRange("Devanagari", ((0x0900, 0x097F), (0xA8E0, 0xA8FF))),
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


PROFILES: dict[str, LanguageProfile] = {
    "generic": LanguageProfile("generic", "Language-agnostic"),
    "bn": LanguageProfile(
        "bn",
        "Bengali",
        ("Bengali",),
        ("Latin",),
        0.20,
        (
            r"(?<!\d)(?:(?:\+?88)?01[3-9]\d{8})(?!\d)",
            r"(?<![০-৯])(?:\+?৮৮)?০১[৩-৯][০-৯]{8}(?![০-৯])",
        ),
        ("গোপনীয়তা নীতি", "সর্বস্বত্ব সংরক্ষিত", "লগ ইন", "সাইন ইন", "সাবস্ক্রাইব"),
    ),
    "ne": LanguageProfile(
        "ne",
        "Nepali",
        ("Devanagari",),
        ("Latin",),
        0.20,
        (r"(?<!\d)(?:\+?977[- ]?)?(?:9[678]\d{8}|0?1\d{7})(?!\d)",),
        ("गोपनीयता नीति", "सर्वाधिकार सुरक्षित", "लग इन", "साइन इन", "सदस्यता लिनुहोस्"),
    ),
    "hi": LanguageProfile("hi", "Hindi", ("Devanagari",), ("Latin",), 0.20),
    "en": LanguageProfile("en", "English", ("Latin",), (), 0.50),
    "ja": LanguageProfile("ja", "Japanese", ("Han", "Hiragana", "Katakana"), ("Latin",), 0.50),
}

ALIASES = {"bengali": "bn", "bangla": "bn", "nepali": "ne", "hindi": "hi", "english": "en", "japanese": "ja", "auto": "generic"}


def get_profile(name: str) -> LanguageProfile:
    key = ALIASES.get(name.casefold(), name.casefold())
    if key not in PROFILES:
        choices = ", ".join(sorted(PROFILES))
        raise ValueError(f"Unknown profile {name!r}. Available profiles: {choices}")
    return PROFILES[key]


@lru_cache(maxsize=8192)
def character_script(character: str) -> str:
    for name, script in SCRIPTS.items():
        if script.contains(character):
            return name
    # Unicode names give useful coverage for scripts that do not yet have a
    # first-class cleaning profile. This is descriptive, not language ID.
    import unicodedata

    name = unicodedata.name(character, "")
    for script_name in (
        "ARMENIAN", "GEORGIAN", "GUJARATI", "GURMUKHI", "KANNADA",
        "MALAYALAM", "ORIYA", "ODIA", "TAMIL", "TELUGU", "THAI",
    ):
        if script_name in name:
            return "Odia" if script_name in {"ORIYA", "ODIA"} else script_name.title()
    return "Other"
