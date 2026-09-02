# Vendored production code — parity oracle, not product

These two files are **byte-identical copies** from `mefuru/polypool` at commit
`4d311d5a5ac978af9d191b503b9efab3f500b9d4` (`4d311d5`), taken 2026-09-02:

| file | upstream path | git blob |
|---|---|---|
| `services/predicateEval.js` | `agents/services/predicateEval.js` | `d58f1f6efafe16aa2e78b9edd519d2d68fa780b5` |
| `config/signalVocabulary.js` | `agents/config/signalVocabulary.js` | `654f5fb6a17ac9b98dc86dd28054b41871ea32f9` |

They exist for ONE reason: the Python evaluator in `quorum/why.py` is a port of
`evalPredicate`, and a port that is not tested against its source is a
reimplementation with extra steps. `tests/regen_expected.js` runs THIS copy over the
frozen live rows to produce `tests/fixtures/expected.json`; `tests/test_parity.py`
asserts the Python side matches it on every row.

**Not product.** The entry is stdlib Python and runs without node. These files are a
test oracle. Do not import them from `quorum/`.

**Refresh discipline.** Upstream is CANONICAL-COPY under polypool's core-sync
(3RDI-118 / BV7X-147); if it changes, re-copy, update the blob hashes above, regenerate
`expected.json`, and re-run parity. A silent drift between this copy and upstream is
exactly the failure the hashes are here to make visible — check them with
`git hash-object` against the upstream path, not by eye.
