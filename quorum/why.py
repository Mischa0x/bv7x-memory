"""Atom evaluation — WHICH facts produced a call, at the moment it was made.

This is a PORT of the production evaluator, ``polypool/agents/services/
predicateEval.js`` (``evalLeg``, ``evalPredicate``, ``signalsOf``,
``predicateShape``), and it must agree with it on every live row. The
semantics are theirs; nothing here is invented. ``tests/test_parity.py``
asserts the agreement against a frozen dump of the real field, and CI
regenerates the JS side from a byte-identical vendored copy so the two
cannot drift apart silently.

Why a port and not a probe. The research script this grew out of accepted
``==`` and ``!=`` (production does not), evaluated every atom (production
short-circuits on the first false one, so a null in a LATER atom is
irrelevant), and had no notion of ``SKIP`` (a needed signal was null that
day — excluded from the sample, NOT an abstention). Each of those is a
place where "why did this agent call UP" would have been answered with a
fact that did not actually decide anything.

Vocabulary, pinned from the source:

* A predicate is two one-sided legs, ``up`` and ``down``. A leg is ``None``
  (absent), the string ``'else'``, or ``{'all': [atom, ...]}`` — a flat AND
  of 1–4 atoms. No nesting, no OR, no signal-vs-signal.
* An atom is ``{'signal', 'op', 'value'}`` with ``op`` in ``> >= < <=``.
* A row is the day vector keyed by signal name. Values are numbers; anything
  that is not a finite number (``None``, a bool, a string, NaN, inf) is
  treated exactly as JS ``Number.isFinite`` treats it: as missing.
* ``evaluate`` returns ``'UP'``, ``'DOWN'``, ``None`` (evaluable, nothing
  fired — an abstention), ``'SKIP'`` (a needed signal was missing), or
  ``'CONFLICT'`` (both legs fired; counted, no fire).
"""
from __future__ import annotations

import math
from typing import Any

# Exactly production's table. ``==`` and ``!=`` are deliberately absent.
OPS = {
    '>':  lambda a, b: a > b,
    '>=': lambda a, b: a >= b,
    '<':  lambda a, b: a < b,
    '<=': lambda a, b: a <= b,
}
MAX_ATOMS_PER_LEG = 4

SKIP = 'SKIP'
CONFLICT = 'CONFLICT'


def _finite(v: Any) -> bool:
    """JS ``Number.isFinite`` — no coercion. ``True``/``False`` are not numbers,
    strings are not numbers, NaN and inf are not finite."""
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return math.isfinite(v)
    return False


def eval_leg(leg: dict, row: dict) -> bool | str:
    """One conjunction leg against a row → ``True`` | ``False`` | ``'SKIP'``.

    Port of ``evalLeg``. The order of the two checks is load-bearing: a
    missing signal returns SKIP only if every EARLIER atom held. One false
    atom decides the leg and the day stays in-sample as long as THIS leg
    resolved; nulls elsewhere in the row are irrelevant to it.
    """
    for atom in leg['all']:
        v = row.get(atom['signal'])
        if not _finite(v):
            return SKIP
        if not OPS[atom['op']](v, atom['value']):
            return False
    return True


def evaluate(predicate: dict, row: dict) -> str | None:
    """Port of ``evalPredicate``. See the module docstring for the contract.

    Sides are evaluated in the order ``up`` then ``down``, and a SKIP on
    ``up`` returns before ``down`` is looked at. That ordering is production's
    and it is observable — a row whose up leg is SKIP and whose down leg would
    have been false is SKIP, not an abstention.
    """
    conj: dict[str, bool | str | None] = {'up': None, 'down': None}
    for side in ('up', 'down'):
        leg = predicate.get(side)
        if leg is not None and leg != 'else':
            conj[side] = eval_leg(leg, row)
            if conj[side] == SKIP:
                return SKIP
    fired = {'up': conj['up'] is True, 'down': conj['down'] is True}
    # An "else" leg fires when the OPPOSITE conjunction resolved and is false.
    if predicate.get('up') == 'else':
        fired['up'] = conj['down'] is False
    if predicate.get('down') == 'else':
        fired['down'] = conj['up'] is False
    if fired['up'] and fired['down']:
        return CONFLICT
    if fired['up']:
        return 'UP'
    if fired['down']:
        return 'DOWN'
    return None


def signals_of(predicate: dict) -> list[str]:
    """Union of signals the predicate actually reads — derived, never trusted
    from anywhere else. Port of ``signalsOf``; preserves first-seen order the
    way a JS ``Set`` does."""
    out: list[str] = []
    for side in ('up', 'down'):
        leg = predicate.get(side)
        if leg is not None and leg != 'else':
            for a in leg['all']:
                if a['signal'] not in out:
                    out.append(a['signal'])
    return out


def shape(predicate: dict) -> dict:
    """Port of ``predicateShape``: each side is ``'conj'``, ``'else'`` or
    ``'none'``; plus the three named shapes the estate reasons about."""
    def kind(leg: Any) -> str:
        if leg == 'else':
            return 'else'
        return 'conj' if leg else 'none'
    up, down = kind(predicate.get('up')), kind(predicate.get('down'))
    conj = sum(1 for k in (up, down) if k == 'conj')
    none = sum(1 for k in (up, down) if k == 'none')
    return {
        'up': up,
        'down': down,
        'one_legged': conj == 1 and none == 1,
        'total': up == 'else' or down == 'else',
        'gapped': up == 'conj' and down == 'conj',
    }


# ── The WHY ────────────────────────────────────────────────────────────────
#
# Everything above reproduces production. This is the part the product is
# built on: not WHAT the agent called, but WHICH FACTS made it call that.
#
# For a conjunction leg the answer is the atoms themselves — every one held,
# by construction, or the leg would not have fired. For an "else" leg the
# honest answer is different in kind: the agent's STATED condition did not
# hold, and the facts that decided the call are the atoms of the opposite
# leg that FAILED. The copy rule that follows from this is in the plan and
# it is not optional: an else-fire is "its stated condition did not fire",
# never "the agent had no strategy". A default is not necessarily lazy —
# some rules are written so the else leg IS the thesis.

def why(predicate: dict, row: dict) -> dict:
    """Decompose one call into the facts that produced it.

    Returns ``{'direction', 'basis', 'atoms'}`` where

    * ``direction`` is exactly ``evaluate(predicate, row)``;
    * ``basis`` is ``'evidenced'`` (a conjunction fired — the call rests on
      stated facts that held), ``'default'`` (an else leg fired — the call
      rests on the opposite condition failing), or ``None`` when there is no
      call (abstain / SKIP / CONFLICT);
    * ``atoms`` lists the deciding facts as ``{'signal','op','value',
      'observed','held'}``. For an evidenced call every atom has ``held=True``.
      For a default call the atoms are the opposite leg's, and at least one
      has ``held=False`` — those are the facts that decided it.
    """
    direction = evaluate(predicate, row)
    if direction not in ('UP', 'DOWN'):
        return {'direction': direction, 'basis': None, 'atoms': []}

    side = direction.lower()
    leg = predicate.get(side)

    def describe(atoms: list[dict], stop_at_first_failure: bool) -> list[dict]:
        out = []
        for a in atoms:
            v = row.get(a['signal'])
            held = OPS[a['op']](v, a['value']) if _finite(v) else None
            out.append({'signal': a['signal'], 'op': a['op'], 'value': a['value'],
                        'observed': v if _finite(v) else None, 'held': held})
            if stop_at_first_failure and held is False:
                # Production's eval_leg short-circuits here. Atoms after this
                # one were never consulted, so they did not decide anything
                # and reporting their state would claim knowledge the
                # evaluator did not use.
                break
        return out

    if leg == 'else':
        other = predicate.get('down' if side == 'up' else 'up')
        # evaluate() only returns a direction for an else leg when the other
        # side is a conjunction that resolved false, so `other` is a dict here.
        return {'direction': direction, 'basis': 'default',
                'atoms': describe(other['all'], stop_at_first_failure=True)}

    # Every atom of a fired conjunction held, by construction.
    return {'direction': direction, 'basis': 'evidenced',
            'atoms': describe(leg['all'], stop_at_first_failure=False)}
