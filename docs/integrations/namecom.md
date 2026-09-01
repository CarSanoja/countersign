# name.com — Domain API Challenge

## What the integration does

Domain intelligence is the fraud signal, not a feature bolted on. Remove it and
COUNTERSIGN cannot tell a real vendor invoice from an impersonation.

## Endpoints used

| Endpoint | Environment | Why |
|---|---|---|
| `GET /core/v1/hello` | both | connectivity and credential check |
| `GET /core/v1/accountinfo/balance` | sandbox | confirms funds before a defensive registration |
| `POST /core/v1/domains:checkAvailability` | **production** | the sweep: 41 names in one call |
| `POST /core/v1/domains` | **sandbox** | defensive registration of a high-risk variant |
| `POST /core/v1/domains/{d}/records` | sandbox | TXT marker on a domain we hold defensively |
| `GET /core/v1/domains/{d}/records` | sandbox | reads the marker back |

## The environment split, and why it matters

Availability is queried against **production**. The sandbox keeps its own
registry, so asking it who holds `narne.com` tells you nothing about the world;
a demo built on sandbox availability would be theatre. Registration happens in
**sandbox**, where the test credit lives and no real domain is bought.

This is an explicit parameter on every call, never a global flag.

## The sweep

`domain/lookalike.py` generates confusable variants across eight attack classes
— TLD swap, hyphen, omission, doubling, transposition, homoglyph, adjacent key,
suffix — and round-robins the selection so a 40-name budget never drains on TLD
swaps before reaching the homoglyph that actually fools a person.

Measured against the production registry, `name.com` itself has **20 of 34**
confusable variants already registered, including `narne.com`: `rn` for `m`.

## What we are careful not to claim

`checkAvailability` answers *registered or available*. It never answers *who
owns it*. A taken variant may well be the vendor's own defensive registration,
so the signal is `confusable_already_registered` — the surface is occupied —
and never that anyone is an attacker. The signal name was changed from an
earlier, stronger one for exactly this reason.
