#!/usr/bin/env node
/**
 * Run the VENDORED production evaluator over the frozen live rows and write
 * tests/fixtures/expected.json — the oracle tests/test_parity.py checks against.
 *
 * Verdict encoding: evalPredicate returns 'UP' | 'DOWN' | null | 'SKIP' | 'CONFLICT'.
 * JSON has no null-vs-absent distinction worth trusting across two languages, so
 * null (an abstention) is written as the string "NULL". A thrown error is recorded
 * as "ERR:<message>" rather than dropped, because a row the oracle cannot judge is
 * a finding, not a gap.
 *
 * CI runs this and then `git diff --exit-code` on the fixture: if the vendored JS
 * and the committed expectations ever disagree, the build is red before Python is
 * even consulted.
 */
const fs = require('fs');
const path = require('path');
const { evalPredicate } = require('./vendor/services/predicateEval.js');

const fx = path.join(__dirname, 'fixtures');
const doc = JSON.parse(fs.readFileSync(path.join(fx, 'rows.json'), 'utf8'));
const tally = {};
const expected = doc.rows.map(([pi, si]) => {
  let v;
  try { v = evalPredicate(doc.predicates[pi], doc.snapshots[si]); }
  catch (e) { v = 'ERR:' + e.message; }
  const enc = v === null ? 'NULL' : v;
  tally[enc] = (tally[enc] || 0) + 1;
  return enc;
});
fs.writeFileSync(path.join(fx, 'expected.json'),
  JSON.stringify({ oracle: 'tests/vendor/services/predicateEval.js', rows: expected.length, tally, expected }));
console.log(`production evalPredicate over ${expected.length} rows:`, JSON.stringify(tally));
