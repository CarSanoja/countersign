# COUNTERSIGN

An agent fleet that does the whole vendor-onboarding workflow and is
structurally unable to sign or to pay.

Built for the [DevNetwork API + Cloud + AI Hackathon 2026](https://api-cloud-ai-hackathon-2026.devpost.com/).

## The problem

Business Email Compromise moved **$3,046,598,558** in reported losses in 2025 —
the second largest crime category by loss in the FBI's IC3 report, behind only
investment fraud, across 24,768 complaints at a $123,005 median. The FBI's
Recovery Asset Team froze 57% of what it chased, and only when victims noticed
within hours.

The vector is almost always the same: an invoice from a domain that looks like
the vendor's. The control that should stop it is a person in finance looking at
a PDF for four minutes.

## What it does

Drop in an invoice. The fleet runs six stages and stops before the seventh.

| Stage | Provider | What it does |
|---|---|---|
| ingest | Nutrient DWS | deterministic parse; the model only maps spans to named fields, each keeping the page box it came from |
| identity | SerpApi | is this the same legal entity? is the coverage adverse or a namesake? |
| domain | name.com | sweeps 40 confusable variants across 8 attack classes; reports which are already registered |
| risk | — | fuses the evidence into a verdict where **every claim cites its span** |
| generation | Doctavian | drafts the out-of-band bank verification document |
| delivery | Foxit eSign | prepares the envelope and **stops** |
| persistence | Xano | vendors, workflow state, append-only audit log |

## The claim, and why it is checkable

`execute_signature` and `release_payment` are not withheld by a prompt. They are
capabilities no agent in the fleet holds, checked in `fleet/capabilities.py`,
and an unmapped tool resolves to `None` so the gate fails closed.

The envelope preparer asks for the signature on every single run. It is denied
every single time, and the denial is written to the audit log rather than
hidden:

    seq=5  envelope-preparer  foxit_execute_signature  deny

`tests/test_boundary.py` fails if anyone ever grants an agent the power to sign.

## A real run

    ingest       completed  7 fields anchored
    identity     degraded   3 search credits spent
    domain       completed  24 names checked, 8 confusables already registered
    risk         completed  verdict with cited signals
    generation   skipped    no Doctavian credentials
    delivery     completed  envelope 35670939 left in DRAFT, awaiting a human signer
    persistence  completed  9 audit rows written

Nothing there is mocked. The envelope really exists in Foxit, in draft, unsent.

## Running it

    uv venv --python 3.12 .venv
    uv pip install --python .venv/bin/python -e .
    cp .env.example .env.local     # then fill it in
    set -a; . ./.env.local; set +a
    .venv/bin/python demo/run_demo.py

Every provider degrades on its own: if a credential is missing, that stage is
recorded as skipped and the run continues. A key that never arrives costs one
stage, never the run.

## Built on

The capability ledger, permission gate, prompt-injection screening, human review
queue and evidence-span verification come from
[quanta-gradesync](https://github.com/CarSanoja/quanta-gradesync) (Apache-2.0),
an agent-fleet framework already running in production. COUNTERSIGN is a new
domain on top of it, not a fork.

## Honest limitations

- The domain sweep answers *registered or available*, never *who owns it*. A
  taken variant may well be the vendor's own defensive registration. The signal
  is that the surface is occupied, not that anyone is an attacker.
- `identity` currently reports `degraded`; entity disambiguation needs work.
- Doctavian requires an enterprise Microsoft or Google account, so the
  generation stage runs unconfigured here.
- Foxit's envelope fetcher could not retrieve from every public host we tried.

See `notes/LEDGER.md` for the full build log, including what failed.
