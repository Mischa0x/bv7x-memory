/**
 * The 17-signal vocabulary — THE contract between the strategy compiler, the
 * bitvault interpreter's market snapshot, and the mechanical backtester
 * (3RDI-036 / BV7X-036). One module, three consumers, so they can never drift apart
 * silently — KI #51 is what drift costs: a rule naming a field the snapshot
 * doesn't carry is a permanently-inert agent that looks selective.
 *
 * CANONICAL-COPY (3RDI-118 / BV7X-147): byte-identical in both forks, listed
 * in CORE-MANIFEST.json; fork-specific values come only from constants.IDENTITY.
 * Edit via the scripts/core-sync.js discipline so both trees move together.
 *
 * Order matters: the compiler system prompt renders this list verbatim.
 */
const SIGNALS = [
  'price', 'rsi14', 'fearGreed', 'roc7d', 'drawdown30d', 'ma50', 'ma200',
  'distanceFromMA200', 'distanceFromMA50', 'etfFlows7d', 'dxy', 'vix',
  'sp500', 'treasury10y', 'yieldSpread', 'binanceSmartMoney', 'binanceHype',
];

// No historical series exists for these (live-only scores, ~2.5 months of
// constant values on disk) — a predicate touching them is honest
// "not backtestable", never a fabricated number.
const NO_HISTORY = new Set(['binanceSmartMoney', 'binanceHype']);

/**
 * SCALE — "one meaningful step" for each signal, used to turn the distance
 * between an observed value and a rule's threshold into a comparable number
 * (see predicateEval.predicateConfidence).
 *
 * DERIVED, not invented: the median absolute 1-day change over the panel
 * (5,663 rows, 2011-02-01 → 2026-08-03), measured 2026-08-04. Pinned as
 * literals on purpose — a scale computed at runtime from a rolling panel would
 * make confidence a function of when you asked, which is the determinism bug
 * this whole lane exists to remove. Re-derive deliberately, never automatically.
 *
 *   etfFlows7d is measured over the ETF era only (>= 2024-01-11, 936 rows):
 *   across the full panel it reads 0.00 because everything before the gate is
 *   zero-padded, and a zero scale would make every ETF atom infinitely
 *   confident. Exactly the KI #51 class of silent error.
 */
const SCALE = {
  rsi14: 2.38, fearGreed: 3.0, roc7d: 2.42, drawdown30d: 1.13,
  distanceFromMA200: 1.71, distanceFromMA50: 1.56,
  etfFlows7d: 134, dxy: 0.0967, vix: 0.32,
  treasury10y: 0.02, yieldSpread: 0.01,
  // CHOSEN, not derived — these two carry no history to measure (NO_HISTORY).
  // 0-100 scores, so a 5-point step is the same order as fearGreed's.
  binanceSmartMoney: 5.0, binanceHype: 5.0,
};

/**
 * Level signals have no meaningful fixed step: a $69 median move is one thing
 * at $200 BTC and another at $60,000. Their scale is a fraction of the observed
 * value instead — still a pure function of the row, so still deterministic.
 * Fractions are the same panel measurement, expressed relative to level.
 */
const SCALE_RELATIVE = { price: 0.0153, ma50: 0.00398, ma200: 0.00247, sp500: 0.00218 };

/** One meaningful step for `signal` given the observed value. Never 0. */
function scaleFor(signal, observed) {
  if (SCALE_RELATIVE[signal] !== undefined) {
    return Math.max(Math.abs(observed) * SCALE_RELATIVE[signal], 1e-9);
  }
  return SCALE[signal] !== undefined ? SCALE[signal] : 1;
}

module.exports = {
  SIGNALS, VALID_SIGNALS: new Set(SIGNALS), NO_HISTORY,
  SCALE, SCALE_RELATIVE, scaleFor,
};
