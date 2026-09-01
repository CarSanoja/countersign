"""No account identifier may reach a model. Asserted, not assumed."""

from countersign.agents.pii_mask import carries_pii, iban_in, mask_pii


def test_an_iban_is_masked_but_its_shape_survives():
    masked = mask_pii("IBAN: LT12 3250 01234 5678 9012")
    assert "3250" not in masked
    assert "9012" not in masked
    assert "#" in masked


def test_a_swift_code_is_masked():
    assert "REVOLT21" not in mask_pii("SWIFT/BIC: REVOLT21")


def test_a_tax_identifier_is_masked():
    assert "B12345678" not in mask_pii("VAT ES-B12345678")


def test_the_mailbox_is_masked_and_the_domain_is_kept():
    masked = mask_pii("Questions: billing@narne.com")
    assert "billing" not in masked
    assert "narne.com" in masked, "the domain is the signal and must survive"


def test_an_amount_is_not_an_identifier():
    assert mask_pii("Total due $84,000.00") == "Total due $84,000.00"


def test_an_iban_is_read_back_verbatim_from_the_span():
    assert iban_in("IBAN: LT12 3250 01234 5678 9012") == "LT12 3250 01234 5678 9012"


def test_text_without_identifiers_is_left_alone():
    assert not carries_pii("Enterprise Registrar API - annual")


def test_an_ordinary_uppercase_phrase_is_not_mistaken_for_a_bic():
    """A BIC needs its label. Eight uppercase letters is a company name."""
    assert mask_pii("Supplier: GLOBAL SUPPLIES LIMITED") == "Supplier: GLOBAL SUPPLIES LIMITED"


def test_the_labelled_iban_wins_over_one_mentioned_in_passing():
    """A document naming a closed account alongside the new one must not
    hand back whichever came first: the account being paid is the one that
    matters."""
    text = "old DE89 3704 0044 0532 0130 00 / IBAN: LT12 3250 01234 5678 9012"
    assert iban_in(text) == "LT12 3250 01234 5678 9012"


def test_trailing_prose_is_not_swallowed_into_the_account_number():
    assert iban_in("Previous account ES91 2100 0418 4502 0005 1332 is closed") == (
        "ES91 2100 0418 4502 0005 1332"
    )
