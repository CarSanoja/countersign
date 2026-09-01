"""Confusable variants of a domain, spread across attack classes.

The sweep is capped, and a naive cap drains the first class before reaching the
last, so the picks are round-robined: a sweep that only checked TLD swaps would
miss the homoglyph that actually fools a person.
"""

from dataclasses import dataclass
from enum import StrEnum

CONFUSABLE_TLDS = ("com", "co", "net", "org", "biz", "info", "cc", "us")

HOMOGLYPHS: dict[str, tuple[str, ...]] = {
    "o": ("0",),
    "l": ("1", "i"),
    "i": ("1", "l"),
    "e": ("3",),
    "a": ("4",),
    "s": ("5",),
    "m": ("rn",),
}

KEYBOARD: dict[str, str] = {
    "a": "s", "b": "v", "c": "x", "d": "s", "e": "r", "f": "d", "g": "f",
    "h": "g", "i": "o", "j": "h", "k": "j", "l": "k", "m": "n", "n": "b",
    "o": "p", "p": "o", "q": "w", "r": "t", "s": "a", "t": "y", "u": "y",
    "v": "c", "w": "q", "x": "z", "y": "t", "z": "x",
}

SUFFIXES = ("-inc", "-llc", "-group", "-billing", "-invoices", "-pay")


class VariantKind(StrEnum):
    TLD_SWAP = "tld-swap"
    HYPHEN = "hyphen"
    OMISSION = "omission"
    DOUBLING = "doubling"
    TRANSPOSITION = "transposition"
    HOMOGLYPH = "homoglyph"
    ADJACENT_KEY = "adjacent-key"
    SUFFIX = "suffix"


HIGH_RISK_KINDS: frozenset[VariantKind] = frozenset(
    {
        VariantKind.HOMOGLYPH,
        VariantKind.ADJACENT_KEY,
        VariantKind.HYPHEN,
        VariantKind.TLD_SWAP,
        VariantKind.TRANSPOSITION,
    }
)


@dataclass(frozen=True)
class Variant:
    domain_name: str
    kind: VariantKind


def _split(domain: str) -> tuple[str, str] | None:
    label, dot, tld = domain.partition(".")
    if not dot or not label:
        return None
    return label, tld


def generate_variants(domain: str, limit: int = 40) -> list[Variant]:
    parts = _split(domain.lower().strip())
    if parts is None:
        return []
    label, tld = parts
    found: dict[str, Variant] = {}

    def add(name: str, kind: VariantKind) -> None:
        if name != domain and name not in found:
            found[name] = Variant(name, kind)

    for alt in CONFUSABLE_TLDS:
        if alt != tld:
            add(f"{label}.{alt}", VariantKind.TLD_SWAP)

    if "-" in label:
        add(f"{label.replace('-', '')}.{tld}", VariantKind.HYPHEN)
    else:
        for i in range(1, len(label)):
            add(f"{label[:i]}-{label[i:]}.{tld}", VariantKind.HYPHEN)

    for i, char in enumerate(label):
        add(f"{label[:i]}{label[i + 1:]}.{tld}", VariantKind.OMISSION)
        add(f"{label[:i]}{char}{label[i:]}.{tld}", VariantKind.DOUBLING)

        if i + 1 < len(label):
            swapped = label[:i] + label[i + 1] + char + label[i + 2:]
            add(f"{swapped}.{tld}", VariantKind.TRANSPOSITION)

        for glyph in HOMOGLYPHS.get(char, ()):
            add(f"{label[:i]}{glyph}{label[i + 1:]}.{tld}", VariantKind.HOMOGLYPH)

        near = KEYBOARD.get(char)
        if near:
            add(f"{label[:i]}{near}{label[i + 1:]}.{tld}", VariantKind.ADJACENT_KEY)

    for suffix in SUFFIXES:
        add(f"{label}{suffix}.{tld}", VariantKind.SUFFIX)

    return _balance(list(found.values()), limit)


def _balance(variants: list[Variant], limit: int) -> list[Variant]:
    buckets: dict[VariantKind, list[Variant]] = {}
    for variant in variants:
        buckets.setdefault(variant.kind, []).append(variant)

    picked: list[Variant] = []
    for round_index in range(max((len(b) for b in buckets.values()), default=0)):
        for bucket in buckets.values():
            if round_index < len(bucket):
                picked.append(bucket[round_index])
                if len(picked) == limit:
                    return picked
    return picked
