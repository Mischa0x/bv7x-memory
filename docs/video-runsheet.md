# Quorum — video run-sheet

One unbroken take, 3½–4 minutes. Terminal for the first half, browser for the second, terminal again to close. Everything below was executed in this order on a clean clone on 2026-09-05 and completes in about two seconds of machine time — the video is narration, not waiting.

**Why one take matters:** criterion 4 is *cold-start recall on video, one unbroken take, with a timestamp or commit hash on screen.* The first command puts both on screen. Do not cut.

---

## Pre-flight (off camera, five minutes before)

```bash
# a genuinely fresh clone — cold start has to be real
rm -rf /tmp/quorum-take && git clone https://github.com/Mischa0x/bv7x-memory.git /tmp/quorum-take
cd /tmp/quorum-take
export QUORUM_STORE=/tmp/quorum-take/quorum.db      # a store path that visibly does not exist yet
export QUORUM_PY=~/.sibyl-venv/bin/python           # the Sibyl client lives here
ls quorum.db 2>/dev/null || echo "no store — good"
```

- Terminal: large font (18–20pt), dark theme, window ~120×32. Clear it.
- Browser: one tab ready but **empty** — you'll type `localhost:8420` on camera. Zoom to 125%.
- Second browser tab, already open, minimised: `https://base.easscan.org/attestation/view/0x30431e642678aa1d0442c8373139e47d763f67af85899809174e5621cc78cd50`
- Third tab, minimised: `https://basescan.org/tx/0x1d7a818a75f3d8402e88054443dd8761d05b4e621b9b0a6908abe5796ab059bc`
- Recording at 1080p or better; mic checked. Nothing else on the desktop.

---

## The take

### 0:00 — Stamp the take `[terminal]`

```bash
date -u && git rev-parse --short HEAD
```

> *This is a fresh clone of the entry, recorded in one take. That's the commit and the time.*

### 0:10 — Cold start `[terminal]`

```bash
$QUORUM_PY -m quorum field 2026-08-27
```

Expected: `"status": "CANNOT SAY", "reason": "no memory store at …"`

> *Quorum is a memory of why. Every night, five and a half thousand strategy agents look at the same Bitcoin market and each says UP or DOWN. The protocol has always kept the call. It has never kept the reason — which conditions the agent's rule was watching, what they read, whether they held. With no memory, ask the field what it believes and the only honest answer is: cannot say.*

### 0:40 — Ingest `[terminal]`

```bash
$QUORUM_PY -m quorum ingest --from tests/fixtures/rows.json
```

Expected: `{"ingested_nights": 21, "rows": 23106, "skipped_nights": 0}`

> *Twenty-one nights, twenty-three thousand calls. What goes into Sibyl is not a blob — it's the rule and the market snapshot, joined, so the reason for every call can be reconstructed on read. It fits in four megabytes.*

### 0:55 — With memory, and without `[terminal]`

```bash
$QUORUM_PY -m quorum field 2026-08-27 | head -20
$QUORUM_PY -m quorum field 2026-08-27 --memory off
```

Expected, with memory: evidenced `n: 588`, `up_share: 0.478`, CI `[0.438, 0.518]`.
Expected, without: `n: 715`, `up_share: 0.543`, CI `[0.506, 0.579]`.

> *Same night, two answers. With memory, count only the calls whose stated condition actually held — five hundred and eighty-eight of them — and the field sits at forty-eight percent, an interval straddling the line. No lean. Without memory, every published direction counts the same: fifty-four percent, and the interval clears the line. A confident UP. Memory didn't make the field more accurate. It made it stop pretending.*

### 1:30 — The gate `[terminal]`

```bash
./deletion-test.sh
```

Expected: `✅ GATE HELD — deleting memory moves the field 6.5pp, and flips the verdict (UP → no lean).`

> *Sibyl scores entries by deleting the memory layer — if the product still works, it's disqualified. This is that test, run against ourselves. Delete memory and the answer changes.*

### 1:50 — What it is worth `[terminal]`

```bash
$QUORUM_PY -m quorum.conviction
```

Expected: evidenced `50.0%` / default `49.7%`, Brier `0.3675` / `0.4318`; then
`as published 0.4094`, `defaults neutralised 0.2909`, `both honest 0.2500`.

> *One number for what that is worth. Accuracy is flat across the split — fifty percent on the evidenced calls, forty-nine point seven on the defaults. The reason does not tell you who is right, and we say so on the page. But conviction — the score on the confidence they claim — is not flat. As published the fleet scores point four one, worse than our own first-party oracle at point three one. Neutralise the confidence on the calls that fell through to a default, and the same calls score point two nine. Better than the oracle, with no agent predicting any better. Point two five is the floor, because getting under a coin flip is skill and this buys none. What it buys is the distance from point four one to point two five — and that is the stretch with anything left on it.*

### 2:10 — The screen `[terminal → browser]`

```bash
$QUORUM_PY -m quorum serve
```

Switch to the browser, type `localhost:8420`. Night is `2026-08-27`, memory **on**.

> *The field explains itself. Left: which signals decided tonight. Middle: one node per call — lit if its rule fired, shadow if it fell through to a default. Right: the belief, its interval, no lean. Notice there's no gold anywhere. The brand has a rule: if nothing is live, there is no gold.*

**Click the switch → memory off.**

> *Flip it. Every node lights up, because without memory nothing distinguishes them. The interval snaps tight, and the page emits a confident UP — the direction its own evidenced agents contradict.*

**Switch back to memory on. Scroll to "Who moved?".** Change night to `2026-09-01`.

> *This is the finding. Over twenty-one nights, eighty-two percent of agents never changed their call. Their rule's condition either always held or never held. Only eighteen percent ever switched — the only agents actually responding to the market. So the naive aggregate — five and a half thousand calls with a tight interval — is mostly deploy-time composition counted as opinion. The honest interval is four times wider. Same point estimate. The certainty was manufactured.*

> *And this is the part a single night can't tell you. Classified from the nights before tonight only — on the twenty-seventh, memory is too shallow and the panel says cannot say. Five nights later the same fleet classifies. Memory deepening changes what the product is able to say.*

**Scroll to "Are they the same opinion?".**

> *We also tested the obvious objection — that agents reading the same signals are one opinion in many coats. They're not. Against an exact independence baseline: fifty-six point one percent agreement observed, fifty-six point five expected by chance. Indistinguishable from strangers. That claim is struck through on the page, because our own test refuted it.*

### 3:20 — The commitment on Base `[terminal]`

Back to the terminal. `Ctrl-C` the server.

```bash
python3 -m quorum verify
```

Expected: `"ok": true`, `"attested": "0xfaa6…925e"`, `"tx": "0xa0013b…"`.

> *Everything you just saw could have been tuned after the fact. So the frozen field and both gate answers are committed to a digest, attested on Base mainnet before judging. Verify recomputes it from the repo — no key, no network, no store.*

Switch to the easscan tab, one beat. Then the basescan tab.

> *And the agent this record belongs to is a live participant on Virtuals ACP — this is a job it bought and completed on Base this week, create, fund, complete.*

### 3:50 — Delete it, on camera `[terminal]`

```bash
rm quorum.db && $QUORUM_PY -m quorum field 2026-08-27
```

Expected: `"status": "CANNOT SAY"`.

> *Delete the memory. The product doesn't degrade to an estimate. It stops. That's the whole design: a memory that answers everything is how you inherit noise as if it were structure. This one holds n and uncertainty beside every claim — and when you take it away, it says so.*

### 4:05 — Close

> *Quorum. Memory of why. Everything is public and reproducible from the repo.*

Stop recording.

---

## If something goes wrong mid-take

- **A command fails:** don't cut. Say *"let me re-run that"* and re-run it. Judges are told it's one take; an honest stumble is worth more than a clean edit.
- **The server won't bind 8420:** `$QUORUM_PY -m quorum serve --port 8421`, and type that instead.
- **Browser shows a stale page:** hard refresh. The API is computed per request; the page can't be stale, only the tab.

## Numbers you will say, and where each comes from

| line | number | source |
|---|---|---|
| calls / nights | 23,106 / 21 | `ingest` output |
| with memory | 588 · 47.8% · [43.8, 51.8] | `field` |
| without | 715 · 54.3% · [50.6, 57.9] | `field --memory off` |
| gate | 6.5pp, verdict flips | `deletion-test.sh` |
| constant-output | 82% | "Who moved?" panel, night 09-01 |
| interval ratio | 4.4× | same panel |
| cohorts | 56.07% vs 56.53% | "Same opinion?" panel |
| attestation | `0x30431e…cd50`, block 50904246 | `verify` / easscan |
| ACP job | 76546, tx `0x1d7a…59bc` | basescan |

Every one of these is recomputed live by the command that produces it. Nothing is read from a slide.
