"""``python -m quorum serve`` — the field explains itself, over the stdlib only.

MEMORY IS ON THE CRITICAL PATH, AND THAT IS THE POINT. Every request to
``/api/field`` recomputes the answer: with ``memory=on`` it opens the store,
reads the decision records for the night and re-derives each call's basis from
(rule × snapshot) through ``why()``. Nothing is cached and no answer is baked
into the page. Delete the store and the endpoint returns CANNOT SAY — which is
the deletion gate, enforced by the same code path a visitor exercises.

``memory=off`` is constructed WITHOUT OPENING THE STORE, deliberately. The naive
vote counts the directions the arena publishes anyway, so it must be reachable
with the memory layer deleted — otherwise the comparison would be a claim rather
than a demonstration.

The honesty gates are the same four the rest of the tool applies:
  * no rate below n=30 — the interval is withheld and the UI says so;
  * CANNOT SAY is a render state, never an error and never zeros;
  * an open call's direction is never served (nights are settled history here);
  * the evidenced split is a claim about WARRANT, never about being right.
"""
import json, os, time
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from .record import QuorumMemory, DEFAULT_STORE, CANNOT_SAY, MIN_N, wilson, decode_rule
from ._gate import _verdict
from .cohorts import cohort_stats
from .why import signals_of

HERE     = os.path.dirname(os.path.abspath(__file__))
STATIC   = os.path.join(HERE, 'static')
FIXTURES = os.path.join(HERE, os.pardir, 'tests', 'fixtures', 'rows.json')
TYPES    = {'.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8',
            '.js': 'application/javascript; charset=utf-8', '.svg': 'image/svg+xml'}


def _fixture():
    with open(FIXTURES) as fh:
        return json.load(fh)


def _share(n, k):
    """A rate, an interval and a verdict — with n always travelling beside them."""
    ci = wilson(k, n) if n >= MIN_N else None
    return {'n': n, 'up': k, 'up_share': (k / n) if n else None, 'ci': ci,
            'verdict': _verdict(ci), 'rate_withheld': n < MIN_N,
            'withheld_reason': (f'n = {n}, below the n>={MIN_N} floor') if n < MIN_N else None}


def field_off(night):
    """The naive vote. No store is opened — this survives the memory layer's deletion."""
    rows = [r for r in _fixture()['rows'] if r[2] == night]
    dirs = [r[3] for r in rows if r[3] in ('UP', 'DOWN')]
    k = sum(1 for d in dirs if d == 'UP')
    return {'night': night, 'memory': False, 'status': 'ok',
            'counts': {'rows': len(rows), 'calls': len(dirs),
                       'evidenced': None, 'default': None},
            'why': [], 'why_note': 'no memory: which facts fired is not recoverable',
            # Without memory every call weighs the same, so every node is lit —
            # the screen shows exactly the credulity the naive count encodes.
            'nodes': '1' * len(dirs),
            'belief': _share(len(dirs), k),
            'belief_label': 'naive vote (no memory)',
            # A configuration is a property of the RULE, and the rule lives in
            # the store. Without it you can count votes but cannot know how many
            # of them were the same vote.
            'cohorts': {'status': CANNOT_SAY,
                        'reason': 'a configuration is a property of the rule, and the rule is in the store'},
            'warrant': CANNOT_SAY}


def field_on(night, store):
    """The warranted belief, recomputed from records on every request."""
    if not os.path.exists(store):
        return {'night': night, 'memory': True, 'status': CANNOT_SAY,
                'reason': f'no memory store at {store}'}
    mem = QuorumMemory.open(store)
    recs = mem.records(night)
    if recs is None:
        return {'night': night, 'memory': True, 'status': CANNOT_SAY,
                'reason': 'night not in memory'}

    calls = [r for r in recs if r['direction'] in ('UP', 'DOWN')]
    ev    = [r for r in calls if r['basis'] == 'evidenced']
    de    = [r for r in calls if r['basis'] == 'default']

    # WHY: which signals actually decided tonight, counted over deciding atoms.
    # `held` is the fact that fired; a default call's deciding atom is one that
    # did NOT hold, and both are worth seeing.
    deciding, held = Counter(), Counter()
    for r in calls:
        for a in r['atoms']:
            deciding[a['signal']] += 1
            if a['held'] is True:
                held[a['signal']] += 1
    why = [{'signal': s, 'deciding': c, 'held': held.get(s, 0)}
           for s, c in deciding.most_common(8)]

    # Configurations come from the rules in memory - derived here, never stored,
    # so the number cannot drift from the records it describes.
    sig_by_rule = {}
    for rid, enc in mem._rules().items():
        try:
            sig_by_rule[rid] = signals_of(decode_rule(enc))
        except Exception:
            pass                      # an undecodable rule stays unplaced, and is counted as such

    return {'night': night, 'memory': True, 'status': 'ok',
            'cohorts': cohort_stats(recs, sig_by_rule) or {
                'status': CANNOT_SAY, 'reason': 'no calls in memory for this night'},
            'counts': {'rows': len(recs), 'calls': len(calls),
                       'evidenced': len(ev), 'default': len(de),
                       'no_call': len(recs) - len(calls)},
            'why': why,
            'why_note': None,
            'nodes': ''.join('1' if r['basis'] == 'evidenced' else '0' for r in calls),
            'belief': _share(len(ev), sum(1 for r in ev if r['direction'] == 'UP')),
            'belief_label': 'evidenced (warranted)',
            'all_calls': _share(len(calls), sum(1 for r in calls if r['direction'] == 'UP')),
            'evidenced_share': (len(ev) / len(calls)) if calls else None,
            'warrant': 'evidenced'}


class Handler(BaseHTTPRequestHandler):
    store = DEFAULT_STORE
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *a):    # one line per request, not two
        print(f'  {self.command} {self.path} → {a[1] if len(a) > 1 else ""}')

    def _send(self, code, body, ctype):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')   # the answer is computed per request
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj), 'application/json; charset=utf-8')

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)

        if u.path == '/api/nights':
            nights = sorted({r[2] for r in _fixture()['rows']})
            return self._json(200, {'nights': nights, 'default': '2026-08-27'})

        if u.path == '/api/field':
            night = (q.get('night') or ['2026-08-27'])[0]
            memory = (q.get('memory') or ['on'])[0] != 'off'
            t0 = time.perf_counter()
            try:
                out = field_on(night, self.store) if memory else field_off(night)
            except Exception as e:                      # never zeros, never a blank panel
                return self._json(500, {'night': night, 'memory': memory,
                                        'status': 'FAILED', 'reason': str(e)})
            out['elapsed_ms'] = round((time.perf_counter() - t0) * 1000, 1)
            out['computed_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            return self._json(200 if out.get('status') == 'ok' else 200, out)

        name = 'index.html' if u.path == '/' else os.path.basename(u.path)
        path = os.path.join(STATIC, name)
        if not os.path.isfile(path):
            return self._send(404, 'not found', 'text/plain; charset=utf-8')
        with open(path, 'rb') as fh:
            body = fh.read()
        return self._send(200, body, TYPES.get(os.path.splitext(name)[1], 'text/plain'))


def serve(port=8420, store=DEFAULT_STORE):
    Handler.store = store
    srv = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    print(f'quorum — http://127.0.0.1:{port}  (store: {store})')
    print('  memory is on the critical path: every /api/field?memory=on recomputes from records.')
    if not os.path.exists(store):
        print(f'  ⚠ no store at {store} — the field will render CANNOT SAY until you run: python -m quorum ingest')
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\nstopped')
    return 0
