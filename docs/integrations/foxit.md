# Foxit eSign — "Your Agent Shouldn't Sign That"

## Reversible and irreversible: Foxit's own line

Foxit's open-source MCP server publishes **40 tools for the reversible work** —
document generation, conversion, merging, compression, OCR, extraction — and
signature is **deliberately excluded** from that toolset. The distinction is
theirs. It is also the entire design of this project:

> **Reversible work is delegated. Irreversible work is not.**

Everything the COUNTERSIGN fleet does is undoable. A parse re-runs. A domain
sweep re-runs against the registry tomorrow and answers again. A verdict can be
overturned by a person who reads the same spans and disagrees. An envelope
sitting in `DRAFT` can be deleted and nobody outside the account ever knew it
existed.

A signature is not undoable. From the moment it is executed the instrument is
enforceable, and the remedy stops being technical and becomes legal. Payment is
worse still: the FBI's Recovery Asset Team froze 57% of what it chased, and only
where the victim noticed within hours.

So the fleet is built to reach the last reversible step and stop on it. The
powers it holds are the ones Foxit put in the toolset; the one it does not hold
is the one Foxit left out.

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

## Arguing with you: why the line sits exactly there

Foxit invites the argument, so here is a position rather than a description.

**The line is drawn by capability, not by confidence.** The tempting alternative
is a threshold: let the agent sign when the verdict comes back `clear`, escalate
when it does not. We rejected it, and the benchmark is the reason. The verdict
is a function of evidence the attacker partly supplies — the sender domain, the
document, the bank line. A boundary that moves with a score is a boundary the
attacker can move, and the attack stops being "write a convincing invoice" and
becomes "produce a `clear` verdict". A boundary made of a capability that was
never issued has no value to tune and no prompt that can talk it down.

**Putting the line further out gives away the only property worth having.** An
agent that signs and then flags for review has not added a control; it has
added a receipt. The point of a human in this workflow is not that they are
better at reading PDFs — they are not, they have four minutes — it is that
their signature is the act the counterparty relies on. Delegate that and there
is no longer anything for the audit trail to protect.

**Putting it further in buys nothing.** Stop one step earlier, with the agent
recommending and a person assembling the envelope, and the four minutes come
straight back. Assembly is reversible work. Handing it to a person is the
mistake in the other direction: it spends human attention on the part that a
retry fixes, and leaves less of it for the part that a retry does not.

**What the position costs us, stated plainly.** Throughput is bounded by human
availability: 39 seconds of work then waits in a queue that we do not control,
and the end-to-end time is theirs, not ours. And we pay it on every run,
including the obvious ones — a `clear` verdict stops at exactly the same place
as a `high` one. That is the price of a boundary with no dial on it, and it is
the price we would pay again: on the four fraudulent invoices in the benchmark,
a dial would have been set by the attacker and not by us.

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
