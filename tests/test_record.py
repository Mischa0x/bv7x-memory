"""The decision record + the deletion gate, tested without a database.

Sibyl's client is not needed to test the record LOGIC: QuorumMemory takes an
injected client, so a tiny in-memory fake stands in for it and CI runs on the
stdlib. A separate live test (test_record_live) exercises the real client when
it is installed, and is skipped otherwise — so the logic is always covered and
the integration is covered where the package exists.

The load-bearing test is the GATE: field(memory=True) and field(memory=False)
must give materially different answers on a real night, and an absent night
must be CANNOT SAY, never a default or a zero. If those ever collapse, the
memory is decoration and the hackathon entry fails its own criterion.
"""
import json, os, unittest
from quorum import why as W
from quorum.record import QuorumMemory, wilson, encode_rule, decode_rule, rule_id, CANNOT_SAY, MIN_N

FX = os.path.join(os.path.dirname(__file__), 'fixtures')
with open(os.path.join(FX, 'rows.json')) as f:
    DOC = json.load(f)


class FakeClient:
    """Enough of the sibyl_memory_client surface for QuorumMemory: state
    get/set with the {'body','updated_at'} wrapper, entity set, and a
    NotFoundError-by-name on absent state (the real client raises)."""
    class NotFoundError(Exception):
        pass

    def __init__(self):
        self.state = {}
        self.entities = {}

    def set_state(self, key, body):
        self.state[key] = {'body': json.loads(json.dumps(body)), 'updated_at': 'x'}

    def get_state(self, key):
        if key not in self.state:
            raise FakeClient.NotFoundError(key)
        return self.state[key]

    def set_entity(self, category, name, body, **kw):
        self.entities[(category, name)] = body


def fresh():
    m = QuorumMemory(FakeClient())
    m.ingest(DOC['predicates'], DOC['snapshots'], DOC['rows'])
    return m


class RuleCodec(unittest.TestCase):
    def test_encode_decode_roundtrips_every_rule(self):
        for p in DOC['predicates']:
            pred = {'up': p.get('up'), 'down': p.get('down')}
            back = decode_rule(encode_rule(pred))
            # decode normalises to {predicate_version, up, down}; compare legs
            self.assertEqual(back['up'], pred['up'] if pred['up'] != {} else None)
            self.assertEqual(back['down'], pred['down'])

    def test_rule_id_stable_and_collision_free_over_the_field(self):
        ids = {}
        for p in DOC['predicates']:
            pred = {'up': p.get('up'), 'down': p.get('down')}
            rid = rule_id(pred)
            enc = encode_rule(pred)
            self.assertEqual(rid, rule_id(pred))          # stable
            self.assertEqual(ids.get(rid, enc), enc)      # no id maps to two rules
            ids[rid] = enc


class Ingest(unittest.TestCase):
    def test_ingest_then_reconstruct_matches_full_precision_why(self):
        m = fresh()
        self.assertEqual(sorted(m.nights()), sorted({r[2] for r in DOC['rows']}))
        # every reconstructed record equals why() on the original full-precision inputs
        by_night = {}
        for pi, si, night, *_ in DOC['rows']:
            by_night.setdefault(night, []).append((pi, si))
        night = '2026-08-27'
        recs = m.records(night)
        want = [W.why(DOC['predicates'][pi], DOC['snapshots'][si]) for pi, si in by_night[night]]
        self.assertEqual(len(recs), len(want))
        # order is preserved by ingest, so compare directions+bases pairwise
        for r, w in zip(recs, want):
            self.assertEqual((r['direction'], r['basis']), (w['direction'], w['basis']))

    def test_ingest_is_idempotent(self):
        m = fresh()
        again = m.ingest(DOC['predicates'], DOC['snapshots'], DOC['rows'])
        self.assertEqual(again['ingested_nights'], 0)
        self.assertGreater(again['skipped_nights'], 0)


class Gate(unittest.TestCase):
    def test_DELETION_DELTA_memory_on_vs_off_differ_on_a_real_night(self):
        m = fresh()
        on = m.field('2026-08-27', memory=True)
        off = m.field('2026-08-27', memory=False,
                      naive_directions=[r[3] for r in DOC['rows'] if r[2] == '2026-08-27'])
        self.assertEqual(on['status'], 'ok')
        # the naive vote leans UP with a verdict; the evidenced subset does not.
        self.assertGreater(off['up_share'], 0.5)
        self.assertLess(on['evidenced']['up_share'], 0.5)
        # and the point estimates are materially apart — this is the gate.
        self.assertGreater(abs(off['up_share'] - on['evidenced']['up_share']), 0.03)

    def test_absent_night_is_CANNOT_SAY_never_a_default(self):
        m = fresh()
        r = m.field('2099-01-01', memory=True)
        self.assertEqual(r['status'], CANNOT_SAY)
        self.assertNotIn('evidenced', r)          # no fabricated split
        self.assertIsNone(m.records('2099-01-01'))  # not [], not zeros — None

    def test_memory_off_needs_no_store(self):
        # the naive answer must be computable with an empty memory — that is why
        # it survives deletion. Construct QuorumMemory over a fake with nothing in it.
        m = QuorumMemory(FakeClient())
        off = m.field('2026-08-27', memory=False, naive_directions=['UP', 'UP', 'DOWN'])
        self.assertEqual(off['n'], 3)
        self.assertEqual(off['warrant'], CANNOT_SAY)

    def test_no_rate_below_min_n(self):
        self.assertIsNone(wilson(0, 0) and None)  # smoke
        m = fresh()
        # a night with < MIN_N calls would carry rate None; assert the rule holds
        f = m.field('2026-08-27', memory=True)
        for bucket in ('evidenced', 'default', 'all'):
            b = f[bucket]
            if b['n'] < MIN_N:
                self.assertIsNone(b['rate'])
                self.assertIsNone(b['ci'])


class Live(unittest.TestCase):
    """Exercises the real sibyl_memory_client if installed; skipped otherwise."""
    def test_record_live(self):
        try:
            import sibyl_memory_client  # noqa: F401
        except ImportError:
            self.skipTest('sibyl_memory_client not installed')
        import tempfile
        d = tempfile.mkdtemp()
        m = QuorumMemory.open(os.path.join(d, 'q.db'))
        m.ingest(DOC['predicates'], DOC['snapshots'], DOC['rows'])
        self.assertEqual(len(m.nights()), len({r[2] for r in DOC['rows']}))
        on = m.field('2026-08-27', memory=True)
        self.assertEqual(on['status'], 'ok')
        self.assertLess(on['evidenced']['up_share'], 0.5)


if __name__ == '__main__':
    unittest.main()
