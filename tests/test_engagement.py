"""Engagement: the temporal finding, and the properties that make it memory.

Most of this runs on synthetic histories with no store. Three things have to hold
or the panel is decoration: classification uses PRIOR nights only; shallow memory
returns CANNOT SAY rather than a number; and the memory-off path cannot produce
any of it.
"""
import unittest

from quorum.engagement import MIN_N, MIN_PRIOR_NIGHTS, classify, decompose
from quorum.server import field_off


def hist(*bases, start=1):
    """A per-night basis dict from a sequence, nights numbered as ISO-sortable strings."""
    return {f'n{start + i:02d}': b for i, b in enumerate(bases)}


class Classify(unittest.TestCase):
    def test_too_shallow_is_none(self):
        self.assertIsNone(classify(['evidenced'] * (MIN_PRIOR_NIGHTS - 1)))

    def test_always_never_switching(self):
        self.assertEqual(classify(['evidenced'] * MIN_PRIOR_NIGHTS), 'always')
        self.assertEqual(classify(['default'] * MIN_PRIOR_NIGHTS), 'never')
        self.assertEqual(classify(['evidenced', 'default'] * MIN_PRIOR_NIGHTS), 'switching')

    def test_no_calls_do_not_count_toward_depth(self):
        """An abstention or a failed night is not a call; it must not make a
        rule look better-known than it is."""
        self.assertIsNone(classify(['evidenced'] * (MIN_PRIOR_NIGHTS - 1) + [None, None, None]))


class PriorOnly(unittest.TestCase):
    def test_tonight_never_classifies_itself(self):
        """The whole point: what memory knew BEFORE tonight. A rule with exactly
        MIN_PRIOR_NIGHTS calls INCLUDING tonight has one too few."""
        b = {f'n{i:02d}': 'evidenced' for i in range(1, MIN_PRIOR_NIGHTS + 1)}   # nights n01..n06
        tonight = f'n{MIN_PRIOR_NIGHTS:02d}'                                       # n06 is tonight
        out = decompose({'r': 'UP'}, {'r': b}, tonight)
        self.assertEqual(out['status'], 'CANNOT SAY')
        self.assertEqual(out['prior_nights'], MIN_PRIOR_NIGHTS - 1)

    def test_future_nights_are_ignored(self):
        """Nights AFTER tonight must not leak into the classification."""
        rules = {f'r{i}': hist(*(['evidenced', 'default'] * 3), *(['evidenced'] * 10)) for i in range(40)}
        tonight = 'n07'   # n01..n06 are prior (switching); n08+ are future (all evidenced)
        calls = {f'r{i}': 'UP' if i % 2 else 'DOWN' for i in range(40)}
        out = decompose(calls, rules, tonight)
        self.assertEqual(out['status'], 'ok')
        self.assertEqual(out['classes']['switching']['n'], 40)
        self.assertNotIn('always', out['classes'])


class Decompose(unittest.TestCase):
    def _fleet(self, n_const_up=200, n_const_down=200, n_switch=100):
        rules, calls = {}, {}
        for i in range(n_const_up):
            rules[f'u{i}'] = hist(*(['evidenced'] * 8)); calls[f'u{i}'] = 'UP'
        for i in range(n_const_down):
            rules[f'd{i}'] = hist(*(['default'] * 8)); calls[f'd{i}'] = 'DOWN'
        for i in range(n_switch):
            rules[f's{i}'] = hist(*(['evidenced', 'default'] * 4)); calls[f's{i}'] = 'UP' if i % 2 else 'DOWN'
        return rules, calls

    def test_constant_agents_inflate_precision(self):
        """The finding in miniature: 400 constant-output agents make the naive
        interval far narrower than the 100 responsive ones justify."""
        rules, calls = self._fleet()
        out = decompose(calls, rules, 'n09')
        self.assertEqual(out['status'], 'ok')
        self.assertGreater(out['precision_ratio'], 1.5)
        self.assertLess(out['naive']['width_pp'], out['responsive']['width_pp'])
        self.assertAlmostEqual(out['constant_share'], 0.8, places=6)

    def test_shallow_memory_is_cannot_say_not_zero(self):
        rules, calls = self._fleet()
        rules = {k: {n: b for n, b in v.items() if n <= 'n03'} for k, v in rules.items()}
        out = decompose(calls, rules, 'n04')
        self.assertEqual(out['status'], 'CANNOT SAY')
        self.assertIn('prior night', out['reason'])
        self.assertNotIn('naive', out)

    def test_too_few_switchers_is_cannot_say(self):
        rules, calls = self._fleet(n_switch=MIN_N - 1)
        out = decompose(calls, rules, 'n09')
        self.assertEqual(out['status'], 'CANNOT SAY')
        self.assertIn('floor', out['reason'])

    def test_unclassified_are_counted_in_naive_only(self):
        rules, calls = self._fleet()
        for i in range(50):                       # 50 brand-new agents, one night of history
            rules[f'new{i}'] = {'n08': 'evidenced'}; calls[f'new{i}'] = 'UP'
        out = decompose(calls, rules, 'n09')
        self.assertEqual(out['unclassified'], 50)
        self.assertEqual(out['naive']['n'], 550)
        self.assertEqual(sum(g['n'] for g in out['classes'].values()), 500)


class MemoryOnly(unittest.TestCase):
    def test_memory_off_cannot_produce_history(self):
        h = field_off('2026-09-01')['history']
        self.assertEqual(h['status'], 'CANNOT SAY')
        self.assertIn('history', h['reason'])
        for k in ('naive', 'responsive', 'classes', 'precision_ratio'):
            self.assertNotIn(k, h)


if __name__ == '__main__':
    unittest.main()
