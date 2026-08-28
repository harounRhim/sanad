# Sanad — Tajweed correction for Qur'anic recitation

Arabic speech AI that listens to a recitation and tells the learner **which rule
they got wrong and by how much** — not just a score.

> **Scope.** Sanad is an assistive practice tool. It does not replace a qualified
> teacher and is not an authority on tajwīd. Its thresholds are derived from
> measured recitation, not from a scholarly ruling. See [Limitations](#limitations).

---

## The problem

Learning tajwīd requires a teacher who listens and corrects. Most learners do not
have one available on demand. Generic speech recognition does not help: it tells
you *what* was said, never whether the `madd` was held for 2 ḥarakāt or 6, or
whether the `ghunnah` was actually nasalised.

Sanad measures the things tajwīd is actually about — **duration and nasality** —
against the rule annotations of the verse being recited.

## How it works

```
audio ─► Wav2Vec2 forced alignment ─► per-character timing
                                            │
verse + tajweed annotations (ground truth) ─┤
                                            ▼
                        content guard (CER)  ──► mismatch? stop, don't grade
                                            │
                                            ▼
                        acoustic rule measurement ──► per-segment report
```

**Forced alignment.** `jonatasgrosman/wav2vec2-large-xlsr-53-arabic` decodes the
audio; CTC alignment maps each character of the reference verse to a time span.

**Relative ḥaraka unit.** One ḥaraka is estimated *inside the recitation itself*,
ideally from `madd_2` segments (2 ḥarakāt by definition). Grading is therefore
independent of the reciter's tempo — a slow and a fast recitation of the same
verse are judged the same way.

**Acoustic measurement.** `madd` rules are scored on held duration in ḥarakāt.
`ghunnah` rules additionally get a nasality score from low-frequency energy.

**Content guard.** Before grading, the decoded text is compared to the expected
verse by character error rate. If they diverge, grading is short-circuited.
This came from a real failure: on 2026-07-06 the system happily graded a
recitation performed in French. A detailed tajwīd report on the wrong content is
worse than no report.

## Results

Calibration over **6,747 measured segments** across 48 āyāt (sūrahs 105–114).
Values are held duration in ḥarakāt.

| Rule | Segments | Median | Nominal |
|---|---:|---:|---|
| `madd_2` | 1,226 | 2.00 | 2 |
| `madd_246` | 1,064 | 3.10 | 2–6 |
| `ghunnah` | 861 | 0.94 | ~1 |
| `ikhfa` | 724 | 2.20 | ~2 |
| `idghaam_ghunnah` | 565 | 1.50 | ~2 |
| `madd_munfasil` | 549 | 4.97 | 4–5 |
| `iqlab` | 547 | 1.00 | ~1 |
| `madd_muttasil` | 532 | 5.83 | 4–5 |
| `madd_6` | 332 | 11.32 | 6 |
| `ikhfa_shafawi` | 285 | 2.00 | ~2 |
| `madd_6_muqattaat` | 62 | 13.95 | 6+ |

Two findings worth reading:

- **`madd_2` lands at exactly 2.00 with zero deviation** — expected, since it
  defines the ḥaraka unit. It is a sanity check on the measurement, not a result.
- **`madd_6` measures 11.32, not 6.** Reciters hold madd lāzim far longer than
  its nominal value. `muqaṭṭaʿāt` letters are longer still and vary so much
  (8–25+ ḥarakāt) that they were split into their own class — leaving them mixed
  in polluted the norm for genuine madd lāzim.

Raw calibration: [`Data/processed/tajweed_calibration.json`](Data/processed/tajweed_calibration.json).

## Limitations

- **Calibrated on a single reciter, 48 āyāt, sūrahs 105–114.** Not validated
  across recitation styles, and not validated on learner voices — which are
  exactly the voices the tool is meant to serve.
- **Two rule families only.** `madd` (duration) and `ghunnah` (duration +
  nasality) are the objectively measurable ones. Rules depending on articulation
  point or letter quality are out of scope for this version.
- **CPU inference takes seconds per āyah.** The model is loaded once at server
  startup; it is not real-time.
- **Alignment quality bounds everything.** A bad decode produces bad timings,
  and therefore bad grades. The content guard catches gross failures, not subtle
  ones.

## Architecture

| Component | What it does |
|---|---|
| `src/tajweed/correction/` | Alignment, rule measurement, content check, word scoring, calibration, evaluation |
| `src/tajweed/` (ETL) | Streaming ingest of Qur'anic text, tajwīd annotations and multi-reciter audio into Supabase/Postgres |
| `server/app.py` | FastAPI grading service — `/grade`, `/grade_window`, `/grade_clip` |
| `app/` | React + TypeScript + Tailwind PWA — reader, practice, memorisation, SM-2 review |

The ETL handles ~36 GB of audio across 30 reciters without loading it into RAM:
generators plus `ijson` throughout, batched idempotent upserts, and a replayable
dead-letter queue so a failing row never stops the stream. Full pipeline
documentation: [`docs/PIPELINE.md`](docs/PIPELINE.md).

## Tests

```bash
pip install -r requirements.txt
pytest -q          # 81 tests
```

`torch`, `transformers` and `soundfile` are imported lazily and are only needed
for the real Wav2Vec2 aligner. The test suite runs on the synthetic aligner, so
the core installs and tests without them.

## Running it

See [`docs/PIPELINE.md`](docs/PIPELINE.md) for the ETL, and
[`app/README.md`](app/README.md) for the frontend. Configuration is by
environment variable — copy `.env.example.txt` to `.env` and
`app/.env.example` to `app/.env.local`.

The `service_role` Supabase key is server-side only; the browser gets the
publishable key and reads through row-level security policies.

## Data sources

Qur'anic text (Uthmani), tajwīd rule annotations and reciter audio come from
third-party sources, each under its own terms. No audio or corpus data is
committed to this repository — only the code that processes it, and the
calibration results it produces.

---

**Author:** Haroun Rhim · Monastir, Tunisia
