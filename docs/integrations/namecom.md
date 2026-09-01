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

## The edge cases are the benchmark

Four of the six labelled invoices are frauds. The other two are deliberate
negatives, and they are the harder half of the set: **a legitimate invoice that
must not alarm is a harder call than a fraudulent one, because a control that
fires on everything gets switched off.**

| Case | Sender | Expected | The trap it sets |
|---|---|---|---|
| `clean` | `name.com` | `clear` | the real vendor, bank details unchanged |
| `bank-change-only` | `name.com` | `review` | right domain, new account number |

The naive version of this integration fails `clean` outright. `name.com` has 20
of 34 confusables registered, so a rule that scores "confusables exist against
this vendor" would mark **every** genuine name.com invoice for review — and the
finance team that gets a flag on all of them stops reading flags by the second
week. `confusable_already_registered` is therefore a standing surface signal
about the vendor's namespace, never on its own enough to raise the level. What
moves the level is the *sender* not being the official domain.

`bank-change-only` is the same discipline one notch in. A changed account on the
correct domain is exactly the BEC payload, and it is also what happens whenever
a vendor genuinely switches bank. It earns `review` — a person, an out-of-band
call — and not `high`, because an alarm that is wrong half the time trains the
one person who could have stopped the fraud to click through it.

The fourth fraud is an edge case pointing the other way. `nane.com` is
registered to nobody, and the intuitive reading is that an unowned domain is
harmless. It is the opposite: an invoice whose sender domain nobody holds
cannot have come from a mailbox there, so `sender_domain_unregistered` raises
the level rather than lowering it.

## The edge case that would have sunk it

`invoices.name.com` is the vendor's own billing namespace; `narne.com` is an
attacker's homoglyph. A check that only asks whether the sender differs from the
official domain hands both the same signal, and the customer whose invoices all
arrive from a billing subdomain switches the sentinel off in week one.

So `domain/relation.py` names the relation before anything is raised:

| Sender, against official `name.com` | Relation | Raises `sender_domain_not_official` |
|---|---|---|
| `name.com` | same | no |
| `invoices.name.com` | subdomain | no |
| `name.net` | sibling TLD | **yes** |
| `narne.com` | confusable, homoglyph | **yes** |
| `acme-supplies.io` | unrelated | **yes** |

Sharing a registrable name is what makes a sender the vendor — and when the
official domain is recorded as a host, `www.name.com`, a sender at
`invoices.name.com` sits under the same registrable name and is the vendor too.
Carrying the same *label* under another suffix is not the same thing:
`name.net` is a separate purchase by whoever got there first, which is why the
benchmark expects `high` on it. The relation also carries the attack class, so
the claim reads "is a homoglyph variant of name.com" rather than a bare
"is not name.com".

The same rule governs the surface signal. `confusable_already_registered` is
suppressed when the sender is inside the vendor's own namespace: the variants
registered around `name.com` say nothing against a mail that came from
`name.com`.

**Where this still has an edge.** The suffix table in `relation.py` is a short
list of the compound suffixes invoices actually arrive under, not the full
public suffix list. Outside it the last two labels are read as the registrable
name, so a vendor under a rarer compound suffix, or under a hosting suffix such
as `github.io`, can be read as sharing a registrant with a neighbour that only
shares its suffix. It is written into the module's own docstring rather than
left for a judge to find.

## What we are careful not to claim

`checkAvailability` answers *registered or available*. It never answers *who
owns it*. A taken variant may well be the vendor's own defensive registration,
so the signal is `confusable_already_registered` — the surface is occupied —
and never that anyone is an attacker. The signal name was changed from an
earlier, stronger one for exactly this reason.
