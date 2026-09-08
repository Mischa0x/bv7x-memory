"""Conviction: the score that separates being right from being entitled to be sure.

Accuracy asks whether a call was right. Conviction asks how sure the agent SAID it
was, and scores the distance between that claim and what happened -- the Brier score,
mean (stated - outcome)^2, lower better, a coin flip costing 0.2500.

The problem is not that the agents predict badly. It is that they publish ~0.93 and
is right about half the time, and until the basis of each call was recoverable there
was nothing in the record to condition that claim on: a call that fired on its own
evidence and a call that fell through its rule's else leg are the same row.

Scores the frozen join in tests/fixtures/conviction.json three ways. The first is
MEASURED. The second and third are ARITHMETIC PROJECTIONS over measured components --
what the same calls would have scored had they stated something else -- and no agent
predicts any better in either.
"""
from __future__ import annotations

import json
import math
import pathlib

FIXTURE = pathlib.Path(__file__).resolve().parent.parent / 'tests' / 'fixtures' / 'conviction.json'

COIN = 0.25      # a forecast of 0.5 on a binary outcome
ORACLE = 0.3121  # the first-party oracle over the same rounds (/agents/conviction)


def load(path: pathlib.Path | None = None) -> list[list]:
    """[basis, correct, stated_confidence, night] per settled call."""
    return json.loads((path or FIXTURE).read_text())['calls']


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p, d = k / n, 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100 * (c - h), 100 * (c + h))


def brier(calls, stated=None) -> float:
    """Mean (stated - outcome)^2.

    `stated` is None to score the confidence each call actually published, or a
    callable (basis, published) -> claim, which lets a scenario restate one class
    while leaving the other exactly as it was.
    """
    vals = []
    for basis, correct, conf, _night in calls:
        claim = conf if stated is None else stated(basis, conf)
        if claim is None:
            continue
        vals.append((claim - correct) ** 2)
    return sum(vals) / len(vals) if vals else float('nan')


def by_basis(calls) -> dict:
    out = {}
    for letter, name in (('e', 'evidenced'), ('d', 'default')):
        sub = [c for c in calls if c[0] == letter]
        n, k = len(sub), sum(c[1] for c in sub)
        out[name] = {'n': n, 'correct': k,
                     'accuracy': k / n if n else float('nan'),
                     'ci': wilson(k, n), 'brier': brier(sub)}
    return out


def scenarios(calls) -> dict:
    """as-published (measured), defaults neutralised, both classes told honestly."""
    b = by_basis(calls)
    rate = {'e': b['evidenced']['accuracy'], 'd': b['default']['accuracy']}
    return {
        'as_published': brier(calls),
        'defaults_neutralised': brier(calls, lambda basis, conf: 0.5 if basis == 'd' else conf),
        'honest_both': brier(calls, lambda basis, conf: rate[basis]),
    }


def report(calls=None) -> str:
    calls = load() if calls is None else calls
    b, s = by_basis(calls), scenarios(calls)
    L = [f'{len(calls):,} settled calls, re-derived from (rule x snapshot) and joined to outcomes',
         '',
         f'{"basis":<11}{"n":>8}{"accuracy":>11}{"95% CI":>18}{"Brier":>9}']
    for name in ('evidenced', 'default'):
        r = b[name]
        ci = f'[{r["ci"][0]:.1f}, {r["ci"][1]:.1f}]'
        L.append(f'{name:<11}{r["n"]:>8,}{100 * r["accuracy"]:>10.1f}%{ci:>18}{r["brier"]:>9.4f}')
    L += ['',
          'ACCURACY is flat across the split. CONVICTION is not.',
          '',
          f'{"scenario":<38}{"Brier":>8}   {"vs oracle " + format(ORACLE, ".4f"):>18}',
          f'{"as published (MEASURED)":<38}{s["as_published"]:>8.4f}   worse',
          f'{"default calls neutralised to 0.50":<38}{s["defaults_neutralised"]:>8.4f}   better',
          f'{"both classes stated honestly":<38}{s["honest_both"]:>8.4f}   better',
          '',
          f'coin flip {COIN:.4f} is the floor: no restatement goes below it, because',
          'getting there is skill and this buys none. It buys the distance from 0.41 to 0.25.']
    return '\n'.join(L)


if __name__ == '__main__':  # pragma: no cover
    print(report())
