# Doctavian — Generate It Right. Sign It Tight.

## Status: authenticated, uploading, blocked in their generator

Auth is solved. `GET /v1/documents/document/list` returns 200 with the bearer from
their portal plus the api-key, and both `template/upload` and `data/upload` return
201 with a storage id.

`POST /v1/documents/document/generate` returns **500 `TEMPLATE_READ_FAILED` /
`GENERATE_FUNCTION_FAILED`** on every attempt. Event ids for their support:
`bab3e41a-271b-41c7-ac87-a8b0afe8b16e`, `3ff066b6-f011-494f-93fb-8d9bc1bce156`,
`f8a6addc-c421-461e-90ec-f9805dadd83c`.

Ruled out, one at a time:

| Tried | Result |
|---|---|
| Minimal python-generated .docx | same 500 |
| Fully formatted .docx with tables and styles | same 500 |
| .docx produced by a different engine, `file` reports "Microsoft Word 2007+" | same 500 |
| `urn` as bare GUID, and as `GUID:filename` | same 500 |
| `{{placeholder}}` syntax | same 500 |
| Documented `<mdoc:text>` element syntax | same 500 |
| Fresh upload immediately before each attempt | same 500 |

The failure is on the read, before any template parsing, which is why the syntax
made no difference.

## What their template documentation reveals

The generator is **Maven Documents**, and it is Salesforce-native. Its own reference
states the purpose plainly: *"to keep the flexibility of standard document generation,
while also incorporating data from the Salesforce database"*, and *"on Salesforce,
users define the dynamic data they want inside an element"*.

Elements are written as HTML-like tags inside the document — `mdoc:repeater`,
`mdoc:table`, `mdoc:text` — and the parameters that carry data are Salesforce field
expressions. The REST API exposes `loadMethod: Storage` as an alternative to
`Salesforce`, but the template model underneath assumes an org.

That is a plausible explanation for a read that fails before parsing, and it is a
guess: we could not confirm it, and said so when reporting it.

## Original status note

Doctavian provisioned a hackathon account ("Team Carlos") on their demo
environment:

    base URL   demo.api.doctavian.com
    auth       x-api-key header, plus a bearer from the self-service portal
    limits     10 MB per upload, 1000 generations and signings

The api-key alone is accepted — an unauthenticated call now fails with
`Authorization header is missing` rather than `ApiKeyInvalid`, which confirms
the gateway validates the key before the bearer. The bearer is issued from
https://demo.portal.doctavian.com/self-service/developers and there is no
programmatic path to it on the demo environment: `/v1/common/service/token`,
`/public/v1/auth/token` and `/v1/common/client/token` all return
`OperationNotFound`, which settles the contradiction in the published
documentation about that last one.

## What it generates

Not the payment, and not the contract. When the verdict says a bank detail
changed on an unverified sender, the correct artefact is an **out-of-band bank
verification request**: a document the vendor must confirm through a channel the
attacker does not control.

The agent shapes the structured payload for a fixed template. It never writes
prose that ends up inside a legal instrument.

## Contract, as read from the OpenAPI

    POST /v1/documents/document/generate
      template.urn, template.fileFormat (docx|xlsx), template.loadMethod
      data.loadMethod, data.urn
      headers: x-api-key, Authorization

## Traps documented for whoever picks this up

**Uploaded templates are deleted from Storage after the generation that
consumes them**, whether it succeeds or fails. A repeated run must re-upload.

**Extension validation is case-sensitive**: a `.DOCX` is rejected.

**The gateway validates `x-api-key` before the bearer**, so both credentials are
required and a missing api-key surfaces as `ApiKeyNotFound` rather than a 401
about the token.

`POST /v1/common/client/token` appears in the authentication guide with a full
example but in none of the 109 paths of the published OpenAPI. We asked.
