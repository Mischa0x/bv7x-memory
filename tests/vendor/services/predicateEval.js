/**
 * predicateEval — the deterministic half of a strategy (3RDI-036 / BV7X-036).
 *
 * CANONICAL-COPY (3RDI-118 / BV7X-147): byte-identical in both forks, listed
 * in CORE-MANIFEST.json; fork-specific values come only from constants.IDENTITY.
 * Edit via the scripts/core-sync.js discipline so both trees move together.
 *
 * A predicate is the machine-executable shadow of a compiled entryRule:
 * two one-sided legs (UP / DOWN), each a flat AND of atomic threshold
 * comparisons over the shared 17-signal vocabulary. Deliberately SMALL —
 * no nesting, no OR inside a leg, no signal-vs-signal comparison. What the
 * schema cannot express is honestly "not backtestable", never approximated.
 *
 * This module is pure and carries no backtest assumptions on purpose: it is
 * also the future $0 nightly evaluator (scale-readiness #4) — the same
 * `evalPredicate(predicate, row)` that grades 5,659 historical days can one
 * day replace the paid per-agent LLM evaluation, once fidelity is proven.
 *
 * Sign/unit conventions (panel-native, pinned here and in the extraction
 * prompt): distanceFromMA200/50 and roc7d in percent points; drawdown30d is
 * NEGATIVE percent from the 30-day high (a "10% drawdown" is <= -10) — an
 * atom comparing drawdown30d against a positive value is REJECTED, never
 * silently mirrored; etfFlows7d in $M; fearGreed 0-100; price USD.
 */
const { VALID_SIGNALS } = require('../config/signalVocabulary');

const OPS = {
  '>': (a, b) => a > b,
  '>=': (a, b) => a >= b,
  '<': (a, b) => a < b,
  '<=': (a, b) => a <= b,
};
const MAX_ATOMS_PER_LEG = 4;

/* ── BV7X-201 — TARGETS: a leg may express HOW FAR, not only WHETHER ────────
 *
 * Operator decision 2026-08-22: agents emit a granular prediction as well as a
 * direction, and the direction DEPENDS ON the granular one. Until now this
 * language was structurally incapable of it — a leg is a flat AND of threshold
 * comparisons, which decides a boolean and can never yield a magnitude.
 *
 * A target is OPTIONAL and the schema stays `predicate_version: 1`. A predicate
 * without targets validates and evaluates EXACTLY as before, byte for byte —
 * that is the off-by-default posture, expressed as an absent field rather than
 * a flag someone has to remember to set.
 *
 *   target: { pct: <number> }                              // constant move
 *   target: { pct: <number>, scale: { signal, k } }        // condition-scaled
 *
 * effective move % = pct + k * row[signal]      (scale optional)
 * target price      = entry * (1 + move / 100)
 *
 * WHY `scale` EXISTS AND IS NOT DECORATION. A constant pct already differs
 * per agent, which is enough for a distribution to exist — but a constant is
 * not a forecast, it is an offset, and a field of constants aggregates to
 * something that never responds to the market. The scale term is what lets two
 * agents disagree about how far BECAUSE they disagree about conditions, which
 * is the only thing that makes a stake-weighted median mean anything. A single
 * signal, linear, no nesting — the same austerity the atoms follow, and for the
 * same reason: what the schema cannot express is honestly not backtestable.
 *
 * THE SIGN RULE IS THE OPERATOR'S DEPENDENCY, MADE UNREPRESENTABLE-IF-VIOLATED.
 * An UP leg's move must be positive and a DOWN leg's negative, so "DOWN beside
 * a higher target" cannot be stored. With `scale` the effective move is
 * data-dependent and CAN flip sign on a given day; that is checked at eval time
 * and REFUSED rather than emitted, because a contradictory pair is exactly the
 * silent-wrong-answer class KI #103 is about. Refusing loses a day's call;
 * assuming would publish a call whose number and direction disagree.
 */
const MAX_ABS_MOVE_PCT = 50;   // a >50% move at a 1-7d horizon is a typo, not a forecast

function validateTarget(target, name) {
  if (target === null || target === undefined) return { target: null };
  if (typeof target !== 'object') return { error: `${name} target must be an object` };
  if (typeof target.pct !== 'number' || !Number.isFinite(target.pct)) {
    return { error: `${name} target has a non-finite pct` };
  }
  if (target.pct === 0) {
    // Zero is not "no movement" — it is a direction-less call, and this estate
    // has already paid for one: the legacy NEUTRAL/HOLD row that carried
    // oracle_correct:false and dragged the record to 33/59 while the scorecard
    // read 33/58 (fixed 2026-08-07). An agent with no view abstains by having
    // no leg fire; it does not predict zero.
    return { error: `${name} target pct is zero — abstain by not firing, never by predicting no movement` };
  }
  if (Math.abs(target.pct) > MAX_ABS_MOVE_PCT) {
    return { error: `${name} target pct ${target.pct} exceeds +/-${MAX_ABS_MOVE_PCT}` };
  }
  let scale = null;
  if (target.scale !== null && target.scale !== undefined) {
    const s = target.scale;
    if (typeof s !== 'object') return { error: `${name} target scale must be an object` };
    if (!VALID_SIGNALS.has(s.signal)) return { error: `unknown scale signal "${s.signal}"` };
    if (typeof s.k !== 'number' || !Number.isFinite(s.k)) {
      return { error: `${name} target scale has a non-finite k` };
    }
    if (s.k === 0) return { error: `${name} target scale k is zero — drop the scale instead` };
    scale = { signal: s.signal, k: s.k };
  }
  // Sign agreement with the leg it sits on. Checked statically here on `pct`;
  // the scaled value is re-checked per row in evalTarget, where it can differ.
  const wantPositive = name === 'up';
  if (wantPositive && target.pct < 0) return { error: 'up leg target must be a positive move' };
  if (!wantPositive && target.pct > 0) return { error: 'down leg target must be a negative move' };
  return { target: scale ? { pct: target.pct, scale } : { pct: target.pct } };
}

function validateLeg(leg, name) {
  if (leg === null || leg === undefined) return { leg: null };
  if (leg === 'else') return { leg: 'else' };
  if (typeof leg !== 'object' || !Array.isArray(leg.all)) {
    return { error: `${name} leg must be null, "else", or {all:[...]}` };
  }
  if (leg.all.length < 1 || leg.all.length > MAX_ATOMS_PER_LEG) {
    return { error: `${name} leg needs 1-${MAX_ATOMS_PER_LEG} atoms` };
  }
  for (const atom of leg.all) {
    if (!atom || typeof atom !== 'object') return { error: `${name} leg has a non-object atom` };
    if (!VALID_SIGNALS.has(atom.signal)) return { error: `unknown signal "${atom.signal}"` };
    if (!OPS[atom.op]) return { error: `unknown op "${atom.op}" (allowed: > >= < <=)` };
    if (typeof atom.value !== 'number' || !Number.isFinite(atom.value)) {
      return { error: `atom on "${atom.signal}" has a non-finite value` };
    }
    if (atom.signal === 'drawdown30d' && atom.value > 0) {
      // The panel's drawdown is negative. A positive threshold means the
      // extraction (or the human) flipped the sign — refusing beats a silent
      // mirror transform that could invert the strategy.
      return { error: 'drawdown_sign_ambiguous' };
    }
  }
  return { leg: { all: leg.all.map(a => ({ signal: a.signal, op: a.op, value: a.value })) } };
}

/**
 * @returns {{ok: true, predicate} | {ok: false, reason}}
 */
function validatePredicate(p) {
  if (!p || typeof p !== 'object') return { ok: false, reason: 'predicate_null' };
  if (p.predicate_version !== 1) return { ok: false, reason: 'unknown predicate_version' };
  const up = validateLeg(p.up, 'up');
  if (up.error) return { ok: false, reason: up.error };
  const down = validateLeg(p.down, 'down');
  if (down.error) return { ok: false, reason: down.error };
  if (up.leg === null && down.leg === null) return { ok: false, reason: 'both legs empty' };
  const elseCount = [up.leg, down.leg].filter(l => l === 'else').length;
  if (elseCount > 1) return { ok: false, reason: 'only one leg may be "else"' };
  if (elseCount === 1) {
    const other = up.leg === 'else' ? down.leg : up.leg;
    if (!other || other === 'else') return { ok: false, reason: '"else" needs a conjunction on the other leg' };
  }
  // BV7X-201 targets live at PREDICATE level, not on the leg, because a leg
  // may be the string 'else' — there is nowhere on it to hang a field, and
  // widening the leg's type from `null | 'else' | {all}` to carry one would
  // touch every consumer that pattern-matches on it. An 'else' leg fires and
  // therefore needs a magnitude exactly like a conjunction does.
  const out = { predicate_version: 1, up: up.leg, down: down.leg };
  const t = p.targets;
  if (t !== null && t !== undefined) {
    if (typeof t !== 'object') return { ok: false, reason: 'targets must be an object' };
    const upT = validateTarget(t.up, 'up');
    if (upT.error) return { ok: false, reason: upT.error };
    const downT = validateTarget(t.down, 'down');
    if (downT.error) return { ok: false, reason: downT.error };
    // A target on a leg that cannot fire is dead configuration, and dead
    // configuration is how a strategy comes to look like it forecasts a
    // magnitude it will never emit. Refuse it rather than storing it.
    if (upT.target && up.leg === null) return { ok: false, reason: 'up target on an absent up leg' };
    if (downT.target && down.leg === null) return { ok: false, reason: 'down target on an absent down leg' };
    if (upT.target || downT.target) {
      out.targets = { up: upT.target, down: downT.target };
    }
  }
  return { ok: true, predicate: out };
}

/**
 * Classify a validated predicate's leg shape (pure — no market data).
 * Each side is 'conj' (a conjunction), 'else', or 'none' (null leg).
 *   - oneLegged: exactly one conjunction and the other side empty — the rule
 *     can only ever fire in that one direction and abstains structurally in
 *     the other, so it cannot accrue a two-sided record (BV7X-010 / 3RDI-057).
 *   - total: an "else" leg fills every non-firing day, so the rule never abstains.
 *   - gapped: two conjunctions with no "else" — fires both ways but abstains
 *     when neither conjunction holds (the 3RDI-020 / BV7X-020 abstention-gap shape).
 */
function predicateShape(predicate) {
  const kind = (leg) => (leg === 'else' ? 'else' : (leg ? 'conj' : 'none'));
  const up = kind(predicate.up);
  const down = kind(predicate.down);
  const conj = [up, down].filter(k => k === 'conj').length;
  const none = [up, down].filter(k => k === 'none').length;
  return {
    up,
    down,
    oneLegged: conj === 1 && none === 1,
    total: up === 'else' || down === 'else',
    gapped: up === 'conj' && down === 'conj',
  };
}

/**
 * Non-blocking deploy-time advisories about a rule's shape (3RDI-057 / BV7X-010).
 * A style note today, surfaced on the deploy receipt and logged; NOT a gate —
 * upgrading it to a certification requirement waits on 3RDI-020 / BV7X-020's
 * evidence — and the operator's standing rule that agents are never forced
 * (users write rules freely; the else-leg warning stays an advisory).
 * @returns {Array<{code: string, message: string}>}
 */
function deployWarnings(predicate) {
  const out = [];
  if (!predicate) return out;
  const s = predicateShape(predicate);
  if (s.oneLegged) {
    const dir = s.up === 'conj' ? 'UP' : 'DOWN';
    const other = dir === 'UP' ? 'DOWN' : 'UP';
    out.push({
      code: 'one_legged_predicate',
      message: `This rule can only ever predict ${dir}: it has no ${other} leg, so it abstains on every day its condition is false and cannot accrue a two-sided record. Add an "otherwise predict ${other}" leg to make it total.`,
    });
  }
  return out;
}

/** Union of signals the predicate actually reads — derived, never LLM-trusted. */
function signalsOf(predicate) {
  const out = new Set();
  for (const leg of [predicate.up, predicate.down]) {
    if (leg && leg !== 'else') for (const a of leg.all) out.add(a.signal);
  }
  return [...out];
}

/** Evaluate one conjunction leg against a row: true | false | 'SKIP' (null data). */
function evalLeg(leg, row) {
  for (const atom of leg.all) {
    const v = row[atom.signal];
    if (v === null || v === undefined || !Number.isFinite(v)) return 'SKIP';
    if (!OPS[atom.op](v, atom.value)) {
      // Still verify the remaining atoms are evaluable? No — one false atom
      // decides the leg, and the day stays in-sample as long as THIS leg
      // resolved. Nulls elsewhere in the row are irrelevant to this leg.
      return false;
    }
  }
  return true;
}

/**
 * @param {object} predicate - a validatePredicate-approved predicate
 * @param {object} row       - a day vector keyed by the signal vocabulary
 * @returns {'UP'|'DOWN'|null|'SKIP'|'CONFLICT'}
 *   null = evaluable, no fire (abstention); SKIP = a needed signal was null
 *   that day (excluded from the sample, NOT an abstention); CONFLICT = both
 *   legs fired (counted, no fire).
 */
function evalPredicate(predicate, row) {
  const conj = { up: null, down: null };
  for (const side of ['up', 'down']) {
    const leg = predicate[side];
    if (leg && leg !== 'else') {
      conj[side] = evalLeg(leg, row);
      if (conj[side] === 'SKIP') return 'SKIP';
    }
  }
  const fired = { up: conj.up === true, down: conj.down === true };
  // An "else" leg fires when the opposite conjunction resolved and is false.
  if (predicate.up === 'else') fired.up = conj.down === false;
  if (predicate.down === 'else') fired.down = conj.up === false;

  if (fired.up && fired.down) return 'CONFLICT';
  if (fired.up) return 'UP';
  if (fired.down) return 'DOWN';
  return null;
}

// ── Confidence ──────────────────────────────────────────────────────────────
//
// A predicate has no probability model, so this is NOT a calibrated
// probability and must never be presented as one. It answers a narrower,
// honest question: how far inside the firing region did this decision land,
// measured in "one meaningful step" units for each signal?
//
// The band is deliberately narrow. bitvault's own interpreter rejects a
// confidence of exactly 1.0 or 0.0 as suspicious, so emitting either would look
// like a compromised evaluation by the house's own rule; and claiming 0.95
// because RSI cleared its threshold by 20 points would be a lie about
// calibration we cannot back.
//
// Both the band and the curve are FIRST SETTINGS. The shadow window records
// this value without submitting it precisely so the histogram can decide
// whether a spread exists at all — if it turns out degenerate, a documented
// constant is the more honest answer and this function should be deleted.
const CONF_MIN = 0.55;
const CONF_SPAN = 0.30;   // → [0.55, 0.85]
const SLACK_CAP = 3;

/** Signed distance from the threshold, in scale units. Positive = further in. */
function slackOf(atom, row, { scaleFor }) {
  const v = row[atom.signal];
  if (v === null || v === undefined || !Number.isFinite(v)) return null;
  const raw = (atom.op === '>' || atom.op === '>=') ? v - atom.value : atom.value - v;
  return raw / scaleFor(atom.signal, v);
}

/**
 * @param {object} predicate  validatePredicate-approved
 * @param {object} row        vocabulary-keyed day vector
 * @param {'UP'|'DOWN'} side  the leg that actually fired
 * @returns {number|null} 2dp confidence in [CONF_MIN, CONF_MIN+CONF_SPAN]
 */
function predicateConfidence(predicate, row, side) {
  const { scaleFor } = require('../config/signalVocabulary');
  const key = side === 'UP' ? 'up' : 'down';
  const leg = predicate[key];
  let m;
  if (leg && leg !== 'else') {
    // A conjunction is only as strong as its binding constraint.
    const slacks = leg.all.map(a => slackOf(a, row, { scaleFor }));
    if (slacks.some(s => s === null)) return null;
    m = Math.min(...slacks);
  } else if (leg === 'else') {
    // An "else" fires because the OPPOSITE conjunction is false. What governs
    // how close this is to flipping is the smallest perturbation that would
    // make that whole leg true — so the LARGEST shortfall among its failing
    // atoms, not the smallest. Flipping the narrowest failure is not enough
    // when two atoms failed.
    const other = predicate[key === 'up' ? 'down' : 'up'];
    if (!other || other === 'else') return null;
    const failing = other.all
      .map(a => slackOf(a, row, { scaleFor }))
      .filter(s => s !== null && s < 0)
      .map(s => -s);
    if (!failing.length) return null;
    m = Math.max(...failing);
  } else {
    return null;
  }
  const bounded = Math.max(0, Math.min(m, SLACK_CAP));
  return Math.round((CONF_MIN + CONF_SPAN * (1 - Math.exp(-bounded))) * 100) / 100;
}

/**
 * BV7X-201 — evaluate the granular half.
 *
 * DELIBERATELY A SECOND FUNCTION rather than a wider return from evalPredicate.
 * That function's contract ('UP'|'DOWN'|null|'SKIP'|'CONFLICT') has three
 * service consumers and three test files, and KI #103 is precisely the cost of
 * widening a discriminator underneath consumers that read it as narrower. This
 * one composes with it instead: same direction, same abstentions, plus a number.
 *
 * @param {object} predicate  - validatePredicate-approved
 * @param {object} row        - day vector keyed by the signal vocabulary
 * @param {number} entryPrice - price at submission (predictions.entry_price)
 * @returns {{direction, movePct, target}|{direction}|'SKIP'|'CONFLICT'|null|{refused}}
 *   - null / 'SKIP' / 'CONFLICT' pass straight through from evalPredicate
 *   - {direction} with no movePct: the leg fired but declares no target
 *     (a direction-only agent — still valid, still the majority today)
 *   - {refused} : a target existed and could not be honoured. NEVER a silent
 *     fallback to a direction-only call, because the whole point of the
 *     dependency is that the two agree.
 */
function evalTarget(predicate, row, entryPrice) {
  const direction = evalPredicate(predicate, row);
  if (direction === null || direction === 'SKIP' || direction === 'CONFLICT') return direction;

  const target = predicate.targets ? predicate.targets[direction.toLowerCase()] : null;
  if (!target) return { direction };

  if (!Number.isFinite(entryPrice) || entryPrice <= 0) {
    return { direction, refused: 'entry_price_unusable' };
  }

  let movePct = target.pct;
  if (target.scale) {
    const v = row[target.scale.signal];
    // A null scaling signal is NOT a zero contribution — that would silently
    // demote a condition-scaled forecast to its constant, which is a different
    // prediction wearing the same agent's name. Same family as evalLeg's SKIP.
    if (v === null || v === undefined || !Number.isFinite(v)) return 'SKIP';
    movePct += target.scale.k * v;
  }

  // The operator's dependency, enforced where it can actually break: a scaled
  // move can cross zero on a given row even though `pct` passed the static
  // sign check at validation. Refuse — a call whose number says one thing and
  // whose direction says another is worse than no call.
  const signOk = direction === 'UP' ? movePct > 0 : movePct < 0;
  if (!signOk) return { direction, refused: 'target_sign_contradicts_direction' };
  if (Math.abs(movePct) > MAX_ABS_MOVE_PCT) return { direction, refused: 'target_out_of_bounds' };

  return { direction, movePct, target: entryPrice * (1 + movePct / 100) };
}

/**
 * Direction DERIVED from a granular target, for the submission path — the
 * operator's rule stated as code: up/down is dependent on the granular call.
 * Equality is not a direction (see validateTarget's zero note): it abstains.
 */
function directionFromTarget(targetPrice, entryPrice) {
  if (!Number.isFinite(targetPrice) || !Number.isFinite(entryPrice) || entryPrice <= 0) return null;
  if (targetPrice > entryPrice) return 'UP';
  if (targetPrice < entryPrice) return 'DOWN';
  return null;
}

module.exports = {
  validatePredicate, evalPredicate, signalsOf, predicateConfidence, predicateShape, deployWarnings,
  evalTarget, directionFromTarget,
  _internal: { OPS, MAX_ATOMS_PER_LEG, MAX_ABS_MOVE_PCT, evalLeg, validateTarget, slackOf, CONF_MIN, CONF_SPAN, SLACK_CAP },
};
