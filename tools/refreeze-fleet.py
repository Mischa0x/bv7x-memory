#!/usr/bin/env python3
"""Re-cut data/fleet-nights.json from the live agent database.

Runs the SAME query sibyl_demo.backfill_fleet runs against a live DB, so the
frozen snapshot and the on-box path cannot drift into different shapes.

Two rules this tool exists to enforce, because the file it writes is public:

1. AGGREGATES ONLY. Night-level counts, never per-agent rows. Per-agent is
   below statistical power anyway (thirty resolutions a season), and the free
   tier caps the store.

2. AN OPEN CALL'S DIRECTION IS WITHHELD — IN AGGREGATE AS WELL AS PER AGENT.
   A night whose calls have not all settled still describes live positions,
   and the aggregate up/down for such a night IS the signal BV-7X sells. So
   up/down are written only for nights where settled == called; otherwise they
   are null and the night is marked. The obedience buckets (called / abstained
   / failed / total) carry no direction and are always written — they are what
   the demo's obedience panel renders.

The database is opened READ-ONLY (mode=ro). This tool never writes to it, and
never imports the service's db module (which would run migrations against prod).

    python3 tools/refreeze-fleet.py [--db PATH] [--out PATH]
"""
import argparse, json, os, sqlite3
from datetime import datetime, timezone

DEFAULT_DB  = "/home/mischa/polypool/agents/data/agents.db"
DEFAULT_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           os.pardir, "data", "fleet-nights.json")

QUERY = """
    SELECT date(predicted_at) d,
           SUM(direction IS NOT NULL)                        called,
           SUM(direction = 'UP')                             up,
           SUM(direction = 'DOWN')                           down,
           SUM(direction IS NULL AND eval_error IS NOT NULL) failed,
           SUM(direction IS NULL AND eval_error IS NULL)     abstained,
           SUM(outcome IS NOT NULL)                          settled,
           COUNT(*)                                          total
    FROM predictions GROUP BY d ORDER BY d"""


def night(r):
    """One night's aggregate, with open-call directions withheld."""
    called, settled = r["called"] or 0, r["settled"] or 0
    total = r["total"] or 0
    fully_settled = settled >= called   # called == 0 -> 0/0, a fact, not a secret
    body = {
        "date": r["d"],
        "called": called,
        "up":   (r["up"]   or 0) if fully_settled else None,
        "down": (r["down"] or 0) if fully_settled else None,
        "failed": r["failed"] or 0,
        "abstained": r["abstained"] or 0,
        "settled": settled,
        "total": total,
        "obedience_rate": (round(called / total, 4) if total else None),
    }
    if not fully_settled and called:
        body["_directions_withheld"] = "open calls remain; aggregate lean is the signal"
    return body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--out", default=DEFAULT_OUT)
    a = ap.parse_args()

    db = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    nights = [night(r) for r in db.execute(QUERY).fetchall()]
    db.close()

    withheld = sum(1 for n in nights if n.get("_directions_withheld"))
    doc = {
        "_what": "BV-7X strategy-fleet nightly aggregates, Base Sepolia 84532.",
        "_granularity": ("night-level counts only. No per-agent rows. An open call's "
                         "direction is withheld in aggregate as well as per agent, so "
                         "up/down are null on any night whose calls have not all settled."),
        "_frozen": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "nights": nights,
    }
    with open(a.out, "w") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    print(f"wrote {a.out}: {len(nights)} nights "
          f"({nights[0]['date']} → {nights[-1]['date']}), "
          f"{withheld} with directions withheld")


if __name__ == "__main__":
    main()
