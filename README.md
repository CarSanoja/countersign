# COUNTERSIGN

An agent fleet that does the whole vendor-onboarding workflow and is
structurally unable to sign or to pay.

Built for the [DevNetwork API + Cloud + AI Hackathon 2026](https://api-cloud-ai-hackathon-2026.devpost.com/).

## Measured, not asserted

Six labelled invoices, every sender domain's registration status checked against
the production registry, two runs each. `demo/benchmark/measure.py` reproduces
this end to end against live APIs and writes `demo/benchmark/scorecard.json`.

| Metric | Result | Why it is the metric |
|---|---|---|
| Verdict accuracy | **6/6** | including the two negatives: a real invoice must come back clear |
| Reproducibility | **6/6** | the same invoice twice must give the same verdict, or it cannot be trusted once |
| Sources that match retrieved evidence | **35/35** | every citation checked against what the run actually collected, not just that the field is filled |
| Providers citing in verdicts | **3/3 (namecom, nutrient, serpapi)** | live data has to change the answer, not decorate it |
| Fabricated source rejected | **yes** | a draft citing evidence nobody collected is refused, checked adversarially |
| Signature denied | **12/12** | the agent asks on every run and is refused on every run |
| Probes denied through the real gate | **4/4** | the probe raises if the gate ever lets it through, so a permissive gate breaks the benchmark |
| Human-only powers denied | **16/16** | every agent in the roster, against every reserved power |
| A granted call still allowed | **yes** | rules out the gate that passes by denying everything |
| Median latency | **40.4s** | against the four minutes a person spends, and misses |

Two of the six are negatives, and they are the harder half: a control that flags
every invoice is a control finance mutes. `name.com` itself has 20 of 34
confusable variants registered, so an invoice that genuinely came from
`name.com` still has to come back `clear`. See `docs/integrations/namecom.md`.

The verdict level is measured given a known official domain. Establishing that
domain is itself part of the run — SerpApi discovers it when it is not supplied —
but the accuracy figure holds it fixed so the number means one thing.

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

## Reversible work is delegated. Irreversible work is not.

The distinction is Foxit's own. Their open-source MCP server publishes 40 tools
for the reversible work — generation, conversion, merging, compression, OCR,
extraction — and leaves signature deliberately out of that toolset. COUNTERSIGN
takes that line and makes it structural.

Every stage above is undoable: a parse re-runs, a sweep re-runs, a verdict can
be overturned by a person who reads the same spans, a `DRAFT` envelope can be
deleted. A signature is not, and a payment is not — so no agent in the fleet is
issued the power to execute either.

`execute_signature` and `release_payment` are not withheld by a prompt. They are
capabilities no agent in the fleet holds, checked in `fleet/capabilities.py`,
and an unmapped tool resolves to `None` so the gate fails closed.

The envelope preparer asks for the signature on every single run. It is denied
every single time, and the denial is written to the audit log rather than
hidden:

    seq=5  envelope-preparer  foxit_execute_signature  deny

`tests/test_boundary.py` fails if anyone ever grants an agent the power to sign.
The argument for putting the line exactly there — and what a threshold-based
boundary would have cost — is in `docs/integrations/foxit.md`.

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
    .venv/bin/python demo/run_demo.py            # the whole pipeline
    .venv/bin/python demo/run_from_prompt.py     # the same run, from a plain instruction
    .venv/bin/python demo/benchmark/measure.py   # the labelled set and the scorecard

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
- The sender-to-official comparison uses a short table of compound suffixes
  rather than the full public suffix list. Under a rarer compound suffix, or a
  hosting suffix like `github.io`, two unrelated names can read as one
  registrant.
- `identity` currently reports `degraded`; entity disambiguation needs work.
- Doctavian requires an enterprise Microsoft or Google account, so the
  generation stage runs unconfigured here.
- Foxit's envelope fetcher could not retrieve from every public host we tried.

See `notes/LEDGER.md` for the full build log, including what failed.
