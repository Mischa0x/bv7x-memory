"""The Base commitment — proof that the numbers were not tuned after the fact.

WHAT IS COMMITTED, AND WHY THAT AND NOT A FORECAST. Quorum's claim is about a
RECORD, so the thing worth pinning to a chain is the record's content: the frozen
field every panel is computed from, and the deletion-gate answer it produces. The
commitment is a digest over both. Anyone can recompute it from this repo and
check it against the attestation on Base, and the block timestamp proves it
existed before judging.

It deliberately does NOT commit a forecast. An open call's direction is the thing
BV-7X sells, and the standing rule is that it is never rendered — in aggregate or
per agent. Publishing one to earn a hackathon multiplier would trade the product
for a rosette. A content commitment proves we cannot cheat; a forecast commitment
would leak the product and prove less.

THE DIGEST IS sha256, NOT keccak. keccak256 is not in the Python standard
library, and the judge-facing half of this tool runs on the stdlib with no
network. sha256 is exactly as binding for this purpose, and it keeps `verify`
runnable by anyone with a clean Python. The Base side stores the same 32 bytes.

Preimage, one line, newline-free, fields joined by '|':

    quorum-attest-v1|<night>|<sha256 of tests/fixtures/rows.json>|E:<n>/<up>|N:<n>/<up>

  E: the evidenced (warranted) subset — the answer WITH memory.
  N: the naive vote — the answer WITHOUT memory, computed without opening the store.

Both halves are in the preimage on purpose: the entry's whole claim is that they
disagree, so the commitment pins the disagreement rather than one side of it.
"""
import hashlib
import json
import os

SCHEME = 'quorum-attest-v1'
HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, os.pardir, 'tests', 'fixtures', 'rows.json')
RECEIPT = os.path.join(HERE, os.pardir, 'attestation.json')


def fixture_digest(path: str = FIXTURES) -> str:
    """sha256 of the frozen field, byte for byte as committed."""
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b''):
            h.update(chunk)
    return h.hexdigest()


def preimage(night: str, evidenced: dict, naive: dict, fixtures: str = FIXTURES) -> str:
    return '|'.join([
        SCHEME,
        night,
        fixture_digest(fixtures),
        f"E:{evidenced['n']}/{evidenced['up']}",
        f"N:{naive['n']}/{naive['up']}",
    ])


def commitment(night: str, evidenced: dict, naive: dict, fixtures: str = FIXTURES) -> dict:
    pre = preimage(night, evidenced, naive, fixtures)
    return {'scheme': SCHEME, 'night': night, 'preimage': pre,
            'commitment': '0x' + hashlib.sha256(pre.encode()).hexdigest()}


def compute(night: str, store: str) -> dict:
    """Build the commitment from the two answers the tool actually produces.

    Imported here rather than at module top so `verify` stays importable with no
    store present — the deletion gate applies to this file too.
    """
    from .server import field_on, field_off
    on, off = field_on(night, store), field_off(night)
    if on.get('status') != 'ok':
        raise SystemExit(f"cannot commit: memory says {on.get('status')} — {on.get('reason', '')}")
    return commitment(night, on['belief'], off['belief'])


def verify(receipt_path: str = RECEIPT) -> dict:
    """Recompute the commitment from this repo and compare it to the receipt.

    Needs no key, no network and no store — the fixture and the recorded answers
    are enough, which is the point: a judge can run this on a clean checkout.
    """
    if not os.path.exists(receipt_path):
        return {'ok': False, 'reason': f'no receipt at {receipt_path}'}
    with open(receipt_path) as fh:
        r = json.load(fh)
    want = commitment(r['night'], r['evidenced'], r['naive'])
    ok = (want['commitment'] == r['commitment'] and want['preimage'] == r['preimage'])
    return {
        'ok': ok,
        'night': r['night'],
        'recomputed': want['commitment'],
        'attested': r['commitment'],
        'fixture_digest_matches': fixture_digest() == r['fixture_sha256'],
        'chain': r.get('chain'),
        'tx': r.get('tx'),
        'uid': r.get('uid'),
        'explorer': r.get('explorer'),
        'reason': None if ok else 'the repo does not reproduce the attested commitment',
    }
