# SerpApi — Best AI Use Case

## The hard part is not the search

"Acme Corp" returns hundreds of results about unrelated companies. The
judgement COUNTERSIGN needs is *which of these is the same legal entity as the
one on this invoice*, and only then *is this coverage adverse*.

A namesake with a lawsuit is not a risk signal. Confusing the two is the most
expensive mistake this agent can make, so the disambiguation runs before the
adverse-media read, and dismissed namesakes are recorded rather than discarded.

## Three engines, three questions

| Engine | Question |
|---|---|
| `google` | which domain is the vendor's official web presence? |
| `google_news` | is there adverse coverage about *this* entity? |
| `google_maps` | is the invoiced address a trading business or a mail drop? |

Three credits per counterparty. The free tier allows 250 a month, so the
benchmark is budgeted and no test spends a live search.

## What live data buys that a model cannot have

No model knows whether a domain was registered last week or whether a company
filed for insolvency yesterday. Those questions are asked at decision time.
Every conclusion carries a `SourceRef` with the result URL; a judgement without
one is rejected by the schema, not merely flagged.

## A correction we made

Absence of a Maps listing was initially treated as evidence the premises were
fake. It is not: plenty of real companies have no Maps entry, and in our own
benchmark the vendor's official site listed the invoiced address while Maps did
not. The signal now requires positive evidence — a mail drop, or a different
business trading there. Absence of evidence is not evidence of absence, and
letting it act as one was making the verdict swing between runs.

SerpApi also reports "no results" through its `error` field. For adverse media,
finding nothing is the good outcome; treating it as a failed call was degrading
the stage.
