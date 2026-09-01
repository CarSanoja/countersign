"""The soak corpus: twenty invoices in the proportion fraud actually arrives in.

Sixteen are legitimate and four are fraudulent. A balanced set would report a
false positive rate no finance team will ever see, because the denominator that
decides whether a control is switched off after a fortnight is the legitimate
invoice, not the fraudulent one.

The hard legitimate cases are the point of the set rather than decoration: a
billing subdomain, a sibling TLD the vendor demonstrably owns, a first invoice
from a supplier with no history, and a bank change that is genuinely the
supplier's own. Every sender domain's registration status is real and was read
from the production registry; the fraudulent senders impersonate name.com and
name.com is never the perpetrator.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Counterparty:
    """A supplier as the corpus needs it: who they are and what they bill for."""

    key: str
    brand: str
    tagline: str
    legal_name: str
    address: str
    official_domain: str
    vat: str
    iban: str
    moved_iban: str
    primary_item: str
    secondary_items: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class SoakCase:
    """One invoice, its ground truth, and why it is in the set."""

    case_id: str
    counterparty: Counterparty
    sender_domain: str
    primary_amount: int
    invoice_number: str
    why: str
    fraudulent: bool = False
    bank_changed: bool = False
    bank_block: bool = True
    sender_display: str = ""

    @property
    def email(self) -> str:
        """What the invoice prints as its billing address, casing included."""
        return self.sender_display or f"billing@{self.sender_domain}"

    @property
    def total(self) -> int:
        return self.primary_amount + sum(amount for _, amount in self.counterparty.secondary_items)


NAMECOM = Counterparty(
    key="namecom",
    brand="Name.com",
    tagline="Domain Services",
    legal_name="Name.com, Inc.",
    address="414 14th Street, Suite 200, Denver, CO 80202",
    official_domain="name.com",
    vat="ES-B12345678",
    iban="GB29 NWBK 6016 1331 9268 19",
    moved_iban="GB94 BARC 2020 1530 0934 59",
    primary_item="Enterprise Registrar API — annual",
    secondary_items=(
        ("Bulk domain portfolio renewal (1,240 domains)", 14_880),
        ("Premium DNS & DNSSEC", 720),
    ),
)

GOOGLE = Counterparty(
    key="google",
    brand="Google",
    tagline="Workspace & Cloud",
    legal_name="Google LLC",
    address="1600 Amphitheatre Parkway, Mountain View, CA 94043",
    official_domain="google.com",
    vat="IE-6388047V",
    iban="IE29 AIBK 9311 5212 3456 78",
    moved_iban="IE64 IRCE 9205 0112 3456 78",
    primary_item="Google Workspace Enterprise Plus — annual, 320 seats",
    secondary_items=(("Cloud Identity Premium", 5_760), ("Vault retention", 1_440)),
)

VERDANT = Counterparty(
    key="verdant",
    brand="Verdant Ledger",
    tagline="Reconciliation Services",
    legal_name="Verdant Ledger Services S.L.",
    address="Carrer de Balmes 191, 08006 Barcelona, Spain",
    official_domain="verdantledger.com",
    vat="ES-B98765432",
    iban="ES91 2100 0418 4502 0005 1332",
    moved_iban="ES79 2100 0813 6101 2345 6789",
    primary_item="Ledger reconciliation onboarding — first quarter",
    secondary_items=(("Data migration", 3_400), ("Support retainer", 1_200)),
)

ATTACKER_IBAN = "LT12 3250 0123 4567 8901"

CASES: tuple[SoakCase, ...] = (
    SoakCase("legit-clean-01", NAMECOM, "name.com", 68_400, "4471",
             "the vendor's own domain and no bank change: the baseline of the set"),
    SoakCase("legit-clean-02", NAMECOM, "name.com", 71_200, "4488",
             "the same shape a month later, to see whether a clean run stays clean"),
    SoakCase("legit-clean-03", NAMECOM, "name.com", 12_600, "4502",
             "a small renewal, because not every legitimate invoice is a large one"),
    SoakCase("legit-clean-04", NAMECOM, "name.com", 96_150, "4519",
             "a large one, in case size alone moves the verdict"),
    SoakCase("legit-billing-subdomain", NAMECOM, "invoices.name.com", 68_400, "4523",
             "the vendor's own billing namespace: the false positive the sentinel exists to avoid"),
    SoakCase("legit-billing-subdomain-renewal", NAMECOM, "invoices.name.com", 21_900, "4530",
             "the same namespace with different content, so the pass is not one document twice"),
    SoakCase("legit-accounts-subdomain", NAMECOM, "accounts.name.com", 33_450, "4541",
             "a second subdomain, because vendors do not send everything from one host"),
    SoakCase("legit-billing-subdomain-credit", NAMECOM, "billing.name.com", 8_250, "4547",
             "a third subdomain on a credit note, the thinnest legitimate document here"),
    SoakCase("legit-bank-change", NAMECOM, "name.com", 68_400, "4552",
             "the supplier really did move bank and says so: the most expensive false positive",
             bank_changed=True),
    SoakCase("legit-bank-change-subdomain", NAMECOM, "invoices.name.com", 45_300, "4558",
             "the same honest change from the billing namespace, to separate the two causes",
             bank_changed=True),
    SoakCase("legit-no-remittance-block", NAMECOM, "name.com", 27_800, "4563",
             "an invoice that prints no account at all, so nothing about the bank is knowable",
             bank_block=False),
    SoakCase("legit-mixed-case-sender", NAMECOM, "name.com", 52_000, "4570",
             "the domain printed as Name.com: casing must not turn a vendor into a stranger",
             sender_display="Billing@Name.com"),
    SoakCase("legit-second-in-month", NAMECOM, "name.com", 19_400, "4574",
             "a second invoice inside one billing period, the ordinary case of repetition"),
    SoakCase("legit-sibling-tld", GOOGLE, "google.net", 184_320, "GO-88214",
             "google.net is registered to the owner of google.com; a sibling TLD the vendor holds"),
    SoakCase("legit-sibling-tld-control", GOOGLE, "google.com", 184_320, "GO-88219",
             "the same vendor from its official domain, so the sibling case has a control"),
    SoakCase("legit-first-time-supplier", VERDANT, "verdantledger.com", 24_500, "VL-1001",
             "a first invoice from a supplier with no history: newness must not read as risk"),
    SoakCase("fraud-homoglyph", NAMECOM, "narne.com", 84_000, "4471",
             "rn for m, registered by somebody: the classic BEC lure",
             fraudulent=True, bank_changed=True),
    SoakCase("fraud-hyphen", NAMECOM, "na-me.com", 84_000, "4471",
             "hyphen insertion, already taken",
             fraudulent=True, bank_changed=True),
    SoakCase("fraud-unregistered", NAMECOM, "nane.com", 84_000, "4472",
             "an invoice from a domain nobody owns is worse, not better",
             fraudulent=True, bank_changed=True),
    SoakCase("fraud-subdomain-lure", NAMECOM, "name.com.billing-invoices.co", 84_000, "4473",
             "name.com appears in full, as a label of somebody else's registrable domain",
             fraudulent=True, bank_changed=True),
)

LEGITIMATE = tuple(case for case in CASES if not case.fraudulent)
FRAUDULENT = tuple(case for case in CASES if case.fraudulent)

COUNTERPARTIES = (NAMECOM, GOOGLE, VERDANT)

__all__ = [
    "ATTACKER_IBAN",
    "CASES",
    "COUNTERPARTIES",
    "FRAUDULENT",
    "GOOGLE",
    "LEGITIMATE",
    "NAMECOM",
    "VERDANT",
    "Counterparty",
    "SoakCase",
]
