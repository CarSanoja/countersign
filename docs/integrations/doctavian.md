# Doctavian — Generate It Right. Sign It Tight.

## Status: credentialed on the demo environment

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
