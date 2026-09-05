"""The cohort test, and the property that makes it worth having.

`cohort_stats` is pure, so most of this runs on synthetic records with no store
and no client. The one integration property — that the answer is UNAVAILABLE
without memory — is asserted against the server's two code paths, because that
is the claim the entry actually makes.
"""
import unittest
from quorum.cohorts import cohort_stats, expected_agreement, MIN_N
from quorum.server import field_off


def recs(spec):
    """spec: {rule_id: [directions]} -> decision records."""
    return [{'rule_id': rid, 'direction': d} for rid, ds in spec.items() for d in ds]


class ExpectedAgreement(unittest.TestCase):
    def test_single_agent_always_agrees_with_itself(self):
        self.assertEqual(expected_agreement(1, 0.5), 1.0)

    def test_baseline_is_well_above_half(self):
        """The trap this baseline exists to avoid: a majority of a small sample
        is lopsided by chance, so 56% agreement is NOT evidence of consensus."""
        self.assertGreater(expected_agreement(50, 0.5), 0.55)
        self.assertLess(expected_agreement(50, 0.5), 0.60)

    def test_converges_toward_half_as_n_grows(self):
        self.assertLess(expected_agreement(1000, 0.5), expected_agreement(50, 0.5))

    def test_extreme_p_forces_agreement(self):
        self.assertAlmostEqual(expected_agreement(40, 1.0), 1.0, places=9)


class Clustering(unittest.TestCase):
    def test_identical_cohorts_are_detected_as_clustered(self):
        """A cohort that really is one opinion must register as clustered —
        otherwise the test could never fire and would be decoration."""
        spec = {f'r{i}': ['UP'] * 40 if i % 2 else ['DOWN'] * 40 for i in range(6)}
        c = cohort_stats(recs(spec), {f'r{i}': ['vix'] if i % 2 else ['roc7d'] for i in range(6)})
        self.assertTrue(c['clustered'])
        self.assertEqual(c['verdict'], 'cohorts cluster')
        self.assertGreater(c['excess_pp'], 40)

    def test_alternating_cohorts_are_not_clustered(self):
        """Agents in a cohort that split down the middle are not one opinion."""
        spec = {f'r{i}': ['UP', 'DOWN'] * 20 for i in range(6)}
        c = cohort_stats(recs(spec), {f'r{i}': [f's{i}'] for i in range(6)})
        self.assertFalse(c['clustered'])
        self.assertEqual(c['verdict'], 'indistinguishable from independent')

    def test_configurations_group_by_signal_set_not_rule(self):
        """Two rules reading the same signals are ONE configuration — the whole
        premise — and signal ORDER must not split them."""
        c = cohort_stats(recs({'a': ['UP'] * 5, 'b': ['DOWN'] * 5}),
                         {'a': ['vix', 'roc7d'], 'b': ['roc7d', 'vix']})
        self.assertEqual(c['configurations'], 1)
        self.assertEqual(c['calls'], 10)

    def test_rule_missing_from_memory_is_unplaced_not_dropped(self):
        """A silently smaller denominator is how a field gets overstated."""
        c = cohort_stats(recs({'a': ['UP'] * 4, 'ghost': ['DOWN'] * 3}), {'a': ['vix']})
        self.assertEqual(c['unplaced'], 3)
        self.assertEqual(c['calls'], 4)

    def test_agreement_withheld_below_the_floor(self):
        c = cohort_stats(recs({'a': ['UP'] * (MIN_N - 1)}), {'a': ['vix']})
        g = c['largest'][0]
        self.assertTrue(g['withheld'])
        self.assertIsNone(g['agreement'])
        self.assertIsNone(g['excess_pp'])
        self.assertIsNone(c['excess_pp'])          # nothing tested, so no verdict
        self.assertIsNone(c['verdict'])

    def test_no_calls_returns_none_so_caller_says_cannot_say(self):
        self.assertIsNone(cohort_stats([{'rule_id': 'a', 'direction': None}], {'a': ['vix']}))


class MemoryOnly(unittest.TestCase):
    """THE point of the panel: without the store this is not merely absent, it
    is unanswerable — a configuration is a property of the rule."""

    def test_memory_off_cannot_produce_cohorts(self):
        c = field_off('2026-08-27')['cohorts']
        self.assertEqual(c['status'], 'CANNOT SAY')
        self.assertIn('rule', c['reason'])
        for k in ('configurations', 'n_eff_if_clustered', 'excess_pp', 'largest'):
            self.assertNotIn(k, c)

    def test_memory_off_still_answers_the_vote(self):
        """The contrast has to be sharp: the vote survives, the structure does not."""
        d = field_off('2026-08-27')
        self.assertEqual(d['status'], 'ok')
        self.assertEqual(d['counts']['calls'], 715)


if __name__ == '__main__':
    unittest.main()
