#!/usr/bin/env python3
"""Freeze the live field into tests/fixtures/rows.json — DEV ONLY.

Judges never run this: the fixture it writes is committed, so the parity test
runs off bundled data with no agents.db and no Sibyl account (the plan's
judge-simulation rule). Re-run it to refresh the fixture from production.

Reads the database READ-ONLY through sqlite3's URI mode. It never imports
polypool's services/db.js, whose require() runs migrations against production
(INTERNALS KI #53) — the .js research probes read a JSON dump for the same reason.

Shape is deduplicated by reference: every distinct predicate and snapshot once,
and each live row as a pointer pair plus its metadata. 23,106 rows as flat JSON
would be ~16 MB; this is under 2.
"""
import json, sqlite3, sys, datetime, os

DB = os.environ.get('AGENTS_DB', '/home/mischa/polypool/agents/data/agents.db')
OUT = os.path.join(os.path.dirname(__file__), 'fixtures', 'rows.json')

con = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
con.row_factory = sqlite3.Row
rows = con.execute('''
  SELECT p.id, date(p.predicted_at) AS night, p.direction AS stored,
         p.decision_snapshot AS snap, s.predicate_json AS pred
  FROM predictions p
  JOIN agents a ON a.id = p.agent_id
  JOIN spec_backtests s ON s.spec_hash = a.spec_hash
  WHERE p.decision_snapshot IS NOT NULL AND s.predicate_json IS NOT NULL
  ORDER BY p.predicted_at, p.id''').fetchall()

preds, pidx, snaps, sidx, out = [], {}, [], {}, []
for r in rows:
    if r['pred'] not in pidx:
        pidx[r['pred']] = len(preds); preds.append(json.loads(r['pred']))
    if r['snap'] not in sidx:
        sidx[r['snap']] = len(snaps); snaps.append(json.loads(r['snap']))
    out.append([pidx[r['pred']], sidx[r['snap']], r['night'], r['stored'], r['id']])

doc = {
    'generated': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    'source': 'polypool/agents/data/agents.db (read-only); predictions ⋈ agents ⋈ spec_backtests',
    'row_fields': ['predicate_index', 'snapshot_index', 'night', 'stored_direction', 'prediction_id'],
    'note': ('stored_direction is the HOSTED (LLM) lane\'s verdict as recorded on the row, '
             'NOT the predicate\'s. Parity is Python-vs-JS on the predicate; the LLM comparison '
             'is a different measurement (91.6% agreement, research/quorum/parity.js).'),
    'predicates': preds, 'snapshots': snaps, 'rows': out,
}
with open(OUT, 'w') as f:
    json.dump(doc, f, separators=(',', ':'))
print(f'rows={len(out)} predicates={len(preds)} snapshots={len(snaps)} nights={len(set(r[2] for r in out))} -> {OUT} ({os.path.getsize(OUT)/1e6:.2f} MB)')
