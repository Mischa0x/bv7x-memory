# bv7x-memory

**A pre-committed track record you can ask questions of.**

Since February 2026 the BV-7X oracle has published every Bitcoin call it makes
to Base — committed *before* the outcome is known, attested via EAS,
reconstructible from IPFS. That started as accountability. What it became is a
record nobody can edit after the fact, us included, which turns out to be the
only kind worth querying.

This tool turns that record, and the strategy fleet's nightly cross-section,
into structured memory on the [Sibyl Memory](https://github.com/Sibyl-Labs/Sibyl-Memory)
plugin — and demonstrates the finding that motivated it.

## The finding

The aggregate is unremarkable:

```
40/71 = 56.3%  [95% CI 44.8–67.3]
```

One filter later, on the same rows:

```
UP    27/38 =  71.1%  [95% CI 55.2–83.0]
DOWN  13/32 =  40.6%  [95% CI 25.5–57.7]
```

A **30.4 percentage-point gap**, invisible to every query that asked only for
the average. Six consecutive in-house accuracy programmes optimised straight
past it, because every one of them looked at the aggregate. Internally that is
BV7X-180; it went unfound for months.

## The part that matters more

Bucketing the same calls by the model's own stated confidence appears to reveal
a second, bigger finding — the model is *worst* exactly where it is most
confident (8/26) and best where it is least (17/24). Inverted calibration would
be a headline.

Cross the two filters and it dissolves. **Every** high-confidence call is a
DOWN call; **every** medium is an UP call. The buckets are collinear with
direction, so "inverted calibration" is the direction split wearing a different
label — one finding, not two.

The demo walks through that dissolution on purpose. A memory that answers
everything is how you inherit noise as if it were structure. Retention without
uncertainty is not an asset; it is a way to compound luck.

## Run it

Requires Python 3.11+ and the Sibyl Memory client.

```bash
pip install 'sibyl-memory-cli[mcp]'

./sibyl_demo.py backfill    # load both records into a local SQLite store
./sibyl_demo.py demo        # the four-question narrative
./sibyl_demo.py status      # what memory holds
./sibyl_demo.py ask --record oracle --direction UP
./sibyl_demo.py ask --record oracle --direction DOWN --regime FALLING
./sibyl_demo.py ask --record fleet
```

No account, no API key, no network writes. The oracle record is fetched from a
public endpoint anyone can hit; the fleet record ships frozen in `data/`, so
every panel runs on your machine exactly as it runs on ours.

| env var | default |
|---|---|
| `SIBYL_DEMO_STORE` | `~/.sibyl-memory/bv7x-demo.db` |
| `BV7X_AGENTS_DB` | unset — falls back to `data/fleet-nights.json` |

## Two records, never merged

| | chain | what |
|---|---|---|
| **oracle** | Base mainnet 8453 | first-party attester; every call committed before the outcome |
| **fleet** | Base Sepolia 84532 | strategy-agent fleet, night aggregates, the obedience buckets |

There is deliberately **no code path that unions them**. `ask` takes exactly one
`--record`, the loaders write disjoint entity categories, and a registry state
document declares the rule inside the store itself. A combined accuracy figure
across two chains and two attesters would be meaningless.

## Honesty gates, enforced in code

1. **`MIN_N = 30`** — no rate printed below 30 resolved calls. Counts, yes; a
   percentage, no. This fires constantly in the demo, and it is meant to.
2. **Wilson 95% intervals** beside every rate, so `n` is never invisible.
3. **Only resolved calls** enter the accuracy path. An open call's direction is
   a product we sell; this tool never prints it.
4. **Derived fields are labelled.** `regime_derived` and `confidence_bucket` are
   computed here, not attested.

Confidence buckets are fitted to the live distribution rather than guessed. The
model's confidence spans 0.500–0.638 and is massed at the floor, so a textbook
`>= 0.65` "high" bucket matches **nothing** — and an empty bucket does not read
as a mis-specified filter, it reads as *"this model never has conviction,"*
which is false.

## Obedience is not performance

Fleet nights are stored as aggregates, never per-agent — the free-tier cap and
statistical power agree that thirty resolutions a season carries no signal
while cohort/night carries thousands.

The buckets separate `failed` from `abstained`, because an agent that **could
not** call is not an agent that **chose not to**. Conflating them wrote 7,936
false stand-asides into our own track record across four nights before it was
caught (BV7X-264); the snapshot in `data/` shows the outage plainly rather than
hiding it. Performance asks *"was it right."* Obedience asks *"did it do what it
said."* Only the second tells you whether to buy the signal.

## Where memory is load-bearing

**Honest status: in this prior-work snapshot, it is not yet.** Backfill fetches,
stores, and reads back; delete the memory calls, hold the rows in a list, and
the output is identical. Memory here is a cache — recomputable from the ledger,
which is a virtue architecturally and a failure against a deletion test.

The build turns that around by making memory hold **what a fresh fetch cannot
know**: the hypothesis ledger. Which question was asked, when, at what `n`, and
what the verdict was. A public API returns current state only — it can never
tell you which questions you already asked, or which findings you already
burned. Concretely:

- **Pre-registration by construction.** A finding is reportable only if its
  query was registered *before* the data that confirms it arrived. Without
  persistent memory there is no "before".
- **Burned hypotheses stay buried.** The confound above becomes a remembered
  fact with its cross-tab, so the tool refuses to resurface inverted
  calibration as though it were new.
- **Watermarked accrual.** Each run scores only newly settled calls, so the
  labeled cross-section compounds instead of being recomputed.

Delete memory from that and the tool re-reports dead hypotheses, loses every
verdict, and cannot tell new evidence from old — it degrades visibly, which is
the point.

## Prior Work declaration

Per the hackathon rules, disclosed in full:

- `sibyl_demo.py`, its README, and the frozen fleet snapshot were **built on
  2026-08-31, before the Sep 1–10 build window**, and are carried in as prior
  work. Original home: `scripts/sibyl-demo/` in a private BV-7X repository.
- The **BV-7X protocol, oracle, attestation pipeline and agent fleet** are
  pre-existing production systems dating to February 2026. They are the data
  source, not hackathon output.
- The **thesis** this implements — memory as heredity for a market that already
  has variation and selection — was written 2026-08-26.
- **Everything after Sep 1** is hackathon work and lands in this repo's commit
  history as such.

## The thesis

A market without memory is selection without heredity — it can reward, but it
cannot evolve. BV-7X already has variation (thousands of mutually distinct
strategy predicates) and selection (staked claims settled in USDC, scored for
marginal information). Memory is the third part: retention.

Every settlement produces a labeled fact — who believed what, against whom, and
what proved true. Without memory those labels collapse into per-agent tallies
and evaporate. With it they accumulate into structure, and the structure feeds
back.

**Memory doesn't make the agents smarter. It makes the protocol smarter than
its agents** — the same field, read better, with no individual agent improving
at all.

The honest limit: retention cannot create information the inputs do not
contain. What it does is find, weight, compensate and inherit every unit of
information that does enter.

## License

MIT — see [LICENSE](./LICENSE).
