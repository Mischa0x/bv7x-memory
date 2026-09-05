"""Engagement — the one thing here that a single night cannot tell you.

Every earlier probe was cross-sectional: one night, one snapshot, a pure
function of that night's ledger. This one is temporal. It asks, for each rule,
whether its stated condition has ever actually fired — and classifies the rule
from the nights STRICTLY BEFORE tonight, so the answer is what memory knew when
tonight's call was made, not what it learned afterwards.

THE FINDING (21 nights, 996 rules with >= 8 calls): 82% never changed their
call. 567 were never evidenced — their condition never held, they called through
the else leg every night, one direction, 567/567. 254 were always evidenced —
their condition always held, one direction, 252/254. Only 175 ever switched.
Within-rule split-half correlation of engagement: r = +0.87. It is a trait, not
a coincidence, and it survives the shape control (988 of the 996 are total
predicates that CAN go either way) and the regime control (distanceFromMA200
spanned 25 points, roc7d 26 — the market moved; those rules did not).

WHAT IT DOES TO THE SIGNAL. The naive vote counts every agent as an independent
nightly read. But an agent whose call has not changed in three weeks carries no
information about TONIGHT — it is deploy-time composition, a bias term fixed
when its threshold was written. Only the switching agents are market-responsive.
On 2026-09-01 the naive interval is roughly three times narrower than the
responsive one: the aggregate's stated precision is manufactured by counting
agents that cannot move.

THIS IS ABOUT PRECISION, NOT ACCURACY. It says the field's stated uncertainty
is wrong, not that any direction is right — which keeps it inside "conviction is
the metric" and outside the accuracy programme BV7X-176 closed.

WHY IT IS MEMORY. You cannot tell a constant-output agent from a responsive one
on one night; they look identical. It takes a history. Classification needs
MIN_PRIOR_NIGHTS of that rule's own calls before tonight, so early nights render
CANNOT SAY — not because the code failed but because memory is still shallow —
and the panel lights up as memory deepens. Delete the store and tonight's answer
does not degrade to a view; the ability to state an honest interval is gone.
"""
from collections import defaultdict

from .record import wilson

MIN_PRIOR_NIGHTS = 6     # a rule needs this many prior calls to be classified
MIN_N = 30               # no rate, and no interval, below this — the tool's one floor


def classify(prior_basis):
    """One rule's engagement class from its PRIOR calls' bases.

    'always'    — every prior call rested on its stated condition holding
    'never'     — no prior call did; it always fell through the else leg
    'switching' — it has done both, i.e. its rule has actually responded
    None        — fewer than MIN_PRIOR_NIGHTS prior calls: memory too shallow
    """
    calls = [b for b in prior_basis if b in ('evidenced', 'default')]
    if len(calls) < MIN_PRIOR_NIGHTS:
        return None
    e = sum(1 for b in calls if b == 'evidenced')
    return 'always' if e == len(calls) else 'never' if e == 0 else 'switching'


def _share(directions):
    n = len(directions)
    k = sum(1 for d in directions if d == 'UP')
    ci = wilson(k, n) if n >= MIN_N else None
    return {'n': n, 'up': k, 'up_share': (k / n) if n else None, 'ci': ci,
            'width_pp': round((ci[1] - ci[0]) * 100, 1) if ci else None,
            'rate_withheld': n < MIN_N}


def decompose(calls_by_rule, basis_by_rule, tonight):
    """The full decomposition. ``calls_by_rule`` — {rule_id: direction} for
    tonight's calls. Returns the naive belief, the responsive belief, the
    per-class breakdown, and the precision ratio — or CANNOT SAY with a reason."""
    nights = sorted({n for h in basis_by_rule.values() for n in h})
    prior = [n for n in nights if n < tonight]

    by_class = defaultdict(list)
    for rid, d in calls_by_rule.items():
        if d not in ('UP', 'DOWN'):
            continue
        hist = basis_by_rule.get(rid, {})
        by_class[classify([hist[n] for n in prior if n in hist])].append(d)

    all_dirs = [d for ds in by_class.values() for d in ds]
    classified = sum(len(v) for k, v in by_class.items() if k is not None)
    switching = by_class.get('switching', [])

    base = {'night': tonight, 'prior_nights': len(prior), 'min_prior_nights': MIN_PRIOR_NIGHTS,
            'calls': len(all_dirs), 'classified': classified,
            'unclassified': len(by_class.get(None, []))}

    if len(prior) < MIN_PRIOR_NIGHTS:
        return {**base, 'status': 'CANNOT SAY',
                'reason': f'only {len(prior)} prior night(s) in memory; classification needs {MIN_PRIOR_NIGHTS}'}
    if len(switching) < MIN_N:
        return {**base, 'status': 'CANNOT SAY',
                'reason': (f'{classified:,} of {len(all_dirs):,} callers have {MIN_PRIOR_NIGHTS}+ prior nights, '
                           f'and only {len(switching)} of those ever switched — below the n>={MIN_N} floor')}

    naive, resp = _share(all_dirs), _share(switching)
    return {**base, 'status': 'ok',
            'classes': {k: _share(v) for k, v in by_class.items() if k is not None},
            'constant_share': (sum(len(by_class.get(k, [])) for k in ('always', 'never')) / classified) if classified else None,
            'naive': naive,
            'responsive': resp,
            'precision_ratio': (round(resp['width_pp'] / naive['width_pp'], 1)
                                if naive['width_pp'] and resp['width_pp'] else None)}
