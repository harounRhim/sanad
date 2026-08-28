# -*- coding: utf-8 -*-
"""
Sanad — public demo Space.

Wraps the tajweed correction engine in a Gradio UI, deliberately scoped to the
ten short surahs (105-114) that the calibration actually covers.

Why the ayah list is restricted: the haraka unit is estimated from `madd_2`
segments inside the recitation itself. On an ayah with no madd_2 to anchor it,
the fallback unit is unreliable and the reported durations become nonsense
(measured 37.67 harakat on 114:1 during testing). Only ayahs carrying a madd_2
anchor are offered here.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import gradio as gr
import spaces
import torch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from tajweed.correction.aligner import Wav2Vec2Aligner            # noqa: E402
from tajweed.correction.evaluate import evaluate                  # noqa: E402
from tajweed.correction.ground_truth import LocalGroundTruth      # noqa: E402

MODEL_ID = os.environ.get("SANAD_MODEL", "jonatasgrosman/wav2vec2-large-xlsr-53-arabic")
DATA = ROOT / "Data"

SURAH_NAMES = {
    105: "Al-Fil", 106: "Quraysh", 107: "Al-Ma'un", 108: "Al-Kawthar",
    109: "Al-Kafirun", 110: "An-Nasr", 111: "Al-Masad", 112: "Al-Ikhlas",
    113: "Al-Falaq", 114: "An-Nas",
}

# Ayahs in 105-114 that carry a madd_2 anchor, so the haraka unit is trustworthy.
#
# Each was verified end-to-end against a reference recitation before being
# listed. Two candidates were dropped after that sweep:
#   106:1 — the decoder garbles this very short ayah (CER 0.79), so the content
#           guard rejects even a correct recitation.
#   108:1 — the haraka unit collapses to 0.050s here, against 0.20-0.24s
#           everywhere else, which inflates every reported duration.
DEMO_AYAHS = [
    (105, 1), (106, 2), (106, 3), (107, 2), (109, 1), (109, 3), (109, 5),
    (110, 3), (111, 2), (111, 4), (112, 4), (113, 4), (114, 3),
]
CHOICES = [f"{SURAH_NAMES[s]} {s}:{a}" for s, a in DEMO_AYAHS]

_gt = LocalGroundTruth(DATA / "raw" / "quran-uthmani.txt",
                       DATA / "raw" / "tajweed.hafs.uthmani-pause-sajdah.json")
_cal = json.loads((DATA / "processed" / "tajweed_calibration.json").read_text(encoding="utf-8"))
_aligner = None


def _get_aligner():
    """Weights load once into the main process; the GPU move happens per call.

    This Space runs on ZeroGPU, where CUDA only exists inside a @spaces.GPU
    function. Loading the ~1.2 GB model on every request would dominate the
    latency, so it is loaded on CPU at first use and only *moved* to the GPU
    inside the decorated call.
    """
    global _aligner
    if _aligner is None:
        _aligner = Wav2Vec2Aligner(model_id=MODEL_ID, device="cpu")
    return _aligner


def _to_device(aligner, device):
    model = getattr(aligner, "_model", None)
    if model is not None:
        aligner._model = model.to(device)
    aligner.device = device
    return aligner


COLOR = {"green": "#1f7a4d", "yellow": "#9a6b00", "red": "#a32020"}


def _render_verse(word_scores, plain_text):
    if not word_scores:
        return f"<div dir='rtl' style='font-size:2rem;line-height:2.2'>{plain_text}</div>"
    parts = []
    for w in word_scores:
        c = COLOR.get(w.get("verdict", "green"), "#444")
        rules = w.get("rules") or []
        tip = " · ".join(r.get("message", "") for r in rules) or "no measurable rule"
        parts.append(
            f"<span title=\"{tip}\" style=\"color:{c};border-bottom:2px solid {c};"
            f"margin:0 .18em;padding-bottom:2px\">{w['word']}</span>"
        )
    return ("<div dir='rtl' style='font-size:2rem;line-height:2.4;"
            "font-family:serif'>" + " ".join(parts) + "</div>")


@spaces.GPU(duration=120)
def _run_engine(audio_path, s, a):
    aligner = _get_aligner()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    _to_device(aligner, device)
    try:
        return evaluate(Path(audio_path), s, a, aligner, _gt, calibration=_cal).to_dict()
    finally:
        # Release the GPU copy so the next call starts from a clean CPU model.
        if device == "cuda":
            _to_device(aligner, "cpu")
            torch.cuda.empty_cache()


def grade(audio_path, choice):
    if not audio_path:
        return "### Record or upload a recitation first.", "", None

    s, a = DEMO_AYAHS[CHOICES.index(choice)]
    rep = _run_engine(audio_path, s, a)

    text = _gt.get(s, a).text
    cer = rep.get("content_cer")
    cer_txt = f"{cer:.2f}" if cer is not None else "n/a"

    if rep.get("content_status") == "content_mismatch":
        head = (f"### Content mismatch — not graded\n"
                f"The decoded audio does not match {SURAH_NAMES[s]} {s}:{a} "
                f"(character error rate {cer_txt}).\n\n"
                f"Recognised: *{rep.get('decoded_text') or '—'}*")
        return head, _render_verse(None, text), None

    unit = rep.get("haraka_unit_s")
    rows = [[r.get("rule"), r.get("measured"), r.get("expected"),
             r.get("status"), r.get("message")] for r in rep.get("results", [])]

    head = (f"### {SURAH_NAMES[s]} {s}:{a}\n"
            f"Audio {rep.get('duration_s', 0):.1f}s · ḥaraka unit "
            f"{unit:.3f}s · content CER {cer_txt} · "
            f"{len(rows)} measurable segment(s)")
    if not rows:
        head += "\n\nNo measurable rule fired on this recitation."
    return head, _render_verse(rep.get("word_scores"), text), rows


with gr.Blocks(title="Sanad — tajwīd correction") as demo:
    gr.Markdown(
        "# Sanad — tajwīd correction for Qur'anic recitation\n"
        "Recite an āyah and get back **which rule was measured and by how much** — "
        "duration in ḥarakāt, and nasality for ghunnah rules.\n\n"
        "> **Assistive practice tool.** It does not replace a qualified teacher and "
        "is not an authority on tajwīd. Thresholds come from measured recitation, "
        "not from a scholarly ruling."
    )
    with gr.Row():
        with gr.Column():
            ayah = gr.Dropdown(CHOICES, value=CHOICES[0], label="Āyah to recite")
            audio = gr.Audio(sources=["microphone", "upload"], type="filepath",
                             label="Your recitation")
            btn = gr.Button("Grade recitation", variant="primary")
        with gr.Column():
            head = gr.Markdown()
            verse = gr.HTML()
            table = gr.Dataframe(
                headers=["rule", "measured", "expected", "status", "note"],
                label="Measured segments", wrap=True)

    gr.Markdown(
        "**Scope.** Only sūrahs 105–114 are offered, and only the āyāt that carry a "
        "`madd_2` segment. The ḥaraka unit is estimated *inside* each recitation from "
        "`madd_2` (2 ḥarakāt by definition), which makes grading independent of the "
        "reciter's tempo — but leaves it unreliable on āyāt with no such anchor.\n\n"
        "**Calibration** covers 6,747 segments across 11 rules, measured on a single "
        "reciter over 48 āyāt. It has not been validated on learner voices — which are "
        "the voices this tool exists to serve.\n\n"
        "[Source code](https://github.com/harounRhim/sanad) · "
        "[harounrhim.github.io](https://harounrhim.github.io)"
    )

    btn.click(grade, [audio, ayah], [head, verse, table])

if __name__ == "__main__":
    demo.launch()
