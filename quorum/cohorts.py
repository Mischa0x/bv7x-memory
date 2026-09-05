"""How many independent opinions are in a night? Fewer than the call count — or
so the obvious argument goes. This module tests that argument and reports that
it FAILS.

THE ARGUMENT. A call is a function of (rule, market snapshot). Every agent sees
the same snapshot on a given night, so two agents whose rules read the same
signals should be one opinion wearing two coats. On that view the field's 1,926
calls collapse to its ~72 signal-configurations, and any belief computed over
calls is overconfident by a factor of ~34.

THE TEST. If a configuration were an opinion, agents inside one would agree far
more than strangers do. So compare each cohort's internal agreement against the
agreement you would get from n INDEPENDENT agents drawing at the field's own UP
rate — E[max(k, n-k)]/n for k ~ Binomial(n, p), computed exactly.

THE RESULT (2026-08-27, 36 cohorts at n>=30): observed 56.07%, independence
predicts 56.53%, excess -0.45pp. Agents sharing a signal-configuration are
statistically indistinguishable from strangers. The argument is wrong.

WHY IT IS WRONG, and it agrees with what the estate already measured: a
configuration fixes WHICH signals a rule reads, not the THRESHOLDS it reads them
at. Thresholds are agent-specific, so two agents on {vix, roc7d} split on the
same snapshot. Prior research reached this at the atom level ("facts fragment");
this reaches it independently at the cohort level.

WHAT SURVIVES, and it is the load-bearing part. Every number above is
RECOVERABLE ONLY FROM MEMORY. The published record carries a direction per agent
and nothing else; a configuration is a property of the RULE, and the rule lives
in the store. Without memory you cannot compute this test, cannot answer whether
two agents were the same opinion — and cannot discover that they were not. The
capability memory confers here is not a better answer. It is the ability to ask
the question at all, and to have it come back NO.

No accuracy or edge claim lives in this module. It is a statement about
independence (BV7X-176 closed the accuracy question in writing).
"""
from collections import defaultdict
from math import comb

MIN_N = 30          # the same floor the rest of the tool applies


def expected_agreement(n: int, p: float) -> float:
    """Agreement among n INDEPENDENT agents each calling UP with probability p.

    E[max(k, n-k)] / n for k ~ Binomial(n, p) — computed exactly rather than
    simulated, so the baseline carries no sampling noise of its own. Note it is
    well above 50%: a majority of a small sample is lopsided by chance, and
    forgetting that is how coincidence gets read as consensus.
    """
    if n <= 0:
        return 0.0
    return sum(comb(n, k) * p**k * (1 - p)**(n - k) * max(k, n - k)
               for k in range(n + 1)) / n


def cohort_stats(records, signals_by_rule):
    """Group a night's calls by signal-configuration and test the clustering
    argument against an exact independence baseline.

    ``records``         — decision records (needs 'rule_id' and 'direction').
    ``signals_by_rule`` — rule_id -> the signals that rule reads.

    Returns None when there is nothing to say, so the caller renders CANNOT SAY
    rather than a zero.
    """
    calls = [r for r in records if r.get('direction') in ('UP', 'DOWN')]
    if not calls:
        return None

    p = sum(1 for r in calls if r['direction'] == 'UP') / len(calls)

    by_cfg = defaultdict(list)
    for r in calls:
        sig = signals_by_rule.get(r['rule_id'])
        # A call whose rule is not in memory cannot be placed. Bucket it
        # explicitly — a silently smaller denominator overstates the field.
        by_cfg[None if sig is None else tuple(sorted(sig))].append(r)

    placed = {k: v for k, v in by_cfg.items() if k is not None}
    unplaced = len(by_cfg.get(None, []))
    sizes = [len(v) for v in placed.values()]
    total = sum(sizes)
    if not total:
        return None

    # Kish's effective sample size — reported ONLY as the counterfactual the
    # test refutes, never as a finding. It assumes within-cohort correlation of
    # 1, which is exactly what `excess_pp` measures and finds absent.
    n_eff_if_clustered = (total ** 2) / sum(s * s for s in sizes)

    def one(cfg, rs):
        n = len(rs)
        up = sum(1 for r in rs if r['direction'] == 'UP')
        obs = max(up, n - up) / n
        exp = expected_agreement(n, p)
        return {'signals': list(cfg), 'n': n, 'up': up,
                'lean': 'UP' if up * 2 > n else ('DOWN' if up * 2 < n else 'split'),
                'agreement': obs if n >= MIN_N else None,
                'expected': exp if n >= MIN_N else None,
                'excess_pp': round((obs - exp) * 100, 1) if n >= MIN_N else None,
                'withheld': n < MIN_N}

    tested = [(c, rs) for c, rs in placed.items() if len(rs) >= MIN_N]
    obs_mean = exp_mean = excess = None
    if tested:
        obs_mean = sum(max(sum(1 for r in rs if r['direction'] == 'UP'),
                           len(rs) - sum(1 for r in rs if r['direction'] == 'UP')) / len(rs)
                       for _, rs in tested) / len(tested)
        exp_mean = sum(expected_agreement(len(rs), p) for _, rs in tested) / len(tested)
        excess = round((obs_mean - exp_mean) * 100, 2)

    largest = sorted(placed.items(), key=lambda kv: -len(kv[1]))[:6]

    return {
        'calls': total,
        'configurations': len(placed),
        'unplaced': unplaced,
        'up_rate': p,
        # the claim under test
        'n_eff_if_clustered': round(n_eff_if_clustered, 1),
        'collapse_if_clustered': round(total / n_eff_if_clustered, 1),
        # the test itself
        'tested_cohorts': len(tested),
        'observed_agreement': obs_mean,
        'expected_if_independent': exp_mean,
        'excess_pp': excess,
        'clustered': (excess is not None and excess >= 5.0),
        'verdict': (None if excess is None else
                    'cohorts cluster' if excess >= 5.0 else
                    'indistinguishable from independent'),
        'largest': [one(c, rs) for c, rs in largest],
    }
