# Submission — Quorum, memory of why

Team **bv7x-80d2** · repo **[Mischa0x/bv7x-memory](https://github.com/Mischa0x/bv7x-memory)** (MIT)
· tracker **[bv7x.ai/sibyl](https://bv7x.ai/sibyl)** · video: _link on submission_

Submitted from the team's private build page. Build window Sep 1–10 2026,
deadline **Sep 10, 23:59 UTC**.

---

## The problem

Strategy agents on BV-7X publish a direction and a confidence every night, each
reading the same Bitcoin market. The protocol sells the
aggregate of those calls.

It has always kept the call. It has never kept the **reason** — which conditions
the agent's rule was watching, what they read that night, and whether they held.
Without the reason, a call that fired on its own evidence and a call that fell
through the rule's `else` leg are the same row, carrying the same confidence. So
the aggregate counts them the same, and it has been wrong about itself in a way
nothing in the record could reveal.

## The product

Quorum re-derives every call from `(rule × market snapshot)` and persists the
decomposition, so the field can be asked *why*, not just *what*. On top of that it
can do the thing the raw ledger cannot: separate earned confidence from unearned,
and decline to answer when what is left does not lean.

## What the agent persists, recalls, and uses

*(the memory-implementation note the checklist asks for)*

- **Persists** — per night: the market snapshot (17 signals), each agent's
  certified predicate, and the re-derived call with its `basis` (`evidenced` when
  a conjunction fired, `default` when an else leg did) and the deciding atoms.
  21 nights, 23,106 records, ~4 MB, through Sibyl entities plus a journal.
- **Recalls** — in a **fresh process** with no state carried over, `field <night>`
  opens the store and reconstructs that night's basis split. With no store it
  returns `CANNOT SAY` and the reason, never a default.
- **Uses** — the recalled basis decides three things it could not decide
  otherwise: which calls enter the belief (evidenced only), whether the belief is
  stated at all (a Wilson interval straddling 50% prints `no lean`), and, across
  nights, which rules have ever actually responded to the market. The last one is
  strictly temporal: it is classified from nights **before** tonight, so it is a
  fact only a memory can hold.

## Where memory is load-bearing (the pass/fail gate)

`./deletion-test.sh` is the judge's script. Delete the memory layer and the field
moves 6.5 points and **flips its verdict**:

```
WITH memory    (evidenced)   588 calls · 47.8% UP · CI [43.8, 51.8]  → no lean
WITHOUT memory (naive vote)  715 calls · 54.3% UP · CI [50.6, 57.9]  → UP
```

The product does not degrade to an estimate when memory is removed. It loses the
distinction that makes its answer meaningful, and says so.

## What it is worth, as a number

Accuracy is flat across the split and we do not claim otherwise. Conviction — the
Brier score on the confidence each call published — is not:

```
basis          n       accuracy      Brier
evidenced   3,269         50.0%     0.3675
default     6,124         49.7%     0.4318

as published (MEASURED)             0.4094   worse than our own oracle (0.3121)
default calls neutralised to 0.50   0.2909   better
both classes stated honestly        0.2500   better
```

Reproducible without our database: `python3 -m quorum.conviction`.

## Builders

- **Mischa0x** — BV-7X. _(add any co-builders before submitting.)_

## Base and Virtuals stack used

| Stack | Use | Evidence |
|---|---|---|
| **Base mainnet** (8453) | The frozen field and both gate answers committed to a digest and attested via **EAS** before judging | tx [`0xa0013b4f…291f`](https://basescan.org/tx/0xa0013b4ff269aca8f499ca619e360e1b3465c40e118eb572031176171b4f291f), attestation [`0x30431e64…cd50`](https://base.easscan.org/attestation/view/0x30431e642678aa1d0442c8373139e47d763f67af85899809174e5621cc78cd50), block 50904246 |
| **Virtuals ACP** | The BV-7X agent bought and completed a job end to end as client and evaluator | job **76546**, provider Otto AI, create `0xf1994cf1…` → fund `0x7119ac4e…` → complete [`0x1d7a818a…059bc`](https://basescan.org/tx/0x1d7a818a75f3d8402e88054443dd8761d05b4e621b9b0a6908abe5796ab059bc), 0.01 USDC settled |
| **EAS** | The first-party oracle has published every Bitcoin call to Base since Feb 2026, committed before the outcome | attester `0xd8B71d23…3e1e` |
| **ERC-8004** | Agent identity and reputation for the strategy agents | Base **Sepolia** (84532) — the agent lane is testnet; the token, staking and oracle attestations are mainnet |
| **Sibyl Memory** | The persistence layer: entities, journal, five-tier schema, no vector store | `~/.sibyl-venv`, packages `sibyl-memory-{client,cli,mcp}` |

## Run it in five minutes

```bash
git clone https://github.com/Mischa0x/bv7x-memory && cd bv7x-memory
export QUORUM_STORE=$PWD/quorum.db
python3 -m quorum field 2026-08-27          # CANNOT SAY — no store yet
python3 -m quorum ingest --from tests/fixtures/rows.json
python3 -m quorum field 2026-08-27          # a fresh process recalls and answers
./deletion-test.sh                          # the gate
python3 -m quorum.conviction                # what it is worth
python3 -m quorum verify                    # the Base commitment, offline
python3 -m unittest discover -s tests -t .  # 66 tests
```

## Prior work

Declared in full in the README. The BV-7X protocol, oracle, attestation pipeline
and strategy agents pre-date the window and are the data source, not hackathon output.
Everything after Sep 1 is in this repo's commit history.
