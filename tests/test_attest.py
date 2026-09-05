"""The Base commitment: what it binds, and that tampering breaks it.

The claim the attestation makes is narrow and worth stating exactly: the frozen
field in this repo, and the deletion-gate answer it produces, existed in this
form before the on-chain timestamp. These tests check that the binding is real —
that changing any of it changes the digest — and that verification needs nothing
a judge would not have.
"""
import json
import os
import tempfile
import unittest

from quorum.attest import RECEIPT, SCHEME, commitment, fixture_digest, preimage, verify

E = {'n': 588, 'up': 281}
N = {'n': 715, 'up': 388}
NIGHT = '2026-08-27'


class Preimage(unittest.TestCase):
    def test_is_one_line_and_self_describing(self):
        p = preimage(NIGHT, E, N)
        self.assertNotIn('\n', p)
        self.assertTrue(p.startswith(SCHEME + '|'))
        self.assertIn(NIGHT, p)
        self.assertIn('E:588/281', p)
        self.assertIn('N:715/388', p)

    def test_binds_BOTH_answers(self):
        """The entry's claim is that the two disagree, so the commitment must pin
        the disagreement — not one side of it."""
        base = commitment(NIGHT, E, N)['commitment']
        self.assertNotEqual(base, commitment(NIGHT, {'n': 588, 'up': 282}, N)['commitment'])
        self.assertNotEqual(base, commitment(NIGHT, E, {'n': 715, 'up': 389})['commitment'])

    def test_binds_the_night(self):
        self.assertNotEqual(commitment(NIGHT, E, N)['commitment'],
                            commitment('2026-08-26', E, N)['commitment'])

    def test_binds_the_frozen_field(self):
        """Edit the fixture and the commitment must move — otherwise the
        attestation would say nothing about the data the panels are computed from."""
        d = tempfile.mkdtemp()
        tampered = os.path.join(d, 'rows.json')
        with open(tampered, 'w') as fh:
            fh.write('{"rows": []}')
        self.assertNotEqual(fixture_digest(), fixture_digest(tampered))
        self.assertNotEqual(commitment(NIGHT, E, N)['commitment'],
                            commitment(NIGHT, E, N, tampered)['commitment'])

    def test_is_deterministic(self):
        self.assertEqual(commitment(NIGHT, E, N), commitment(NIGHT, E, N))


class Verify(unittest.TestCase):
    def test_the_committed_receipt_reproduces(self):
        """The whole point: a clean checkout recomputes what is on Base."""
        r = verify()
        self.assertTrue(r['ok'], r.get('reason'))
        self.assertTrue(r['fixture_digest_matches'])
        self.assertEqual(r['recomputed'], r['attested'])
        self.assertEqual(r['chain'], 'base-mainnet-8453')
        self.assertTrue(str(r['tx']).startswith('0x'))

    def test_a_doctored_receipt_fails(self):
        with open(RECEIPT) as fh:
            r = json.load(fh)
        r['evidenced'] = {'n': 588, 'up': 400}          # flatter the finding
        d = tempfile.mkdtemp()
        bad = os.path.join(d, 'attestation.json')
        with open(bad, 'w') as fh:
            json.dump(r, fh)
        out = verify(bad)
        self.assertFalse(out['ok'])
        self.assertIn('does not reproduce', out['reason'])

    def test_missing_receipt_is_reported_not_raised(self):
        out = verify('/nonexistent/attestation.json')
        self.assertFalse(out['ok'])
        self.assertIn('no receipt', out['reason'])

    def test_receipt_carries_no_key_material(self):
        """A receipt is published; a key is not. Assert the obvious explicitly."""
        with open(RECEIPT) as fh:
            blob = fh.read().lower()
        for bad in ('private', 'privkey', 'mnemonic', 'seed', 'secret'):
            self.assertNotIn(bad, blob)


if __name__ == '__main__':
    unittest.main()
