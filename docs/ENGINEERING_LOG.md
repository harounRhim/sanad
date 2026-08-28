# Engineering log

Defects found in Sanad, and what was done about them. Kept because the bugs are
more instructive than the features: each one below was invisible until something
forced it into the open.

---

## The system graded a recitation performed in French

**2026-07-06.** Testing the correction engine with deliberately wrong audio, it
returned a plausible, fully detailed tajwīd report — measured durations, per-word
verdicts, the lot. The recitation was in French.

The engine forced-aligns audio against the *expected* verse. Forced alignment
always produces an alignment: given any audio and any target text, it finds the
path with the best score, however bad that best is. Nothing in the pipeline ever
asked whether the audio was the right content in the first place.

**Fix:** `content_check.py` compares the decoded text against the expected verse
by character error rate and short-circuits grading when they diverge. A detailed
report on the wrong content is worse than no report — it is confidently wrong.

**Still open:** the threshold is a single global value, so it produces false
rejections on very short āyāt where the decoder garbles the audio. Quraysh 106:1,
recited correctly by a professional reciter, is rejected at CER 0.79. The
threshold should scale with āyah length.

---

## `locate_best_span` preferred longer windows at equal cost

**2026-07-11.** When grading a clip against a whole sūrah, the window localiser
preferred a superset window that tied a tighter match on CER. A suffix fit's free
gap is *zero evidence* for the extra āyāt it swallows, so ties were being broken
in favour of claiming more than the audio supported — inflating `ayah_from`.

**Fix:** prune dominated windows before selection.

**What it exposed:** the regression was caught by the test suite only after
`pytest` was reinstalled — it had gone missing from the virtualenv, so the suite
had been silently stale. A test suite that is not run is not a test suite.

---

## Three progress hooks lost updates under burst callers

**2026-07-11.** Streak, memorisation and active-slate hooks each compounded
updates onto render-closure state. Burst callers — the loop inside `finishChunk`,
timers — could read stale state and drop increments. A user could finish a
session and lose their streak.

**Fix:** every mutator now reads the live React Query cache rather than closure
state.

---

## The app looked healthy while persisting nothing

**2026-07-11.** If `schema.sql`'s `user_*` tables were not created, the app ran
perfectly: navigation worked, progress appeared to save, nothing errored
visibly. The writes failed silently to the console.

**Fix:** a red banner in the layout naming exactly what to run. Failures that are
invisible are worse than failures that are loud.

Two further classes of the same problem were fixed the same night: a missing
error boundary meant any render error white-screened the whole app, and a
forgotten password permanently locked a user out of their progress because
mandatory accounts had no recovery flow.

---

## Two tests depended on an 8 MB generated artefact

**2026-08-28.** Setting up continuous integration, two tests in
`test_alignment.py` failed on a clean checkout. They needed
`Data/processed/audio_map.json` — an 8 MB file produced by
`tajweed.audio_mapper`, not committed and not committable.

They had always passed locally because the file happens to exist on the
development machine. The suite was never hermetic; nothing had ever told us.

**Fix:** the two tests skip with an explicit reason when the artefact is absent.
CI now reports **79 passed, 2 skipped** — which is honest, where a green 81 would
not have been.

---

## The engine could never have run on a GPU

**2026-08-28.** `Wav2Vec2Aligner` accepts a `device` argument and defaults to
`"cpu"`. Passing `"cuda"` moved the model to the GPU and then crashed:

```
RuntimeError: targets must be a CUDA tensor
```

`forced_align` builds its `targets` tensor with no device argument, so it landed
on the CPU while the emission sat on the GPU. torchaudio's CUDA kernel refuses
the mix. The `device` parameter had existed for months and had never worked for
its only non-default value.

**Fix:** build `targets` on `decoded.emission.device`.

**How it surfaced:** deploying the demo to Hugging Face Spaces, which allocates a
GPU. Nothing in local development would ever have found it — the default path
works, and the default path was the only path anyone took.

---

## The model reloaded on every single request

**2026-08-28.** With the GPU fix in, grading still failed. ZeroGPU forks a fresh
worker for each decorated call, so a model loaded lazily *inside* that call is
re-read from disk every request — 1.2 GB, every time, inside a metered GPU window.

**Fix:** load at module scope, so the weights live in the parent process and
every forked worker inherits them.

---

## The demo is scoped to 13 āyāt, and here is why

Before publishing the demo, every candidate āyah was run end-to-end against a
reference recitation rather than assumed to work. Two were dropped:

- **106:1** — the decoder garbles this very short āyah (CER 0.79), so the content
  guard rejects even a correct recitation.
- **108:1** — the ḥaraka unit collapses to 0.050 s, against 0.20–0.24 s
  everywhere else, inflating every reported duration.

The second points at a real limitation: the ḥaraka unit is estimated from
`madd_2` segments inside the recitation. On an āyah with no such anchor the
fallback is unreliable — 114:1 reports **37.67 ḥarakāt** for a `madd_246` whose
nominal value is 2–6. Offering only anchored āyāt is a workaround, not a fix.

---

## What is still open

1. **Content-guard threshold** should scale with āyah length, to stop rejecting
   correct recitations of short verses.
2. **Ḥaraka unit without a `madd_2` anchor** needs either a robust fallback or an
   explicit refusal to grade, saying why.
3. **Calibration breadth** — one reciter, 48 āyāt. Not validated across
   recitation styles, and not validated on learner voices, which are the voices
   the tool exists to serve.
