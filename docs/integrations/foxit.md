# Foxit eSign — "Your Agent Shouldn't Sign That"

## The brief, answered literally

The agent starts from a plain instruction, does the whole workflow, prepares the
signature envelope, and **cannot execute it**.

That is not a prompt asking it to behave. `signature.execute` is a capability
no agent in the fleet holds, checked in `fleet/capabilities.py`. A tool that
maps to no capability resolves to `None` and is denied, so the gate fails
closed rather than granting an unnamed power.

## The handoff, on the record

`envelope-preparer` asks for the signature on **every single run**, and is
denied on every single run. The refusal is written to the append-only audit log
rather than swallowed:

    seq=5  envelope-preparer  foxit_execute_signature  deny

A power never asked for would leave no evidence of being unavailable. Asking and
being refused is what makes the boundary auditable.

## Endpoints used

| Endpoint | Why |
|---|---|
| `POST /api/oauth2/access_token` | `client_credentials`, token cached for its lifetime |
| `POST /api/folders/createfolder` | prepares the envelope with `sendNow: false` |
| `GET /api/folders/list` | reads prepared envelopes back |

The envelope lands in `DRAFT` with `dispatched: false`. Envelope **35670939**
is a real one, sitting unsent in the account.

## Two findings, offered in good faith

**The envelope fetcher cannot reach every public host.** `raw.githubusercontent.com`
works; `w3.org` and `africau.edu` both fail with a generic
`error in downloading file from url`. The message does not distinguish an
unreachable host from a malformed request, which cost us hours.

**The file extension is read off `fileNames`.** A vendor legitimately called
Name.com turns `"Bank verification - Name.com Inc"` into file type `com`, and
the envelope is rejected. `_as_pdf_name` now guards it.

`GET /v1/common/status`, documented as a health-ping placeholder, returns 404 in
production.
