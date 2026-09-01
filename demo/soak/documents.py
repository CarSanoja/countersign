"""The corpus as PDFs, built the way demo/benchmark builds its own.

The stylesheet and the page frame come out of demo/fixtures/invoice.html, so the
soak measures the same document shape the rest of the demo does. Only the body
under the header is composed here, because twenty invoices that differ in
sender, account, date and amount cannot be twenty copies of one file.

Rendering is idempotent on purpose. Every pass of a soak reads the same PDFs, so
the conversion is paid for once and a repeated run costs the renderer nothing.
"""

import asyncio
import html
import pathlib
from datetime import date, timedelta

from corpus import ATTACKER_IBAN, SoakCase

from countersign.tools.foxit_pdf import foxit_generate_document

HERE = pathlib.Path(__file__).resolve().parent
FIXTURE = HERE.parent / "fixtures" / "invoice.html"
PDF_DIR = HERE / "pdfs"
BODY_ANCHOR = '<div class="hdr">'
FIRST_ISSUE = date(2026, 9, 1)
DUE_DAYS = 7
RENDER_PAUSE_SECONDS = 8.0
RENDER_ATTEMPTS = 4


def frame() -> str:
    """Everything the fixture declares before its first invoice-specific line."""
    source = FIXTURE.read_text(encoding="utf-8")
    head, anchor, _ = source.partition(BODY_ANCHOR)
    if not anchor:
        raise RuntimeError(f"{FIXTURE} no longer starts its body with {BODY_ANCHOR!r}")
    return head


def _text(value: str) -> str:
    """Every value merged into the page comes from the corpus as plain text."""
    return html.escape(value)


def _money(amount: int) -> str:
    return f"${amount:,.2f}"


def _row(description: str, amount: int) -> str:
    cell = _money(amount)
    return (
        f'<tr><td>{_text(description)}</td><td class="right">1</td>'
        f'<td class="right">{cell}</td><td class="right">{cell}</td></tr>'
    )


def _items(case: SoakCase) -> str:
    party = case.counterparty
    rows = [_row(party.primary_item, case.primary_amount)]
    rows += [_row(name, amount) for name, amount in party.secondary_items]
    rows.append(
        '<tr><td class="total">Total due</td><td></td><td></td>'
        f'<td class="right total">{_money(case.total)}</td></tr>'
    )
    header = (
        '<tr><th>Description</th><th class="right">Qty</th>'
        '<th class="right">Unit</th><th class="right">Amount</th></tr>'
    )
    return "<table>\n" + header + "\n" + "\n".join(rows) + "\n</table>"


def _iban(case: SoakCase) -> str:
    if case.fraudulent:
        return ATTACKER_IBAN
    return case.counterparty.moved_iban if case.bank_changed else case.counterparty.iban


def _bank(case: SoakCase) -> str:
    if not case.bank_block:
        return ""
    heading = (
        "Remittance details — PLEASE NOTE OUR BANK HAS CHANGED"
        if case.bank_changed
        else "Remittance details"
    )
    notice = (
        "Kindly update your records. Payments to our previous account can no longer be applied."
        if case.bank_changed
        else "Standard remittance details, unchanged from the account on file."
    )
    return (
        '<div class="bank">\n'
        f"<strong>{_text(heading)}</strong>\n"
        '<div class="notice">\n'
        f"Beneficiary: {_text(case.counterparty.legal_name)}<br>\n"
        f"IBAN: {_text(_iban(case))}<br>\n"
        "SWIFT/BIC: REVOLT21<br>\n"
        f"Reference: INV-{_text(case.invoice_number)}\n"
        "</div>\n"
        f'<div class="notice" style="margin-top:8px">\n{_text(notice)}\n</div>\n'
        "</div>\n"
    )


def build_html(case: SoakCase, index: int) -> str:
    """One invoice, in the fixture's own frame."""
    party = case.counterparty
    issued = FIRST_ISSUE + timedelta(days=index)
    due = issued + timedelta(days=DUE_DAYS)
    stamp = "%d %b %Y"
    return (
        f'{frame()}<div class="hdr">\n'
        f'  <div><div class="brand">{_text(party.brand)}</div>'
        f'<div style="font-size:9.5pt;color:#444">{_text(party.tagline)}</div></div>\n'
        f'  <div class="meta">INVOICE No. {_text(case.invoice_number)}<br>'
        f"Issued {issued.strftime(stamp)}<br>Due {due.strftime(stamp)}</div>\n"
        "</div>\n\n"
        "<h2>Billed to</h2>\n"
        "Quanta Technologies S.L.<br>Calle Serrano 41, 28001 Madrid, Spain\n\n"
        "<h2>From</h2>\n"
        f"{_text(party.legal_name)}<br>{_text(party.address)}<br>\n"
        f"{_text(case.email)} &nbsp;·&nbsp; {_text(case.sender_domain)}\n\n"
        f"<h2>Items</h2>\n{_items(case)}\n\n"
        f"{_bank(case)}\n"
        f'<div class="foot">{_text(party.legal_name)} · VAT {_text(party.vat)} · '
        f"Questions: {_text(case.email)}</div>\n"
        "</body></html>\n"
    )


def _needs_render(case: SoakCase, force: bool) -> bool:
    target = PDF_DIR / f"{case.case_id}.pdf"
    return force or not target.exists() or target.stat().st_size == 0


async def _render(case: SoakCase) -> str:
    """Convert one written invoice, retrying while the renderer is throttled."""
    html_path = PDF_DIR / f"{case.case_id}.html"
    target = PDF_DIR / f"{case.case_id}.pdf"
    error = "not attempted"
    for attempt in range(RENDER_ATTEMPTS):
        result = await foxit_generate_document(
            template_path=str(html_path),
            data={},
            document_name=case.case_id,
            output_path=str(target),
        )
        if result.ok:
            return ""
        error = result.error or "no detail"
        await asyncio.sleep(RENDER_PAUSE_SECONDS * (attempt + 1))
    return f"{case.case_id}: {error}"


async def ensure_corpus(cases: tuple[SoakCase, ...], *, force: bool = False) -> list[str]:
    """Write every invoice and render the ones that have no PDF yet.

    Sequential with a pause between conversions, because the renderer answers 429
    to a burst and a corpus half rendered is worse than one rendered slowly. A PDF
    already on disk is never re-rendered, so a repeated soak costs the renderer
    nothing at all.

    Mutates external state: converts HTML to PDF through Foxit PDF Services, a
    different product from eSign that creates no envelope and signs nothing.
    """
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    for index, case in enumerate(cases):
        path = PDF_DIR / f"{case.case_id}.html"
        path.write_text(build_html(case, index), encoding="utf-8")
        if not _needs_render(case, force):
            continue
        failure = await _render(case)
        if failure:
            failures.append(failure)
        await asyncio.sleep(RENDER_PAUSE_SECONDS)
    return failures


def pdf_path(case: SoakCase) -> str:
    return str(PDF_DIR / f"{case.case_id}.pdf")


__all__ = ["PDF_DIR", "build_html", "ensure_corpus", "frame", "pdf_path"]
