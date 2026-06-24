"""Deterministic text utilities shared by the TM and the QA linter.

Keeping normalization + placeholder extraction in ONE place means the TM key and
the QA placeholder check can never drift apart — a deliberate choice so "same
English source" means the same thing everywhere.
"""

from __future__ import annotations

import re
from collections import Counter

# printf / iOS / Android style: %@, %lld, %d, %s, %1$@, %2$lld ...
_PRINTF = re.compile(r"%(?:\d+\$)?[@A-Za-z]+")
# {name}, {count}, {0} ...
_BRACES = re.compile(r"\{[^}]*\}")
# <b>, </b>, <tag attr="x">
_TAGS = re.compile(r"</?[A-Za-z][^>]*>")
# Common emoji blocks (covers 🔥, ✅, ⭐, flags, etc.) + variation selector.
_EMOJI = re.compile(
    "["
    "\U0001F000-\U0001FAFF"  # symbols & pictographs, supplemental, etc.
    "\U00002600-\U000027BF"  # misc symbols + dingbats
    "\U00002B00-\U00002BFF"  # arrows / stars
    "\U0001F1E6-\U0001F1FF"  # regional indicators (flags)
    "️"                 # variation selector-16
    "]"
)


def normalize_source(text: str) -> str:
    """Canonical key for TM lookup: trim, collapse inner whitespace, casefold.

    Case-insensitive so 'Settings' and 'settings' are one TM entry. Placeholders
    are preserved as-is (they're part of the identity of the string)."""
    collapsed = re.sub(r"\s+", " ", text.strip())
    return collapsed.casefold()


def extract_placeholders(text: str) -> Counter:
    """Multiset of every placeholder / markup / emoji / newline token in `text`.

    Two strings preserve placeholders iff their Counters are equal — order and
    surrounding words don't matter, but token identity and count do."""
    tokens: list[str] = []
    tokens += _PRINTF.findall(text)
    tokens += _BRACES.findall(text)
    tokens += _TAGS.findall(text)
    tokens += _EMOJI.findall(text)
    # Treat both a real newline and a literal backslash-n as the same token.
    newlines = text.count("\n") + len(re.findall(r"\\n", text))
    tokens += ["\\n"] * newlines
    return Counter(tokens)


def placeholder_diff(source: str, target: str) -> tuple[list[str], list[str]]:
    """Return (missing_in_target, extra_in_target) placeholder tokens."""
    src = extract_placeholders(source)
    tgt = extract_placeholders(target)
    missing = list((src - tgt).elements())
    extra = list((tgt - src).elements())
    return missing, extra
