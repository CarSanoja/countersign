# Build story

Required by the Xano challenge; useful context for every other track.

## What was replaced

The vendor-onboarding and contract-execution module of a procurement suite —
the Coupa / Ariba / Ironclad shape. Supplier gets added, bank details recorded,
contract goes out for signature. In practice: a queue of email attachments and
someone in finance with four minutes per document.

That four minutes is the control that BEC defeats, and it cost **$3.05 billion**
in reported losses in 2025.

## Why this one

Three reasons, in order:

1. It is the exact point where money leaves the company on the strength of a
   document nobody verified.
2. It is judged by a criterion nobody applies to it today: an auditable trail of
   what was checked, against which source, by whom.
3. Every check it needs is an API call, and none of them is a model's opinion.

## Time

| | |
|---|---|
| Start | 31 August 2026, morning |
| First full run against live APIs | 1 September, early hours |
| Working end to end | 1 September |
| Elapsed | **~2.5 days**, one person |

The git history is the real record; no commit was backdated.

## How AI was used

**Claude Code** as the primary engineer, driving two multi-agent workflows:

- **Contracts** — five agents in parallel, one per sponsor API, each reading the
  live documentation and returning a structured contract with an explicit
  `confidence` and an `unknowns` list. This is where the expensive surprises
  surfaced before any code was written: that Nutrient is two products with
  separate keys on one host, that the free Processor tier watermarks output,
  that Foxit eSign issues its own credential pair.
- **Fleet** — eight agents implementing the tools, the seven-agent fleet, the
  orchestration and the demo surface against interfaces that were fixed first.

Thirteen agents, zero failures, roughly 40 minutes of wall clock.

**Gemini 3.5 Flash and Flash-Lite** on Vertex are the runtime models — four of
the seven agents call one. Three deliberately do not: the domain sentinel is
deterministic so its signal survives an audit, the envelope preparer is plumbing
that must not have opinions, and the injection screener stays out of a model
because asking one whether a document is trying to manipulate a model puts the
judgement inside the blast radius.

That split moved during the build, and in one direction. Four times a fact a
rule could settle had been handed to a model, and each time it was decided
differently between runs or not at all: the sender domain, the bank-detail
change, the IBAN, and the sender-versus-official comparison. The model's job
narrowed to the two places where judgement is genuinely required — deciding
whether a search result is the same legal entity, and writing a verdict that
cites its evidence.

## What that bought, and what it did not

Delegation was fastest where the work was narrow and the contract was fixed:
one provider, one file, a schema to return. It was worst at the seams. Every
agent's code passed its own tests; almost everything that broke was between
them — a config that could not carry signature fields, a settled signal the
synthesiser was allowed to drop, a test suite that passed on a clean machine
and failed with credentials loaded.

The lesson, stated plainly: **agents are good at building parts and bad at
noticing that the parts do not meet.** Integration stayed hand-work.

## What AI + Xano bought, together

Worth separating from the general "AI made it faster" claim, because the
acceleration here comes from the combination and not from either half.

Xano's Metadata API makes the backend addressable by code: tables, columns, an
API group and the endpoints inside it are all HTTP calls. That is what made it
something an agent could build at all. `vendors`, `audit_log`, their fourteen
columns, the `countersign` API group and the `GET /vendor` endpoint whose logic
is XanoScript running inside Xano were created in minutes of calls, with nobody
in the dashboard.

The honest part is that the first attempt failed completely — all fourteen
columns came back `000`, a zsh quoting bug in our loop, not a Xano problem —
and the fix was to rewrite the loop in Python and run it again. That is the
actual purchase: the schema is a script, so a mistake costs a re-run instead of
undoing fourteen fields by hand. It paid a second time when `vendors` turned out
to be landing nearly empty, because Xano drops unknown fields silently: the ten
missing columns were an edit to the script, not an afternoon of clicking.

What the combination did not buy is knowledge of the surface. That
`POST /table/{id}/schema` returns 404 and `POST /table/{id}/schema/type/text`
is the real path was found by trying, and so was the `text/x-xanoscript`
content type on the endpoint `PUT`. Agents move fast against a documented API
and blindly against an undocumented corner of one.

## Time saved, honestly

Building the same thing solo without agent delegation: the API research alone
took thirteen agents about forty minutes and surfaced findings we would not
have hit until we tried to demo. Call it a week of work compressed into two and
a half days — a **~3x** speed-up, not the 10x the category likes to claim.

The compression is in breadth, not depth. Six APIs researched and integrated in
parallel is the win. The architecture, the interfaces and every integration bug
were still hand-work.
