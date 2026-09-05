/* QUORUM — the field, drawn from the night's own decision records.
 *
 * The lattice math is PORTED, not invented: fibonacciLattice, depthOpacity and
 * depthRadius come from polypool/web/src/hologram/sphere.ts, where they are
 * pure functions with vitest coverage and no React coupling. Same distribution,
 * same depth falloff, so the field here and the swarm on app.bv7x.ai are the
 * same object seen twice.
 *
 * One node per call. Lit = its rule fired (evidenced). Shadow = it defaulted
 * through an else leg. With memory off we cannot tell the two apart, so every
 * node is lit — which is precisely the credulity a naive vote encodes, drawn
 * rather than argued.
 */
'use strict';

const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));
const MAX_NODES = 6000;          // beyond this we sample, and we say so

function fibonacciLattice(n, x, y, z) {
  for (let i = 0; i < n; i++) {
    const yi = n === 1 ? 0 : 1 - (i / (n - 1)) * 2;
    const r = Math.sqrt(Math.max(0, 1 - yi * yi));
    const theta = GOLDEN_ANGLE * i;
    x[i] = Math.cos(theta) * r;  y[i] = yi;  z[i] = Math.sin(theta) * r;
  }
}
const depthOpacity = d => 0.15 + (d * d * (3 - 2 * d)) * 0.85;   // smoothstep
const depthRadius  = d => 0.75 + d * 0.25;

/* BRAND §3.2 / §14: the Field reads as a ramp, lit -> shadow along the
 * upper-right -> lower-left axis. Depth alone ramps toward the viewer, which is
 * the wrong axis, so a node's own position on the sphere carries a directional
 * term as well. A node IS its own normal on a unit sphere, so this is one dot
 * product against a fixed light sitting upper-right and slightly forward. */
const LX = 0.62, LY = 0.52, LZ = 0.59;
const lambert = (x, y, z) => 0.34 + 0.66 * Math.max(0, (x * LX + y * LY + z * LZ) * 0.5 + 0.5);

const $ = id => document.getElementById(id);
const pct = v => (v == null ? '—' : (v * 100).toFixed(1) + '%');
const num = v => (v == null ? '—' : v.toLocaleString());

/* ── lattice ─────────────────────────────────────────────────────────── */
const cv = $('field'), ctx = cv.getContext('2d');
let nodes = [], X, Y, Z, angle = 0, raf = 0, sampled = 0;

function setNodes(bits) {
  const all = (bits || '').split('');
  sampled = 0;
  if (all.length > MAX_NODES) {                     // even sample, never the first N
    const step = all.length / MAX_NODES, out = [];
    for (let i = 0; i < MAX_NODES; i++) out.push(all[Math.floor(i * step)]);
    sampled = all.length;
    nodes = out;
  } else {
    nodes = all;
  }
  const n = nodes.length;
  X = new Float32Array(n); Y = new Float32Array(n); Z = new Float32Array(n);
  fibonacciLattice(n, X, Y, Z);
}

function resize() {
  const dpr = window.devicePixelRatio || 1;
  cv.width = Math.round(cv.clientWidth * dpr);
  cv.height = Math.round(cv.clientHeight * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function draw() {
  const w = cv.clientWidth, h = cv.clientHeight;
  ctx.clearRect(0, 0, w, h);
  if (!nodes.length) { raf = requestAnimationFrame(draw); return; }

  const cx = w / 2, cy = h / 2, R = Math.min(w, h) * 0.40;
  const ca = Math.cos(angle), sa = Math.sin(angle);
  const order = [];
  for (let i = 0; i < nodes.length; i++) {
    const xr = X[i] * ca - Z[i] * sa;
    const zr = X[i] * sa + Z[i] * ca;
    order.push([zr, cx + xr * R, cy - Y[i] * R, (zr + 1) * 0.5, nodes[i] === '1',
                lambert(xr, Y[i], zr)]);
  }
  order.sort((a, b) => a[0] - b[0]);                // painter's algorithm: back to front

  for (const [, sx, sy, d, lit, lam] of order) {
    const a = depthOpacity(d) * lam, r = depthRadius(d) * (lit ? 2.0 : 1.5);
    if (lit) {
      ctx.beginPath(); ctx.arc(sx, sy, r * 2.6, 0, 6.2832);
      ctx.fillStyle = `rgba(79,192,255,${a * 0.13})`; ctx.fill();      // --sky bloom
      ctx.beginPath(); ctx.arc(sx, sy, r, 0, 6.2832);
      ctx.fillStyle = `rgba(191,239,255,${a})`; ctx.fill();            // --ice
    } else {
      ctx.beginPath(); ctx.arc(sx, sy, r, 0, 6.2832);
      ctx.fillStyle = `rgba(46,19,84,${a * 0.85})`; ctx.fill();        // --violet-shadow
    }
  }
  angle += 0.0016;
  raf = requestAnimationFrame(draw);
}

/* ── render ──────────────────────────────────────────────────────────── */
function renderWhy(d) {
  const el = $('why'), note = $('why-note');
  el.innerHTML = '';
  if (!d.why || !d.why.length) {
    note.textContent = '';
    el.innerHTML = `<div class="cannot-say">
        <div class="big">CANNOT SAY</div>
        <div class="why-not">${d.why_note || 'Nothing to attribute.'}<br><br>
          The published direction survives without memory. The reason behind it does not —
          it is a join of rule and snapshot, and both live in the store.</div>
      </div>`;
    return;
  }
  const max = Math.max(...d.why.map(w => w.deciding));
  for (const w of d.why) {
    const row = document.createElement('div');
    row.className = 'why-row';
    row.innerHTML = `<span class="why-sig"></span><span class="why-n"></span>
                     <span class="bar"><i style="width:${(100 * w.deciding / max).toFixed(1)}%"></i></span>`;
    row.querySelector('.why-sig').textContent = w.signal;
    row.querySelector('.why-n').textContent = num(w.deciding);
    el.appendChild(row);
  }
  note.textContent = `Signals that decided tonight, counted over deciding atoms. `
    + `${num(d.counts.default)} calls had no reason fire — they defaulted through an else leg.`;
}

function renderBelief(d) {
  const b = d.belief, el = $('belief');
  // §3.3: gold only when the interval actually supports a lean.
  const live = b.ci && b.verdict !== 'no lean';
  el.innerHTML = `
    <dl>
      <dt>calls</dt><dd>${num(d.counts.calls)}</dd>
      ${d.counts.evidenced == null ? '' :
        `<dt>evidenced</dt><dd>${num(d.counts.evidenced)} (${pct(d.evidenced_share)})</dd>
         <dt>defaulted</dt><dd>${num(d.counts.default)}</dd>`}
    </dl>
    <hr>
    <div class="rate">${b.rate_withheld ? 'n = ' + num(b.n) : pct(b.up_share) + ' UP'}</div>
    <div class="ci">${b.ci ? `95% CI [${(b.ci[0]*100).toFixed(1)}, ${(b.ci[1]*100).toFixed(1)}] · ${d.belief_label}`
                           : d.belief_label}</div>
    ${b.rate_withheld ? `<p class="withheld">Rate withheld: ${b.withheld_reason}. Counts are printed;
       a percentage at this n would be a claim the sample cannot support.</p>` : ''}
    <div class="verdict ${live ? 'live' : 'quiet'}">
      <div class="label">verdict</div>
      <div class="value">${b.rate_withheld ? 'CANNOT SAY' : b.verdict.toUpperCase()}</div>
    </div>`;
}

function renderHistory(d) {
  const el = $('history'), h = d.history;
  const pp = v => (v == null ? '—' : (v * 100).toFixed(1) + '%');
  if (!h || h.status !== 'ok') {
    const shallow = h && h.prior_nights != null;
    el.innerHTML = `<div class="cannot-say">
        <div class="big">CANNOT SAY</div>
        <div class="why-not">${(h && h.reason) || 'no history'}${shallow ? `<br><br>
          An engagement class is a property of a rule's <em>history</em>, classified from the nights
          before tonight. Memory is ${h.prior_nights} night${h.prior_nights === 1 ? '' : 's'} deep here.
          It deepens nightly — on 2026-09-01 the same fleet classifies.` : `<br><br>
          Without the store there is no history, so a constant-output agent and a responsive one look
          identical — every vote weighs the same, and the naive interval is all that can be said.`}</div>
      </div>`;
    return;
  }
  // both intervals on one 0–100% axis
  const seg = (ci, cls, lab) => {
    const l = ci[0] * 100, w = (ci[1] - ci[0]) * 100;
    return `<div class="ivl ${cls}" style="left:${l.toFixed(2)}%;width:${w.toFixed(2)}%"><span class="ivl-lab">${lab}</span></div>`;
  };
  const c = h.classes || {};
  const cell = (k, label, note) => {
    const g = c[k]; if (!g) return '';
    return `<div class="cls ${k === 'switching' ? 'switching' : 'constant'}">
      <div class="k">${label}</div>
      <div class="v">${num(g.n)}</div>
      <div class="d">${note}${g.rate_withheld ? '' : ` · ${pp(g.up_share)} UP`}</div></div>`;
  };
  el.innerHTML = `
    <div class="ivl-wrap"><div class="ivl-axis"><div class="ivl-mid"></div>
      ${seg(h.naive.ci, 'naive', `naive · n=${num(h.naive.n)}`)}
      ${seg(h.responsive.ci, 'resp', `responsive · n=${num(h.responsive.n)}`)}
    </div></div>
    <div class="classes">
      ${cell('never', 'never fired', 'condition never held — called through the else leg every prior night')}
      ${cell('always', 'always fired', 'condition always held — one direction every prior night')}
      ${cell('switching', 'switched', 'has called both ways — the only agents responding to the market')}
    </div>
    <p class="verdict-line"><b>The naive interval is ${h.precision_ratio}× too narrow.</b>
      Naive: ${pp(h.naive.up_share)} UP, CI [${pp(h.naive.ci[0])}, ${pp(h.naive.ci[1])}] over ${num(h.naive.n)} calls.
      Responsive: ${pp(h.responsive.up_share)} UP, CI [${pp(h.responsive.ci[0])}, ${pp(h.responsive.ci[1])}] over ${num(h.responsive.n)}.
      ${Math.round(h.constant_share * 100)}% of the classified fleet has not changed its call in ${h.prior_nights} nights —
      deploy-time composition counted as if it were tonight's opinion. Precision manufactured by counting
      agents that cannot move. This is a claim about stated uncertainty, not about which direction is right.
      <br><br>
      Classified from ${h.prior_nights} prior nights; ${num(h.unclassified)} callers are too new to classify and are
      counted in the naive figure only. Recomputed from ${num(h.nights_in_memory)} nights of records in ${h.elapsed_ms} ms.</p>
    <div class="depth"><span>memory depth</span><span class="bar"><i style="width:${Math.min(100, 100 * h.prior_nights / 20).toFixed(0)}%"></i></span><span>${h.prior_nights} nights</span></div>`;
}

function renderCohorts(d) {
  const el = $('cohorts'), c = d.cohorts;
  if (!c || c.status) {
    el.innerHTML = `<div class="cannot-say">
        <div class="big">CANNOT SAY</div>
        <div class="why-not">${(c && c.reason) || 'no cohort data'}<br><br>
          Without memory you can count the votes. You cannot know how many of them
          were the same vote — so the question below cannot even be asked, let alone
          answered.</div>
      </div>`;
    return;
  }
  const pp = v => (v == null ? '—' : (v > 0 ? '+' : '') + v.toFixed(2) + 'pp');
  const rows = c.largest.map(g => `
      <tr>
        <td class="sig">${g.signals.join(' · ')}</td>
        <td class="num">${num(g.n)}</td>
        <td class="num">${g.lean}</td>
        <td class="num">${g.withheld ? 'n&lt;30' : (g.agreement * 100).toFixed(1) + '%'}</td>
        <td class="num">${g.withheld ? '—' : (g.expected * 100).toFixed(1) + '%'}</td>
        <td class="num">${g.withheld ? '—' : pp(g.excess_pp)}</td>
      </tr>`).join('');

  el.innerHTML = `
    <div class="claim-grid">
      <div class="claim">
        <div class="k">the field</div>
        <div class="v">${num(c.calls)} calls</div>
        <div class="d">across ${num(c.configurations)} distinct signal-configurations${
          c.unplaced ? ` · ${num(c.unplaced)} unplaced` : ''}.</div>
      </div>
      <div class="claim refuted">
        <div class="k">the claim, if a configuration were an opinion</div>
        <div class="v">${c.n_eff_if_clustered} opinions</div>
        <div class="d">Kish effective sample size — a ${c.collapse_if_clustered}x collapse. It assumes
          agents inside a cohort agree. They do not.</div>
      </div>
      <div class="claim result">
        <div class="k">the test, over ${num(c.tested_cohorts)} cohorts at n&ge;30</div>
        <div class="v">${pp(c.excess_pp)}</div>
        <div class="d">agreement above what ${num(c.tested_cohorts)} groups of INDEPENDENT agents would
          reach by chance at the field's own ${(c.up_rate * 100).toFixed(1)}% UP rate.</div>
      </div>
    </div>

    <table class="cohort-table">
      <thead><tr>
        <th>largest cohorts</th><th class="num">n</th><th class="num">lean</th>
        <th class="num">agree</th><th class="num">if independent</th><th class="num">excess</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>

    <p class="verdict-line"><b>${c.verdict === 'cohorts cluster' ? 'Cohorts cluster.'
        : 'Indistinguishable from independent.'}</b>
      Observed ${(c.observed_agreement * 100).toFixed(2)}% against
      ${(c.expected_if_independent * 100).toFixed(2)}% expected by chance. Agents that read the same
      signals are no more alike than strangers — because a configuration fixes WHICH signals a rule
      reads, not the thresholds it reads them at. The obvious collapse is not there.
      <br><br>
      Every number in this panel is recoverable only from memory: a configuration is a property of the
      rule, and the rule is in the store. What memory bought here is not a better answer — it is the
      ability to ask the question, and to have it come back no.</p>`;
}

function renderCannotSay(d) {
  const failed = d.status === 'FAILED';
  $('why').innerHTML = ''; $('why-note').textContent = '';
  $('field-count').textContent = ''; $('field-note').textContent = '';
  renderHistory({ history: { status: d.status, reason: d.reason } });
  renderCohorts({ cohorts: { status: d.status, reason: d.reason } });
  setNodes('');
  $('belief').innerHTML = `<div class="cannot-say ${failed ? 'failed' : ''}">
      <div class="big">${failed ? 'FAILED' : 'CANNOT SAY'}</div>
      <div class="why-not">${d.reason || 'no answer available'}${failed ? '' :
        '<br><br>This is the deletion gate working, not the page breaking. Without the memory layer there is no basis to report, and a number here would be invented.'}</div>
    </div>`;
}

/* ── data ────────────────────────────────────────────────────────────── */
let memoryOn = true;

async function load() {
  const night = $('night').value;
  $('stamp').innerHTML = '<b>computing…</b>';
  let d;
  try {
    const res = await fetch(`/api/field?night=${encodeURIComponent(night)}&memory=${memoryOn ? 'on' : 'off'}`,
                            { cache: 'no-store' });
    d = await res.json();
  } catch (e) {
    d = { status: 'FAILED', reason: String(e) };    // never zeros
  }

  if (d.status !== 'ok') { renderCannotSay(d); $('stamp').innerHTML = `<b>${d.status || 'FAILED'}</b>`; return; }

  renderWhy(d);
  renderBelief(d);
  renderHistory(d);
  renderCohorts(d);
  setNodes(d.nodes);
  const shown = sampled ? `showing 6,000 of ${num(sampled)} calls (evenly sampled)`
                        : `${num(nodes.length)} calls`;
  $('field-count').textContent = shown;
  $('legend-shadow').hidden = !memoryOn;
  $('legend-lit').innerHTML = memoryOn
    ? '<i class="dot lit"></i><b>lit</b> — its rule fired'
    : '<i class="dot lit"></i><b>every node lit</b> — nothing distinguishes them';
  // The two modes count different populations, and that is the honest asymmetry:
  // memory reconstructs each rule's own direction, while the naive vote can only
  // count the directions the arena published. Say so rather than let it read as a bug.
  $('field-note').textContent = memoryOn
    ? `${num(d.counts.calls)} rules resolved to a direction tonight.`
    : `${num(d.counts.calls)} published directions — fewer than the ${'\u2248'}1.9k rules memory can`
      + ` reconstruct, because without the store only what was published survives.`;
  $('stamp').innerHTML = `<b>${d.computed_at}</b> · computed in ${d.elapsed_ms} ms · `
    + (memoryOn ? 'from memory' : 'store not opened');
}

function setSwitch(on) {
  memoryOn = on;
  const sw = $('switch');
  sw.setAttribute('aria-pressed', String(on));
  $('switch-label').textContent = `Sibyl memory · ${on ? 'on' : 'off'}`;
  $('switch-hint').textContent = on
    ? 'Only calls whose stated condition actually held count toward the belief.'
    : 'Every call counts the same — the shadowed nodes light up as if they were evidence, because without memory nothing distinguishes them.';
  load();
}

(async function boot() {
  const sel = $('night');
  try {
    const { nights, default: def } = await (await fetch('/api/nights')).json();
    for (const n of nights) {
      const o = document.createElement('option');
      o.value = o.textContent = n;
      if (n === def) o.selected = true;
      sel.appendChild(o);
    }
  } catch (e) { /* selector stays empty; load() will render FAILED */ }

  sel.addEventListener('change', load);
  $('switch').addEventListener('click', () => setSwitch(!memoryOn));
  window.addEventListener('resize', resize);
  resize(); draw();
  setSwitch(true);
})();
