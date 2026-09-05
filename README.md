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

## The gate: deleting memory changes the answer

`quorum/record.py` writes a decision record for every call into Sibyl memory —
not a stored blob, but a JOIN of (rule, snapshot) that `why.py` reconstructs on
read. From it the field's belief is computed two ways:

- **with memory** — the *evidenced* subset, the calls that rested on a condition
  that actually held, with a Wilson interval;
- **without memory** — the naive vote count, which needs no store at all.

On the night of 27 August 2026 those disagree: the naive vote is **54.3% UP**
(CI [50.6, 57.9] — a verdict) and the warranted belief is **47.8% UP**
(CI [43.8, 51.8] — no lean, on the other side of the line). Sibyl scores an
entry by deleting the memory layer; ours changes the answer when you do.

```
./deletion-test.sh                 # ingest the frozen field, print with vs without
python3 -m unittest tests.test_record -v   # gate logic, stdlib, no client
```

The whole field — 23,106 records across 21 nights — fits in **~4.1 MB**, under
the client's 5 MB free-tier cap, because records are normalised (rules once,
snapshots per night, a compact `rid:sid` row string) and the reconstruction data
lives in state rather than in FTS-indexed entities. An absent night renders
**CANNOT SAY**, never a default or a zero.

## The screen

```
python3 -m quorum serve          # http://127.0.0.1:8420 — stdlib only, no build step
```

One screen, one control. **WHY** — the signals that decided tonight, counted over
deciding atoms. **THE FIELD** — one node per call, lit if its rule fired, shadowed
if it defaulted through an else leg. **THE BELIEF** — the warranted rate, its
interval, and a verdict.

Then flip the switch. The shadowed nodes light up as if they were evidence, the
interval snaps to [50.6, 57.9], and the page emits a confident **UP** — the
direction its own evidenced agents contradict. Nothing about that transition is
staged: both answers are recomputed server-side per request.

**Memory is on the critical path, and the endpoint proves it.** `memory=on` opens
the store, reads the night's decision records and re-derives each call's basis
from (rule × snapshot). Nothing is cached; the response carries the wall-clock
milliseconds it took. `memory=off` is constructed *without opening the store at
all*, because the naive vote has to remain reachable with the memory layer
deleted — otherwise the comparison would be a claim rather than a demonstration.

Delete the store and the page still serves: WHY and THE BELIEF render **CANNOT
SAY**, the naive side keeps answering, and nothing invents a number. That is the
deletion gate on the surface a judge actually clicks, and it is pinned by tests:

```
python3 -m unittest tests.test_server -v   # 11 tests, stdlib; the gate over HTTP
```

The lattice math (`fibonacciLattice`, `depthOpacity`, `depthRadius`) is ported from
`polypool/web/src/hologram/sphere.ts` rather than reinvented, so the field here and
the swarm on app.bv7x.ai are the same object seen twice. The palette is BV-7X
FIRST LIGHT, and two of its laws do real work: the field ramp is ordered lit→shadow
as proximity to signal, which here means *did your rule fire*; and gold marks only
a verdict the interval supports. With memory on, most nights, there is no gold on
the page at all. That is the honest picture, and the brand already says so.

## Are they the same opinion? (a claim, tested, and refuted)

There is an obvious argument that the field is far smaller than it looks. A call
is a function of (rule, market snapshot); every agent sees the same snapshot on a
given night; so agents whose rules read the same signals should be one opinion
wearing many coats. On 27 August that would collapse **1,926 calls** into the
**72 distinct signal-configurations** behind them — by Kish's effective sample
size, about **56 opinions**, a 34× overstatement in every belief computed over
calls.

It is a good argument and it is wrong. If a configuration were an opinion, agents
inside one would agree far more than strangers do. So compare each cohort against
the agreement that `n` **independent** agents would reach by chance at the field's
own UP rate — `E[max(k, n-k)]/n` for `k ~ Binomial(n, p)`, computed exactly:

```
36 cohorts at n>=30
  observed agreement          56.07%
  expected if independent     56.53%
  excess                      -0.45pp
```

Agents that read the same signals are **statistically indistinguishable from
strangers**. A configuration fixes *which* signals a rule reads, not the
thresholds it reads them at — and thresholds are agent-specific, so two agents on
`{vix, roc7d}` split on the same snapshot. Earlier work found this at the atom
level ("facts fragment"); this reaches it independently at the cohort level.

Note how high the baseline is. 56% agreement *sounds* like consensus and is
exactly what coin flips produce at this sample size. A tool that reported the
56.3 and stopped would have manufactured a finding.

**And every number here is recoverable only from memory.** The published record
carries a direction per agent and nothing else; a configuration is a property of
the *rule*, and the rule is in the store. Delete it and the panel does not degrade
to an estimate — it returns CANNOT SAY, because the question cannot be asked. What
memory bought is not a better answer. It is the ability to ask, and to have it
come back *no*.

```
python3 -m unittest tests.test_cohorts -v   # 12 tests, stdlib
```

The clustering test is drilled in both directions: synthetic cohorts that really
are one opinion register as clustered, cohorts that split do not. A test that
could only ever pass would be decoration.

## The foundation: atom parity

`quorum/why.py` decides which facts produced a call. It is a port of the production
evaluator (`polypool/agents/services/predicateEval.js`) and it is tested against a
byte-identical vendored copy of that file on **every one of 23,106 live rows** from
21 Season 1 nights — not a sample. `tests/test_parity.py` carries two positive
controls so that "0 disagreements" is known to be a measurement: a mutated operator
flips 9 rows, and the evaluator's short-circuit order is asserted observable.

```
python3 -m unittest tests.test_parity -v      # stdlib, no database, no node
```

CI runs the JS oracle and the Python port as separate jobs. Provenance for the vendored
files, with git blob hashes, is in `tests/vendor/PROVENANCE.md`.

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
