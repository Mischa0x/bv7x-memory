"""The decision record — written to, and read back from, Sibyl memory.

WHAT A RECORD IS, AND WHY IT IS NOT A BLOB. A call's "why" is fully determined
by two things: the agent's rule and the market snapshot it was decided against.
``why.py`` reproduces every atom, its observed value and whether it held from
exactly those two inputs — so a decision record is a JOIN of (rule, snapshot),
not a stored copy of its output. Memory holds the rules once and each night's
snapshots once; every record is reconstructed on read.

WHERE THINGS LIVE, AND WHY IT MATTERS (measured day 3). The client's free tier
BLOCKS writes at 5 MB with ``CapExceededError`` — for a judge on a fresh
account, so the store must fit. Two facts forced the layout:

* A per-agent JSON *event* costs ~1.7 KB (envelope + FTS shadow index); the
  field's 23,106 events would be ~40 MB. Normalised to rules-once +
  snapshots-per-night + a compact ``rid:sid`` row string, the whole field is
  ~2.3 MB.
* The bulk (rules bundle, per-night rows+snapshots) is reconstruction data —
  looked up by id in code, never full-text-searched — so it lives in **state**,
  which is not FTS-indexed. Putting it in entities instead FTS-indexes every
  rule string and every ``rid:sid`` token and pushes the same content past the
  cap. A tiny per-night **entity** stub carries only the call count, so the
  night is discoverable by the client's search/recall path.

Store shape (all under one tenant, resolved by the credentials ladder
tenant_id → account_id → default):

* state ``quorum/rules``        — ``{rule_id: "up_leg|down_leg"}`` for every rule.
* state ``quorum/night/<date>`` — ``{"snapshots": {sid: row}, "rows": "rid:sid;…"}``.
* state ``quorum/watermark``    — ``{"nights": [...]}``, so ingest is idempotent.
* entity ``night/<date>``       — ``{"calls": n}``, the searchable stub.

Honesty, enforced here rather than in copy:

* A night not in memory is **CANNOT SAY** — never a default, never zeros.
* No rate below ``MIN_N`` resolved; intervals are Wilson and travel with n.
* An open call's direction is never returned by ``field()``; the composite is
  the SPLIT (evidenced/default) and the UP share with its interval — what the
  deletion gate measures. Per-record directions come only from ``record()``,
  which the page uses for settled nights.
* ``field(memory=False)`` is the naive vote count and needs no memory at all.
  The naive answer survives deletion; the warranted one does not. That is the
  gate.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from typing import Any

from . import why as W

MIN_N = 30
DEFAULT_STORE = os.path.expanduser(os.environ.get('QUORUM_STORE', '~/.sibyl-memory/quorum.db'))
CANNOT_SAY = 'CANNOT SAY'


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval (sibyl_demo.wilson, restated only because that
    module is prior-work substrate and must stay untouched)."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


# ── rule encoding: compact, lossless, content-addressed ─────────────────────

_ATOM = re.compile(r'^([A-Za-z0-9_]+)(<=|>=|<|>)(-?[0-9.]+(?:e-?[0-9]+)?)$')


def encode_leg(leg: Any) -> str:
    if leg == 'else':
        return 'else'
    if not leg:
        return ''
    return ';'.join(f"{a['signal']}{a['op']}{a['value']!r}" for a in leg['all'])


def decode_leg(s: str) -> Any:
    if s == 'else':
        return 'else'
    if not s:
        return None
    atoms = []
    for part in s.split(';'):
        m = _ATOM.match(part)
        if not m:
            raise ValueError(f'unparseable atom {part!r}')
        atoms.append({'signal': m[1], 'op': m[2], 'value': float(m[3])})
    return {'all': atoms}


def encode_rule(pred: dict) -> str:
    return f"{encode_leg(pred.get('up'))}|{encode_leg(pred.get('down'))}"


def decode_rule(s: str) -> dict:
    up, down = s.split('|', 1)
    return {'predicate_version': 1, 'up': decode_leg(up), 'down': decode_leg(down)}


def rule_id(pred: dict) -> str:
    """Content hash of the encoded rule — stable across ingests, independent of
    any fixture's ordering. Ten hex chars: six collided in practice over the
    5,596 live rules (birthday-bound at 24 bits), so ten; and ingest still
    asserts no collision rather than trusting the width."""
    return hashlib.sha1(encode_rule(pred).encode()).hexdigest()[:10]


def snap_id(snap: dict) -> str:
    return hashlib.sha1(json.dumps(snap, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:8]


# ── the memory ──────────────────────────────────────────────────────────────

class QuorumMemory:
    """Sibyl-backed memory of why. ``client`` is a sibyl_memory_client
    MemoryClient; injecting one keeps this module importable and testable
    without the package and lets the caller pick the tenant."""

    def __init__(self, client: Any):
        self.m = client

    @classmethod
    def open(cls, store: str = DEFAULT_STORE, tenant_id: str | None = None) -> 'QuorumMemory':
        from sibyl_memory_client import MemoryClient, DEFAULT_TENANT  # noqa: WPS433
        if tenant_id is None:
            tenant_id = DEFAULT_TENANT
            try:
                c = json.load(open(os.path.expanduser('~/.sibyl-memory/credentials.json')))
                tenant_id = c.get('tenant_id') or c.get('account_id') or DEFAULT_TENANT
            except Exception:
                pass
        return cls(MemoryClient.local(os.path.expanduser(store), tenant_id=tenant_id))

    # -- reads that must fail closed --------------------------------------
    def _state(self, key: str) -> Any:
        """get_state returns ``{'body': ..., 'updated_at': ...}`` or None.
        Absence → None; the body is unwrapped."""
        try:
            g = self.m.get_state(key)
        except Exception as ex:  # noqa: BLE001
            if type(ex).__name__ == 'NotFoundError':
                return None
            raise
        return g.get('body') if g else None

    def _rules(self) -> dict[str, str]:
        b = self._state('quorum/rules')
        return dict(b) if b else {}

    def _night(self, night: str) -> dict | None:
        return self._state(f'quorum/night/{night}')

    def watermark(self) -> list[str]:
        b = self._state('quorum/watermark')
        return sorted(b.get('nights', [])) if b else []

    def nights(self) -> list[str]:
        return self.watermark()

    # -- ingest: idempotent, watermarked -----------------------------------
    def ingest(self, predicates: list[dict], snapshots: list[dict], rows: list[list]) -> dict:
        """Write decision records for every (rule, snapshot, night) row.

        ``rows`` are ``[pred_idx, snap_idx, night, ...]`` — the fixture shape and
        what a live dump produces. Nights already in the watermark are skipped
        whole, so a re-run is a no-op and a partial run resumes. Rules merge into
        the single bundle. The watermark advances ONCE, after every night's state
        is written — measured day 3: a per-night watermark write plus the
        connection churn it invited pushed a 2.3 MB layout past the 5 MB cap.
        """
        done = set(self.watermark())
        by_night: dict[str, list[tuple[int, int]]] = {}
        for r in rows:
            pi, si, night = r[0], r[1], r[2]
            if night in done:
                continue
            by_night.setdefault(night, []).append((pi, si))
        if not by_night:
            return {'ingested_nights': 0, 'rows': 0, 'skipped_nights': len(done)}

        rules = self._rules()
        rid_of: dict[int, str] = {}
        for pi in {pi for lst in by_night.values() for pi, _ in lst}:
            rid = rule_id(predicates[pi])
            enc = encode_rule(predicates[pi])
            if rules.get(rid, enc) != enc:  # 6-hex collision — refuse, do not corrupt
                raise RuntimeError(f'rule_id collision on {rid}: {rules[rid]!r} vs {enc!r}')
            rid_of[pi] = rid
            rules[rid] = enc
        self.m.set_state('quorum/rules', rules)

        n_rows = 0
        for night in sorted(by_night):
            lst = by_night[night]
            sids = {si: snap_id(snapshots[si]) for si in {si for _, si in lst}}
            self.m.set_state(f'quorum/night/{night}', {
                'snapshots': {sids[si]: snapshots[si] for si in sids},
                'rows': ';'.join(f'{rid_of[pi]}:{sids[si]}' for pi, si in lst),
            })
            self.m.set_entity('night', night, {'calls': len(lst)})  # searchable stub
            n_rows += len(lst)
            done.add(night)
        self.m.set_state('quorum/watermark', {'nights': sorted(done)})
        return {'ingested_nights': len(by_night), 'rows': n_rows, 'skipped_nights': len(done) - len(by_night)}

    # -- the record, reconstructed ------------------------------------------
    def records(self, night: str) -> list[dict] | None:
        """Every decision record for a night, from memory alone. ``None`` when
        the night is not in memory — the caller renders CANNOT SAY."""
        N = self._night(night)
        if N is None:
            return None
        rules = self._rules()
        out = []
        for pair in N['rows'].split(';'):
            rid, sid = pair.split(':')
            w = W.why(decode_rule(rules[rid]), N['snapshots'][sid])
            out.append({'rule_id': rid, 'snap_id': sid, 'night': night, **w})
        return out

    def record(self, night: str, rule: str) -> dict | None:
        recs = self.records(night)
        if recs is None:
            return None
        for r in recs:
            if r['rule_id'] == rule:
                return r
        return None

    # -- the field: memory on vs memory off ---------------------------------
    def field(self, night: str, *, memory: bool = True, naive_directions: list[str] | None = None) -> dict:
        """The field's belief for a night.

        memory=True  — from records: the evidenced/default split, and the UP
                       share among calls that rested on a condition that held,
                       with Wilson intervals. CANNOT SAY if the night is absent.
        memory=False — the naive vote count over ``naive_directions`` (what the
                       arena publishes anyway). Needs no memory; never claims
                       warrant.
        """
        if not memory:
            d = [x for x in (naive_directions or []) if x in ('UP', 'DOWN')]
            n = len(d)
            k = sum(1 for x in d if x == 'UP')
            return {'night': night, 'memory': False, 'n': n, 'up': k,
                    'up_share': (k / n) if n else None, 'ci': wilson(k, n) if n >= MIN_N else None,
                    'warrant': CANNOT_SAY}
        recs = self.records(night)
        if recs is None:
            return {'night': night, 'memory': True, 'status': CANNOT_SAY, 'reason': 'night not in memory'}
        calls = [r for r in recs if r['direction'] in ('UP', 'DOWN')]
        ev = [r for r in calls if r['basis'] == 'evidenced']
        de = [r for r in calls if r['basis'] == 'default']

        def share(rs):
            n = len(rs)
            k = sum(1 for r in rs if r['direction'] == 'UP')
            return {'n': n, 'up': k, 'up_share': (k / n) if n else None,
                    'ci': wilson(k, n) if n >= MIN_N else None,
                    'rate': None if n < MIN_N else k / n}
        return {'night': night, 'memory': True, 'status': 'ok',
                'records': len(recs), 'calls': len(calls),
                'abstain_skip_conflict': len(recs) - len(calls),
                'evidenced': share(ev), 'default': share(de), 'all': share(calls),
                'evidenced_share': (len(ev) / len(calls)) if calls else None}
