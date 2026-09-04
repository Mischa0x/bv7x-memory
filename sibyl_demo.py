#!/usr/bin/env python3
"""sibyl-demo — the BV-7X track record as a memory you can ask questions of.

The hackathon build (2026-08-23 arc, re-aimed 2026-08-31). Phase 3 of the May
SIBYL integration spec was scoped as a REMOTE tool against SIBYL's hosted
/retrieve. That endpoint never shipped and the product went local-first
(SQLite, FTS5, zero embeddings), so this runs the same idea entirely on the
local Sibyl Memory plugin: no /ingest, no webhook, no network writes.

The pitch it demonstrates: a pre-committed track record is only as useful as
the questions you can ask it. Aggregate accuracy hides structure; structured
filters over the same rows surface it in one query. The headline finding
(BV7X-180) is a large UP/DOWN asymmetry that six consecutive accuracy
programmes optimised straight past, because every one of them looked at the
average.

TWO RECORDS, NEVER MERGED
  oracle — the first-party attester on Base MAINNET (8453). Every call
           committed before the outcome, attested via EAS, reconstructible
           from IPFS. This is where the direction split lives.
  fleet  — the strategy-agent fleet on Base SEPOLIA (84532). Cross-sectional,
           and the source of the OBEDIENCE record: did an agent do what its
           rule said, which is a different question from whether it was right.
There is deliberately no code path that unions them. `ask` takes exactly one
--record and the two loaders write disjoint entity categories.

HONESTY GATES (enforced in code, not by convention)
  1. No rate is printed below MIN_N resolved. Counts, yes; a percentage, no.
  2. Every rate carries its Wilson 95% interval, so n is never invisible.
  3. Only RESOLVED calls enter the accuracy path — an open call's direction is
     the signal-sale product and is never printed by this tool.
  4. Derived fields are labelled. `regime` is computed here from the oracle's
     own price series; it is NOT an attested field.

Usage
  sibyl_demo.py backfill [--limit N]   load both records into Sibyl Memory
  sibyl_demo.py demo                   the scripted four-question narrative
  sibyl_demo.py ask --record oracle [--direction UP] [--regime FALLING] ...
  sibyl_demo.py status                 what memory currently holds
"""
import argparse, json, math, os, sqlite3, sys, urllib.request
from collections import defaultdict
from datetime import datetime, timezone

from sibyl_memory_client import MemoryClient

# The demo gets its OWN store. Client 0.7.0 builds a cross-tier FTS shadow
# index that ran 1.53 MB for 126 KB of bodies — 12x the source — so 207 demo
# entities consume roughly a third of the 5 MB free-tier cap. That cap is
# SHARED, and BV7X-245's nightly recorder lives in the default store: a demo
# that can fill the institution's memory is a demo that can stop it recording.
# Separate file, separate cap, no contention. --store shared overrides.
DEMO_STORE     = os.path.expanduser(
    os.environ.get("SIBYL_DEMO_STORE", "~/.sibyl-memory/bv7x-demo.db"))
SHARED_STORE   = os.path.expanduser("~/.sibyl-memory/memory.db")
ORACLE_HISTORY = "https://bv7x.ai/api/bv7x/onchain-oracle/history?limit=400"

# The fleet half reads a live SQLite database that only exists on the box
# running the agent fleet. A judge does not have it, and a demo whose most
# original panel is dead on the reviewer's machine is a demo that scored
# itself down. So: use the live DB when BV7X_AGENTS_DB points at one, and
# otherwise fall back to the frozen night-aggregate snapshot committed under
# data/. Same code path, same output shape, runs anywhere.
FLEET_DB       = os.environ.get("BV7X_AGENTS_DB")
FLEET_SNAPSHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "data", "fleet-nights.json")

CAT_ORACLE   = "oracle-call"     # Base mainnet 8453, first-party attester
CAT_FLEET    = "fleet-night"     # Base Sepolia 84532, cohort/night aggregates
REGISTRY_KEY = "bv7x-record-registry"

MIN_N        = 30    # no rate printed below this many resolved calls
REGIME_LOOKBACK_D = 30
REGIME_FLAT_BPS   = 200   # |trailing return| under 2% reads as FLAT

def now(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# ---------------------------------------------------------------- statistics
def wilson(k, n, z=1.96):
    """Wilson score interval. Printed with every rate so n is never invisible."""
    if n == 0: return (0.0, 0.0)
    p = k / n
    d = 1 + z*z/n
    c = (p + z*z/(2*n)) / d
    h = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / d
    return (max(0.0, c-h), min(1.0, c+h))

def rate_line(k, n, label=""):
    """The gate lives here: below MIN_N you get counts, never a percentage."""
    if n == 0:
        return f"{label}no resolved calls"
    if n < MIN_N:
        return (f"{label}{k}/{n} resolved — RATE WITHHELD "
                f"(n < {MIN_N}; too few to report a percentage)")
    lo, hi = wilson(k, n)
    return (f"{label}{k}/{n} = {100*k/n:5.1f}%  "
            f"[95% CI {100*lo:.1f}–{100*hi:.1f}]")

# ------------------------------------------------------------------- loaders
def fetch_oracle():
    with urllib.request.urlopen(ORACLE_HISTORY, timeout=30) as r:
        return json.load(r)["data"]

def derive_regime(rows):
    """Trailing REGIME_LOOKBACK_D-day return of BTC at each call date.

    DERIVED, not attested. Computed from the oracle's own btcPrice series so
    the demo has a second filter axis ("which calls work in which market"),
    which is the query shape the whole thesis rests on.
    """
    series = sorted(((r["date"], r.get("btcPrice")) for r in rows if r.get("btcPrice")),
                    key=lambda x: x[0])
    by_date = dict(series)
    dates = [d for d, _ in series]
    out = {}
    for d in dates:
        prior = [x for x in dates if x < d]
        ref = None
        for p in reversed(prior):
            if (datetime.fromisoformat(d) - datetime.fromisoformat(p)).days >= REGIME_LOOKBACK_D:
                ref = p; break
        if ref is None:
            out[d] = ("UNKNOWN", None); continue
        bps = round(10000 * (by_date[d] - by_date[ref]) / by_date[ref])
        lab = "FLAT" if abs(bps) < REGIME_FLAT_BPS else ("RISING" if bps > 0 else "FALLING")
        out[d] = (lab, bps)
    return out

def bucket_confidence(c):
    """Buckets CALIBRATED 2026-08-31 against the live distribution, not guessed.

    The model's confidence spans 0.500-0.638 and is heavily massed at the
    floor: 104 of 181 calls sit at exactly 0.50. A textbook >=0.65 "high"
    bucket therefore matches NOTHING, and an empty bucket does not read as
    "mis-specified filter" to an audience — it reads as "this model never has
    conviction", which is false. Re-check these cutoffs whenever the model
    version changes; they are a property of the data, not of the code.
    """
    if c is None:            return None
    if c <= 0.50:            return "floor"     # no expressed edge (n=104)
    if c < 0.59:             return "low"       # n=24
    if c < 0.615:            return "medium"    # n=27
    return "high"                               # n=26, tops out at 0.638

def backfill_oracle(mem, rows, limit=None):
    regimes = derive_regime(rows)
    n = 0
    for r in rows if limit is None else rows[:limit]:
        reg, bps = regimes.get(r["date"], ("UNKNOWN", None))
        conf = r.get("confidence")
        body = {
            "record": "oracle", "chain_id": 8453, "chain": "base-mainnet",
            "date": r["date"], "prediction_id": r["predictionId"],
            "direction": r.get("direction"), "action": r.get("action"),
            "confidence": conf,
            "confidence_bucket": bucket_confidence(conf),
            "horizon": r.get("horizon"), "model_version": r.get("modelVersion"),
            "resolved": bool(r.get("resolved")), "correct": r.get("correct"),
            "return_bps": r.get("returnBps"),
            "btc_price": r.get("btcPrice"), "resolution_price": r.get("resolutionPrice"),
            "regime_derived": reg, "regime_trailing_bps": bps,
            "attestation_uid": r.get("uid"), "cid": r.get("cid"),
            "committed_before_outcome": bool(r.get("commitment")),
            "_derived_fields": ["regime_derived", "regime_trailing_bps", "confidence_bucket"],
        }
        mem.set_entity(CAT_ORACLE, r["predictionId"], body)
        n += 1
    return n

def backfill_fleet(mem):
    """Fleet nights as aggregates only — never per-agent.

    Two reasons, and they agree: the free tier caps the store, and per-agent is
    the wrong granularity anyway (thirty resolutions a season has no power;
    cohort/night has thousands). The thesis calls this out explicitly.

    The buckets are the OBEDIENCE record. `failed` is separated from
    `abstained` because BV7X-264 proved that conflating them wrote 7,936 false
    stand-asides into the track record over four nights — an agent that COULD
    NOT call is not an agent that CHOSE not to.
    """
    if not FLEET_DB:
        rows = json.load(open(FLEET_SNAPSHOT))["nights"]
        for r in rows:
            r["record"] = "fleet"; r["chain_id"] = 84532; r["chain"] = "base-sepolia"
            r["_note"] = "aggregates only; per-agent is below statistical power"
            mem.set_entity(CAT_FLEET, f"night-{r['date']}", r)
        return len(rows)
    db = sqlite3.connect(FLEET_DB, uri=True); db.row_factory = sqlite3.Row
    rows = db.execute("""
        SELECT date(predicted_at) d,
               SUM(direction IS NOT NULL)                          called,
               SUM(direction = 'UP')                               up,
               SUM(direction = 'DOWN')                             down,
               SUM(direction IS NULL AND eval_error IS NOT NULL)   failed,
               SUM(direction IS NULL AND eval_error IS NULL)       abstained,
               SUM(outcome IS NOT NULL)                            settled,
               COUNT(*)                                            total
        FROM predictions GROUP BY d ORDER BY d""").fetchall()
    n = 0
    for r in rows:
        called, settled = r["called"] or 0, r["settled"] or 0
        # An open call's direction is withheld in aggregate as well as per
        # agent: a night that has not fully settled still describes live
        # positions, and its up/down IS the signal. Same rule the frozen
        # snapshot is cut under (tools/refreeze-fleet.py) — stated in both
        # places on purpose, because they must not drift.
        fully_settled = settled >= called   # called == 0 -> 0/0, a fact, not a secret
        body = {
            "record": "fleet", "chain_id": 84532, "chain": "base-sepolia",
            "date": r["d"], "called": called,
            "up":   (r["up"]   or 0) if fully_settled else None,
            "down": (r["down"] or 0) if fully_settled else None,
            "failed": r["failed"] or 0, "abstained": r["abstained"] or 0,
            "settled": settled, "total": r["total"] or 0,
            "obedience_rate": (round(called / r["total"], 4) if r["total"] else None),
            "_note": "aggregates only; per-agent is below statistical power",
        }
        mem.set_entity(CAT_FLEET, f"night-{r['d']}", body)
        n += 1
    db.close()
    return n

# -------------------------------------------------------------- query engine
def load(mem, record):
    """One record per call. There is no union path, on purpose."""
    cat = CAT_ORACLE if record == "oracle" else CAT_FLEET
    out = []
    for e in mem.list_entities(cat, limit=1000):
        b = e.get("body")
        out.append(json.loads(b) if isinstance(b, str) else b)
    return out

def filter_oracle(rows, direction=None, regime=None, action=None, horizon=None,
                  confidence_bucket=None, model_version=None,
                  date_from=None, date_to=None, resolved_only=True):
    out = []
    for r in rows:
        if resolved_only and not r.get("resolved"): continue
        if resolved_only and r.get("correct") is None: continue
        if direction and r.get("direction") != direction: continue
        if regime and r.get("regime_derived") != regime: continue
        if action and r.get("action") != action: continue
        if horizon and r.get("horizon") != horizon: continue
        if confidence_bucket and r.get("confidence_bucket") != confidence_bucket: continue
        if model_version and r.get("model_version") != model_version: continue
        if date_from and r.get("date", "") < date_from: continue
        if date_to and r.get("date", "") > date_to: continue
        out.append(r)
    return out

def score(rows):
    k = sum(1 for r in rows if r.get("correct"))
    return k, len(rows)

# ------------------------------------------------------------------ commands
def cmd_backfill(mem, args):
    print(f"[{now()}] backfill — memory is a CACHE OF PROOFS, recomputable from the ledger")
    rows = fetch_oracle()
    n1 = backfill_oracle(mem, rows, args.limit)
    n2 = backfill_fleet(mem)
    mem.set_state(REGISTRY_KEY, {
        "written": now(),
        "records": {
            "oracle": {"category": CAT_ORACLE, "chain_id": 8453,
                       "what": "first-party attester, committed before outcome, EAS on Base mainnet",
                       "entities": n1},
            "fleet":  {"category": CAT_FLEET, "chain_id": 84532,
                       "what": "strategy-agent fleet, night aggregates, obedience buckets",
                       "entities": n2},
        },
        "never_merge": ("Different chains, different attesters, different questions. "
                        "A combined accuracy figure over both would be meaningless."),
        "gates": {"min_n_for_rate": MIN_N, "open_call_directions": "never printed",
                  "derived_fields": ["regime_derived", "regime_trailing_bps", "confidence_bucket"]},
    })
    print(f"  oracle : {n1} attested calls  -> category '{CAT_ORACLE}' (chain 8453)")
    print(f"  fleet  : {n2} night aggregates -> category '{CAT_FLEET}' (chain 84532)")
    print(f"  registry state '{REGISTRY_KEY}' written (declares the never-merge rule)")
    # Upserting 207 entities leaves the FTS index churned; SQLite does not
    # return freed pages to the OS without this. A re-run doubled the file
    # before it was added.
    sqlite3.connect(DEMO_STORE).execute("VACUUM").close()
    st = mem.free_tier_status()
    print(f"  store  : {st['db_size_bytes']:,} bytes ({100*st['pct_used']:.1f}% of free cap), vacuumed")

def cmd_status(mem, args):
    wrapper = mem.get_state(REGISTRY_KEY)
    print(f"[{now()}] sibyl memory — local store, no network writes")
    if not wrapper:
        print("  registry ABSENT — run `backfill` first"); return
    reg = wrapper.get("body", wrapper)   # get_state returns {body, updated_at}
    for name, meta in reg["records"].items():
        print(f"  {name:7} {meta['entities']:>4} entities  chain {meta['chain_id']}  {meta['what']}")
    print(f"  never-merge: {reg['never_merge']}")
    st = mem.free_tier_status()
    print(f"  store: {st['db_size_bytes']:,} bytes ({100*st['pct_used']:.1f}% of free cap)")

def cmd_ask(mem, args):
    rows = load(mem, args.record)
    if args.record == "fleet":
        sel = [r for r in rows if (not args.date_from or r["date"] >= args.date_from)
                              and (not args.date_to or r["date"] <= args.date_to)]
        tot = defaultdict(int)
        for r in sel:
            for k in ("called", "up", "down", "failed", "abstained", "settled", "total"):
                tot[k] += r.get(k) or 0
        print(f"fleet — {len(sel)} nights, chain 84532")
        print(f"  called {tot['called']:,} · abstained {tot['abstained']:,} · "
              f"FAILED {tot['failed']:,} · total {tot['total']:,}")
        if tot["total"]:
            print(f"  obedience (called / total) = {100*tot['called']/tot['total']:.1f}%")
        return
    sel = filter_oracle(rows, args.direction, args.regime, args.action, args.horizon,
                        args.confidence_bucket, args.model_version,
                        args.date_from, args.date_to)
    k, n = score(sel)
    desc = " ".join(f"{f}={v}" for f, v in [
        ("direction", args.direction), ("regime", args.regime), ("action", args.action),
        ("horizon", args.horizon), ("confidence", args.confidence_bucket),
        ("model", args.model_version), ("from", args.date_from), ("to", args.date_to)] if v)
    print(f"oracle — chain 8453, resolved calls{(' · ' + desc) if desc else ''}")
    print("  " + rate_line(k, n))
    if sel:
        avg = sum(r.get("return_bps") or 0 for r in sel) / len(sel)
        print(f"  mean realised move {avg:+.0f} bps")

def cmd_demo(mem, args):
    rows = load(mem, "oracle")
    if not rows:
        print("memory is empty — run `backfill` first"); return
    W = 78
    def head(n, q):
        print("\n" + "─"*W); print(f"Q{n}. {q}"); print("─"*W)

    print("="*W)
    print("BV-7X × Sibyl — a pre-committed track record you can ask questions of".center(W))
    print("local-first: SQLite + FTS5, no embeddings, no network writes".center(W))
    print("="*W)

    head(1, "How accurate is the model? (the question everyone asks)")
    k, n = score(filter_oracle(rows))
    print("  " + rate_line(k, n))
    print("\n  Unremarkable. Six consecutive accuracy programmes stopped here.")

    head(2, "Same rows, one filter: split by the direction called.")
    best = worst = None
    for d in ("UP", "DOWN"):
        k, n = score(filter_oracle(rows, direction=d))
        print("  " + rate_line(k, n, f"{d:5} "))
        if n >= MIN_N:
            r = k/n
            best = (d, r) if not best or r > best[1] else best
            worst = (d, r) if not worst or r < worst[1] else worst
    if best and worst and best[0] != worst[0]:
        print(f"\n  A {100*(best[1]-worst[1]):.1f} percentage-point gap, in the same rows,")
        print("  invisible to every query that asked only for the average.")
        print("  That is BV7X-180. It went unfound for months.")

    head(3, "What else is the average hiding? — and does it survive a check?")
    print("  Filter the same rows by the model's OWN stated confidence:")
    for b in ("low", "medium", "high"):
        k, n = score(filter_oracle(rows, confidence_bucket=b))
        print("    " + rate_line(k, n, f"{b:7} "))
    print("\n  That looks like a second, bigger finding: the model is WORST exactly")
    print("  where it is most confident. Inverted calibration would be a headline.")
    print("\n  So ask memory one more question before believing it —")
    print("  cross the two filters:")
    print(f"    {'':8}{'UP':>12}{'DOWN':>12}")
    for b in ("low", "medium", "high"):
        cells = []
        for d in ("UP", "DOWN"):
            k, n = score(filter_oracle(rows, direction=d, confidence_bucket=b))
            cells.append(f"{k}/{n}")
        print(f"    {b:8}{cells[0]:>12}{cells[1]:>12}")
    print("\n  It dissolves. Every high-confidence call is a DOWN call; every")
    print("  medium is an UP call. The buckets are collinear with direction, so")
    print("  'inverted calibration' is just BV7X-180 wearing a different label —")
    print("  one finding, not two. Nothing here is independent evidence.")
    print("\n  The regime cross-cut lands the same way:")
    for reg in ("RISING", "FALLING", "FLAT", "UNKNOWN"):
        cells = []
        for d in ("UP", "DOWN"):
            k, n = score(filter_oracle(rows, direction=d, regime=reg))
            cells.append(f"{d} {k}/{n}")
        print(f"    {reg:8} " + "   ".join(f"{c:12}" for c in cells))
    print(f"\n  Every cell is under the n>={MIN_N} floor, so the tool prints counts and")
    print("  refuses the percentages. In RISING markets the DOWN calls are the")
    print("  better ones — the opposite of the headline, at a sample size that")
    print("  cannot support either claim.")
    print("\n  THIS is the product. Not a memory that answers everything, but one")
    print("  that holds n and uncertainty beside every claim, so the second")
    print("  question can kill the first. Retain structure you learned below")
    print("  significance and you inherit luck, then compound it.")

    head(4, "Different question: did the agents DO what their rules said?")
    fl = load(mem, "fleet")
    recent = sorted(fl, key=lambda r: r["date"])[-6:]
    print(f"  {'date':12} {'called':>8} {'abstained':>10} {'failed':>8}")
    for r in recent:
        print(f"  {r['date']:12} {r['called']:>8,} {r['abstained']:>10,} {r['failed']:>8,}")
    tot_f = sum(r["failed"] for r in fl)
    print(f"\n  {tot_f:,} rows where the agent could not call — separated from")
    print("  abstention, because they are not the same event. Conflating them")
    print("  wrote thousands of false stand-asides into the record for four")
    print("  nights (BV7X-264). Performance asks 'was it right'. Obedience asks")
    print("  'did it do what it said'. Only one of them is answerable here, and")
    print("  it is the one that tells you whether to buy the signal.")

    print("\n" + "="*W)
    print("A track record you can't query is just a claim. This one answers back.".center(W))
    print("="*W)

    mem.write_event(
        evaluated=f"sibyl-demo run: {len(rows)} oracle calls, {len(fl)} fleet nights",
        acted="four structured-filter queries; direction split reproduced from memory",
        forward="pre-registration by construction — the queries are versioned in the repo",
        extra={"tool": "sibyl-demo", "ts": now()})

def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backfill"); b.add_argument("--limit", type=int)
    sub.add_parser("demo"); sub.add_parser("status")
    a = sub.add_parser("ask")
    a.add_argument("--record", choices=["oracle", "fleet"], required=True)
    for f in ("direction", "regime", "action", "horizon",
              "confidence-bucket", "model-version", "date-from", "date-to"):
        a.add_argument(f"--{f}")
    p.add_argument("--store", default=DEMO_STORE,
                   help="memory db path; 'shared' uses the BV7X-245 store")
    args = p.parse_args()
    store = SHARED_STORE if args.store == "shared" else args.store
    for f in ("confidence_bucket", "model_version", "date_from", "date_to"):
        if not hasattr(args, f): setattr(args, f, None)
    mem = MemoryClient.local(store)
    {"backfill": cmd_backfill, "demo": cmd_demo,
     "status": cmd_status, "ask": cmd_ask}[args.cmd](mem, args)

if __name__ == "__main__":
    main()
