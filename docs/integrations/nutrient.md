# Nutrient DWS — deterministic, auditable, human-in-the-loop

## Why the extraction is deterministic first

Nutrient returns text and layout. The model is only allowed to **map spans that
already exist** onto named fields. It never reads the PDF itself and never
supplies a value, so the same document yields the same fields and every field
carries the page box it came from.

A field the model cannot anchor to a span is returned as **absent**, never
invented. That is the difference between an auditable extraction and a
plausible hallucination.

## Coordinates: the trap we hit

The two Nutrient products report boxes in different units — the Data Extraction
API in render pixels from the top-left, the Processor's `json-content` in PDF
points — and the render DPI is not documented or guaranteed stable.

`schemas/evidence.PageBox` therefore stores **fractions of the page**, validated
to 0..1. Page size is read from the PDF MediaBox, and a document with mixed page
sizes or a disagreeing CropBox is refused rather than given a box that pretends
to be a fraction.

## Endpoints used

| Endpoint | Why |
|---|---|
| `POST /build` (`json-content`) | layout and spans with boxes |
| `POST /build` (`html` part) | renders the benchmark invoices themselves |
| `POST /analyze_build` | prices a request without spending credits |
| `POST /build` (`createRedactions` + `applyRedactions`) | PII redaction |

## Order of operations, decided deliberately

Redacting the PDF before extracting makes the redacted fields unextractable. So
COUNTERSIGN extracts with the deterministic engine first, redacts the resulting
JSON using the spans to know where each value sat, and only then lets a model
see it. "PII is redacted before the model sees it" stays true, by the other
route.

## Two things worth knowing

They are **two products with separate keys on one host**. A Processor key
returns 401 on `/extraction/*`, which reads like a header problem and is not.

The free Processor tier stamps *For Evaluation Purposes Only* on output. A paid
`pdf_live_` key does not, which is what makes the rendered invoices usable.
