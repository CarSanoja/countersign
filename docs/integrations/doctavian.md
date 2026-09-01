# Doctavian — Generate It Right. Sign It Tight.

## Status: integrated, unconfigured

The tool module is written and the pipeline calls it. The generation stage is
skipped at runtime because Doctavian requires an **enterprise Microsoft or
Google account** — personal accounts are not supported — and one was not
provisioned in time. The stage records itself as skipped and the run continues.

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
