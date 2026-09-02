"""Atom parity — the Python evaluator must agree with production on EVERY live row.

Foundation test. If this disagrees, everything downstream — every "why", every
evidenced/default split, every deletion delta — is wrong. Stdlib only; runs off
the bundled fixtures with no database and no node (CI regenerates the JS side
separately and diffs it, so the two halves are checked independently).

Run:  python3 -m unittest tests.test_parity -v
"""
import json, os, unittest
from quorum import why as W

FX = os.path.join(os.path.dirname(__file__), 'fixtures')
with open(os.path.join(FX, 'rows.json')) as f:
    DOC = json.load(f)
with open(os.path.join(FX, 'expected.json')) as f:
    EXP = json.load(f)


def encode(v):
    """Match regen_expected.js: None -> 'NULL', everything else as-is."""
    return 'NULL' if v is None else v


def run_all():
    return [encode(W.evaluate(DOC['predicates'][pi], DOC['snapshots'][si]))
            for pi, si, *_ in DOC['rows']]


class Parity(unittest.TestCase):

    def test_fixture_is_the_full_field(self):
        # A parity test over a handful of rows is a demo, not a proof.
        self.assertEqual(len(DOC['rows']), EXP['rows'])
        self.assertGreater(len(DOC['rows']), 20000, 'fixture shrank — re-run tests/dump_rows.py')
        self.assertGreater(len(set(r[2] for r in DOC['rows'])), 10, 'fewer than 10 nights')

    def test_every_row_agrees_with_production(self):
        got = run_all()
        bad = [(i, DOC['rows'][i][4], e, g) for i, (e, g) in enumerate(zip(EXP['expected'], got)) if e != g]
        self.assertEqual(bad, [], f'{len(bad)} of {len(got)} rows disagree; first: {bad[:5]}')

    def test_tally_matches_oracle(self):
        # Belt and braces: the distribution, not just per-row equality.
        got = run_all()
        tally = {}
        for g in got:
            tally[g] = tally.get(g, 0) + 1
        self.assertEqual(tally, EXP['tally'])

    def test_POSITIVE_CONTROL_a_wrong_operator_is_caught(self):
        # This test exists so that "0 disagreements" is known to be a
        # measurement and not a broken comparator. Mutate ONE operator the
        # way a careless port would (> becomes >=) and assert the parity
        # check goes red. If this ever passes with zero disagreements, the
        # fixture no longer exercises that operator at its boundary and the
        # guard has gone hollow — treat that as a failure of the fixture.
        real = W.OPS['>']
        W.OPS['>'] = lambda a, b: a >= b
        try:
            got = run_all()
        finally:
            W.OPS['>'] = real
        disagreements = sum(1 for e, g in zip(EXP['expected'], got) if e != g)
        self.assertGreater(disagreements, 0, 'mutated evaluator still agreed on every row — the control proves nothing')

    def test_POSITIVE_CONTROL_short_circuit_order_is_observable(self):
        # Production stops at the first FALSE atom, so a null in a LATER atom
        # is irrelevant; a null in an EARLIER one is SKIP. A port that checks
        # "all atoms finite" first would say SKIP for both. Prove the order.
        pred = {'predicate_version': 1,
                'up': {'all': [{'signal': 'rsi', 'op': '>', 'value': 70},
                               {'signal': 'roc7d', 'op': '>', 'value': 0}]},
                'down': 'else'}
        # rsi fails first; roc7d is missing but never consulted -> down/else fires
        self.assertEqual(W.evaluate(pred, {'rsi': 50, 'roc7d': None}), 'DOWN')
        # rsi is missing -> SKIP, regardless of roc7d
        self.assertEqual(W.evaluate(pred, {'rsi': None, 'roc7d': 5}), 'SKIP')
        # up evaluated before down: up SKIP returns before down is looked at
        pred2 = {'predicate_version': 1,
                 'up': {'all': [{'signal': 'rsi', 'op': '>', 'value': 70}]},
                 'down': {'all': [{'signal': 'roc7d', 'op': '<', 'value': 0}]}}
        self.assertEqual(W.evaluate(pred2, {'rsi': None, 'roc7d': -5}), 'SKIP')

    def test_js_number_isFinite_semantics(self):
        pred = {'predicate_version': 1, 'up': {'all': [{'signal': 'x', 'op': '>', 'value': 0}]}, 'down': None}
        for bad in (True, False, '5', float('nan'), float('inf'), None):
            self.assertEqual(W.evaluate(pred, {'x': bad}), 'SKIP', f'{bad!r} should be missing')
        self.assertEqual(W.evaluate(pred, {'x': 1}), 'UP')
        self.assertIsNone(W.evaluate(pred, {'x': -1}))


class Why(unittest.TestCase):
    """The decomposition must be consistent with the verdict on every row."""

    def test_why_agrees_with_evaluate_and_its_atoms_are_honest(self):
        evidenced = default = none = 0
        for pi, si, *_ in DOC['rows']:
            p, r = DOC['predicates'][pi], DOC['snapshots'][si]
            w = W.why(p, r)
            self.assertEqual(w['direction'], W.evaluate(p, r))
            if w['direction'] in ('UP', 'DOWN'):
                self.assertIn(w['basis'], ('evidenced', 'default'))
                self.assertTrue(w['atoms'], 'a call with no deciding facts')
                if w['basis'] == 'evidenced':
                    evidenced += 1
                    self.assertTrue(all(a['held'] is True for a in w['atoms']),
                                    'an evidenced call carries an atom that did not hold')
                else:
                    default += 1
                    # the LAST reported atom is the one that failed (short-circuit),
                    # and nothing before it failed
                    self.assertIs(w['atoms'][-1]['held'], False)
                    self.assertTrue(all(a['held'] is True for a in w['atoms'][:-1]))
            else:
                none += 1
                self.assertIsNone(w['basis']); self.assertEqual(w['atoms'], [])
        # Sanity on the split itself — the research measured ~27% evidenced / ~64% default.
        calls = evidenced + default
        self.assertGreater(calls, 0)
        share = evidenced / calls
        self.assertTrue(0.10 < share < 0.60, f'evidenced share {share:.3f} is outside any plausible band')

    def test_shape_and_signals_match_production_definitions(self):
        p = {'predicate_version': 1,
             'up': {'all': [{'signal': 'rsi', 'op': '>', 'value': 70}, {'signal': 'roc7d', 'op': '>', 'value': 0}]},
             'down': 'else'}
        self.assertEqual(W.signals_of(p), ['rsi', 'roc7d'])
        s = W.shape(p)
        self.assertEqual((s['up'], s['down']), ('conj', 'else'))
        self.assertTrue(s['total']); self.assertFalse(s['gapped']); self.assertFalse(s['one_legged'])
        self.assertTrue(W.shape({'up': {'all': []}, 'down': None})['one_legged'])


if __name__ == '__main__':
    unittest.main()
