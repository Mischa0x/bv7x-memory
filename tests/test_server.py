"""The screen's server — and the deletion gate as a visitor exercises it.

The gate is already tested at the record layer (test_record.Gate). This file
tests the thing a JUDGE actually touches: the HTTP endpoint. Three properties
have to hold or the page is a claim rather than a demonstration.

  1. memory=off NEVER OPENS THE STORE. Asserted by pointing the handler at a
     path that does not exist and requiring a full, correct answer anyway.
  2. memory=on WITHOUT A STORE IS 'CANNOT SAY' — not an exception, not zeros,
     not a default. That is the gate, served over HTTP.
  3. The two modes DISAGREE on a real night. If they ever agree, the memory is
     decoration and the entry fails its own criterion.

Everything except (3) runs on the stdlib; (3) needs the real client to build a
store, and skips without it, matching test_record's convention.
"""
import json, os, tempfile, threading, unittest, urllib.request
from http.server import ThreadingHTTPServer

from quorum.record import CANNOT_SAY
from quorum.server import Handler, field_off, field_on

FX = os.path.join(os.path.dirname(__file__), 'fixtures')
with open(os.path.join(FX, 'rows.json')) as f:
    DOC = json.load(f)
NIGHT = '2026-08-27'
NO_STORE = '/nonexistent/quorum-does-not-exist.db'


class _Server:
    """A real server on an ephemeral port, for the duration of one test."""
    def __init__(self, store):
        Handler.store = store
        Handler.log_message = lambda *a, **k: None   # keep CI output to the test results
        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.port = self.srv.server_address[1]
        self.t = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.t.start()

    def get(self, path):
        with urllib.request.urlopen(f'http://127.0.0.1:{self.port}{path}', timeout=30) as r:
            return r.status, r.read()

    def json(self, path):
        return json.loads(self.get(path)[1])

    def close(self):
        self.srv.shutdown(); self.srv.server_close(); self.t.join(timeout=5)


class Naive(unittest.TestCase):
    def test_off_needs_no_store(self):
        """Property 1, at the function level: the naive vote is computed with a
        store path that does not exist, and is still complete and correct."""
        d = field_off(NIGHT)
        self.assertEqual(d['status'], 'ok')
        self.assertEqual(d['counts']['calls'], 715)
        self.assertAlmostEqual(d['belief']['up_share'], 388 / 715, places=6)
        self.assertEqual(d['belief']['verdict'], 'UP')
        self.assertEqual(d['warrant'], CANNOT_SAY)

    def test_off_lights_every_node(self):
        """Without memory nothing separates evidenced from defaulted, so the
        lattice must show that rather than imply a distinction it cannot make."""
        d = field_off(NIGHT)
        self.assertEqual(set(d['nodes']), {'1'})
        self.assertEqual(len(d['nodes']), d['counts']['calls'])

    def test_off_attributes_nothing(self):
        self.assertEqual(field_off(NIGHT)['why'], [])


class AbsentStore(unittest.TestCase):
    def test_on_without_store_is_cannot_say(self):
        """Property 2 — the gate. Never an exception, never a zero."""
        d = field_on(NIGHT, NO_STORE)
        self.assertEqual(d['status'], CANNOT_SAY)
        self.assertIn('no memory store', d['reason'])
        self.assertNotIn('belief', d)


class Http(unittest.TestCase):
    """The wire, with the memory layer absent — the judge's first click."""
    @classmethod
    def setUpClass(cls):
        cls.s = _Server(NO_STORE)

    @classmethod
    def tearDownClass(cls):
        cls.s.close()

    def test_page_serves_without_memory(self):
        status, body = self.s.get('/')
        self.assertEqual(status, 200)
        self.assertIn(b'Quorum', body)

    def test_nights_endpoint(self):
        d = self.s.json('/api/nights')
        self.assertIn(NIGHT, d['nights'])

    def test_off_over_http(self):
        d = self.s.json(f'/api/field?night={NIGHT}&memory=off')
        self.assertEqual(d['status'], 'ok')
        self.assertEqual(d['counts']['calls'], 715)
        self.assertIn('elapsed_ms', d)          # computed per request, not cached

    def test_on_over_http_is_cannot_say(self):
        d = self.s.json(f'/api/field?night={NIGHT}&memory=on')
        self.assertEqual(d['status'], CANNOT_SAY)

    def test_unknown_path_404s(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.s.get('/nope.js')
        self.assertEqual(e.exception.code, 404)


class HttpGate(unittest.TestCase):
    """Property 3: over the wire, the two modes must materially disagree."""
    def test_gate_over_http(self):
        try:
            import sibyl_memory_client  # noqa: F401
        except ImportError:
            self.skipTest('sibyl_memory_client not installed')
        from quorum.record import QuorumMemory
        d = tempfile.mkdtemp()
        store = os.path.join(d, 'q.db')
        QuorumMemory.open(store).ingest(DOC['predicates'], DOC['snapshots'], DOC['rows'])

        s = _Server(store)
        try:
            on = s.json(f'/api/field?night={NIGHT}&memory=on')
            off = s.json(f'/api/field?night={NIGHT}&memory=off')
        finally:
            s.close()

        self.assertEqual(on['status'], 'ok')
        self.assertEqual(on['counts']['evidenced'], 588)
        # The finding: warranted belief sits below the line, the naive vote above it.
        self.assertLess(on['belief']['up_share'], 0.5)
        self.assertGreater(off['belief']['up_share'], 0.5)
        self.assertNotEqual(on['belief']['verdict'], off['belief']['verdict'])
        self.assertGreater(abs(on['belief']['up_share'] - off['belief']['up_share']), 0.01)
        # And the lattice must actually carry shadow when memory is on.
        self.assertIn('0', on['nodes'])

    def test_night_absent_from_memory_is_cannot_say(self):
        try:
            import sibyl_memory_client  # noqa: F401
        except ImportError:
            self.skipTest('sibyl_memory_client not installed')
        from quorum.record import QuorumMemory
        d = tempfile.mkdtemp()
        store = os.path.join(d, 'q.db')
        QuorumMemory.open(store).ingest(DOC['predicates'], DOC['snapshots'], DOC['rows'])
        self.assertEqual(field_on('1999-01-01', store)['status'], CANNOT_SAY)


if __name__ == '__main__':
    unittest.main()
