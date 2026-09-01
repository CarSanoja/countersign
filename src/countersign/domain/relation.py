"""How the sender domain stands to the vendor's official one.

`sender != official` is not evidence of impersonation. invoices.name.com is the
vendor's own billing namespace and narne.com is an attacker's homoglyph, and a
comparison that only checks inequality hands both the same verdict. Naming the
relation first is what keeps the false positive that would make a customer turn
the product off out of the verdict, without softening the homoglyph.

The suffix table is deliberately a short list rather than the full public suffix
list: it covers the compound suffixes an invoice actually arrives under. Outside
it, the last two labels are read as the registrable name, which is why a vendor
under a rarer compound suffix, or under a hosting suffix such as github.io, can
still be read as sharing a registrant with a neighbour that only shares its
suffix. That is the known edge of this file.
"""

from enum import StrEnum

from autocurricula.schemas.common import StrictBaseModel

from countersign.domain.lookalike import VariantKind, generate_variants

VARIANT_DEPTH = 4096

COMPOUND_SUFFIXES: frozenset[str] = frozenset(
    {
        "co.uk", "org.uk", "ac.uk", "gov.uk", "me.uk", "net.uk", "ltd.uk", "plc.uk",
        "com.au", "net.au", "org.au", "edu.au", "gov.au",
        "co.nz", "net.nz", "org.nz",
        "co.jp", "or.jp", "ne.jp", "ac.jp", "co.kr", "or.kr",
        "com.br", "com.mx", "com.ar", "com.co", "com.pe", "com.uy", "com.ve", "com.ec",
        "com.cn", "net.cn", "org.cn", "com.hk", "com.tw", "com.sg", "com.my", "com.ph",
        "com.vn", "com.tr", "com.ua", "com.pl", "com.es", "com.pt", "com.gr", "com.ro",
        "com.ng", "com.sa", "com.eg", "com.pk", "com.bd", "com.do", "com.gt", "com.pa",
        "co.in", "net.in", "org.in", "co.id", "co.il", "co.za", "co.ke", "co.th",
    }
)


class RelationKind(StrEnum):
    """What a sender domain is to the official one, past mere inequality."""

    SAME = "same"
    SUBDOMAIN = "subdomain"
    PARENT = "parent"
    SIBLING_HOST = "sibling-host"
    SIBLING_TLD = "sibling-tld"
    CONFUSABLE = "confusable"
    UNRELATED = "unrelated"


SAME_REGISTRANT: frozenset[RelationKind] = frozenset(
    {
        RelationKind.SAME,
        RelationKind.SUBDOMAIN,
        RelationKind.PARENT,
        RelationKind.SIBLING_HOST,
    }
)


class DomainRelation(StrictBaseModel):
    """One classified pair, kept so the dossier can show why nothing was raised."""

    kind: RelationKind
    sender: str = ""
    official: str = ""
    variant_kind: VariantKind | None = None

    @property
    def same_registrant(self) -> bool:
        """Whether both names sit inside the namespace the vendor already controls."""
        return self.kind in SAME_REGISTRANT

    @property
    def description(self) -> str:
        """The relation as a clause a claim can carry, never as a bare 'is not'."""
        if self.kind is RelationKind.SAME:
            return "is the vendor's official domain"
        if self.kind is RelationKind.SUBDOMAIN:
            return f"is a subdomain of {self.official}, the vendor's official domain"
        if self.kind is RelationKind.PARENT:
            return f"is the parent domain of {self.official}, the vendor's official domain"
        if self.kind is RelationKind.SIBLING_HOST:
            return (
                f"sits under {registrable(self.official)}, the same registrable domain as "
                f"{self.official}, the vendor's official domain"
            )
        if self.kind is RelationKind.SIBLING_TLD:
            return (
                f"carries the same name as {self.official}, the vendor's official domain, "
                "under a different top-level domain"
            )
        if self.kind is RelationKind.CONFUSABLE:
            kind = self.variant_kind.value if self.variant_kind else "confusable"
            article = "an" if kind[0] in "aeiou" else "a"
            return f"is {article} {kind} variant of {self.official}, the vendor's official domain"
        return f"is unrelated to {self.official}, the vendor's official domain"


def normalize(host: str) -> str:
    """Reduce whatever the extractor handed over to a bare, comparable host name."""
    text = host.strip().lower()
    if "://" in text:
        text = text.partition("://")[2]
    if "@" in text:
        text = text.rpartition("@")[2]
    text = text.split("/")[0].split("?")[0].split(":")[0]
    return text.strip(".")


def public_suffix(host: str) -> str:
    """The suffix a name is bought under, compound where the short table knows one."""
    labels = host.split(".")
    if len(labels) >= 3 and ".".join(labels[-2:]) in COMPOUND_SUFFIXES:
        return ".".join(labels[-2:])
    return labels[-1] if len(labels) > 1 else ""


def registrable(host: str) -> str:
    """The name plus its suffix: name.co.uk, never the bare suffix co.uk."""
    suffix = public_suffix(host)
    if not suffix:
        return host
    depth = suffix.count(".") + 2
    labels = host.split(".")
    return ".".join(labels[-depth:]) if len(labels) >= depth else host


def is_public_suffix(host: str) -> bool:
    """Whether the name is only a suffix, so nothing can be its subdomain."""
    return "." not in host or host in COMPOUND_SUFFIXES


def classify(sender: str, official: str) -> DomainRelation:
    """Name the relation between the sending host and the vendor's official domain."""
    left, right = normalize(sender), normalize(official)
    if not left or not right:
        return DomainRelation(kind=RelationKind.UNRELATED, sender=left, official=right)
    if left == right:
        return DomainRelation(kind=RelationKind.SAME, sender=left, official=right)
    if _is_under(left, right):
        return DomainRelation(kind=RelationKind.SUBDOMAIN, sender=left, official=right)
    if _is_under(right, left):
        return DomainRelation(kind=RelationKind.PARENT, sender=left, official=right)

    base_left, base_right = registrable(left), registrable(right)
    variant = _variant_kind(base_left, base_right)
    if base_left == base_right:
        return DomainRelation(kind=RelationKind.SIBLING_HOST, sender=left, official=right)
    if _same_label(base_left, base_right):
        return DomainRelation(
            kind=RelationKind.SIBLING_TLD, sender=left, official=right, variant_kind=variant
        )
    if variant is not None:
        return DomainRelation(
            kind=RelationKind.CONFUSABLE, sender=left, official=right, variant_kind=variant
        )
    return DomainRelation(kind=RelationKind.UNRELATED, sender=left, official=right)


def _is_under(child: str, parent: str) -> bool:
    """A label boundary is required, so notname.com is not under name.com."""
    return child.endswith(f".{parent}") and not is_public_suffix(parent)


def _same_label(left: str, right: str) -> bool:
    """Same registrable label under different suffixes: name.net against name.com."""
    label_left, _, suffix_left = left.partition(".")
    label_right, _, suffix_right = right.partition(".")
    return bool(label_left) and label_left == label_right and suffix_left != suffix_right


def _variant_kind(sender: str, official: str) -> VariantKind | None:
    """Which attack class of the lookalike generator this pair falls into, if any.

    The generator is run at full depth rather than at the sweep's cap: the sweep
    samples a surface it can afford to check, while a classification that misses
    a homoglyph because of a cap would be worse than no classification at all.
    """
    for base, other in ((official, sender), (sender, official)):
        for variant in generate_variants(base, VARIANT_DEPTH):
            if variant.domain_name == other:
                return variant.kind
    return None


__all__ = [
    "COMPOUND_SUFFIXES",
    "SAME_REGISTRANT",
    "DomainRelation",
    "RelationKind",
    "classify",
    "is_public_suffix",
    "normalize",
    "public_suffix",
    "registrable",
]
