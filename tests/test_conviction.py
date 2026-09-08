"""Conviction: the numbers the README prints, pinned.

Accuracy is flat across the basis split and conviction is not — that asymmetry is
the entire claim, so it is asserted rather than described.
"""
import unittest

from quorum import conviction as C


class Fixture(unittest.TestCase):
    def setUp(self):
        self.calls = C.load()

    def test_shape(self):
        self.assertEqual(len(self.calls), 9393)
        for basis, correct, conf, night in self.calls:
            self.assertIn(basis, ('e', 'd'))
            self.assertIn(correct, (0, 1))
            self.assertTrue(conf is None or 0.0 <= conf <= 1.0)
            self.assertRegex(night, r'^\d{4}-\d{2}-\d{2}$')


class AccuracyIsFlat(unittest.TestCase):
    """The split does NOT sort right calls from wrong ones, and must not claim to."""

    def test_both_classes_sit_on_a_coin_flip(self):
        b = C.by_basis(C.load())
        for name in ('evidenced', 'default'):
            lo, hi = b[name]['ci']
            self.assertLess(lo, 50.0, f'{name} lower bound excludes 50')
            self.assertGreater(hi, 50.0, f'{name} upper bound excludes 50')

    def test_the_gap_is_under_a_point(self):
        b = C.by_basis(C.load())
        gap = abs(b['evidenced']['accuracy'] - b['default']['accuracy'])
        self.assertLess(gap, 0.01)


class ConvictionIsNot(unittest.TestCase):
    """The same split sorts earned confidence from unearned, which is the finding."""

    def test_default_calls_score_worse_on_brier(self):
        b = C.by_basis(C.load())
        self.assertGreater(b['default']['brier'] - b['evidenced']['brier'], 0.05)

    def test_restatement_beats_the_oracle_without_predicting_better(self):
        s = C.scenarios(C.load())
        self.assertGreater(s['as_published'], C.ORACLE)      # today: worse than our own oracle
        self.assertLess(s['defaults_neutralised'], C.ORACLE)  # neutralise the else legs: better
        self.assertLess(s['honest_both'], s['defaults_neutralised'])

    def test_nothing_goes_below_the_coin(self):
        """No restatement can buy skill. The floor is real and the report says so."""
        s = C.scenarios(C.load())
        for k, v in s.items():
            self.assertGreaterEqual(round(v, 4), C.COIN, k)


class Report(unittest.TestCase):
    def test_report_prints_the_measured_label_and_the_floor(self):
        out = C.report()
        self.assertIn('MEASURED', out)
        self.assertIn('0.2500', out)
        self.assertIn('9,393', out)


if __name__ == '__main__':
    unittest.main()
