# -*- coding: utf-8 -*-
"""
src/tajweed/correction/evaluate.py — Orchestrateur + CLI du moteur de correction.

Chaîne (offline/batch) :
    (audio, sourate, ayah)
      → GroundTruth (texte + segments Tajweed)
      → Aligner.align → Alignment (timing par caractère)
      → measure_all → résultats Madd/Ghunnah
      → Report (JSON + résumé console)

Exemples :
    # démo de bout en bout sans modèle (aligneur synthétique, source locale)
    python -m tajweed.correction.evaluate --audio rec.wav --surah 1 --ayah 2 \
        --aligner synthetic --source local

    # évaluation réelle (wav2vec2 CPU, vérité terrain Supabase)
    python -m tajweed.correction.evaluate --audio rec.wav --surah 112 --ayah 1 \
        --aligner wav2vec2 --source supabase
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Tuple

from .types import Report, WindowReport, ClipReport
from .rules import measure_all
from .ground_truth import LocalGroundTruth, SupabaseGroundTruth, GTSegment
from .content_check import check_content, locate_best_span
from .word_score import score_words


def load_waveform(path: Path) -> Tuple[Optional[object], Optional[int]]:
    """(waveform mono float, sr) via soundfile, ou (None, None) si indisponible.
    Sert au score de nasalité ; son absence dégrade en mesure durée-seule."""
    try:
        import soundfile as sf
        import numpy as np
    except ImportError:
        return None, None
    try:
        data, sr = sf.read(str(path), dtype="float32")
    except Exception:  # format non lu par libsndfile (ex. mp3 ancien)
        return None, None
    if getattr(data, "ndim", 1) > 1:
        data = data.mean(axis=1)
    return np.asarray(data), int(sr)


def evaluate(audio_path: Path, surah: int, ayah: int, aligner, gt_source,
             with_nasality: bool = True, calibration: Optional[dict] = None) -> Report:
    g = gt_source.get(surah, ayah)
    al = aligner.align(Path(audio_path), g.text)
    aligner_name = getattr(aligner, "name", type(aligner).__name__)

    # Roadmap V2 Phase 0 : `decoded_text` n'existe que pour un aligneur qui
    # décode réellement l'audio (Wav2Vec2Aligner) — SyntheticAligner (tests/
    # démo) laisse "unknown", pas de garde-fou de contenu possible sans ML.
    content_status, content_cer = "unknown", None
    if al.decoded_text is not None:
        content_status, content_cer = check_content(al.decoded_text, g.text)

    if content_status == "content_mismatch":
        # Court-circuite la notation Tajweed : un rapport détaillé sur un
        # contenu qui ne correspond pas à l'ayah n'a aucun sens (cf. le test
        # du 2026-07-06 où réciter en français/anglais donnait quand même un
        # rapport "gradé" plausible — c'est exactement ce que ceci évite).
        return Report(surah=surah, ayah=ayah, audio_path=str(audio_path),
                      duration=al.duration, haraka_unit_s=None, aligner=aligner_name,
                      results=[], content_status=content_status,
                      content_cer=content_cer, decoded_text=al.decoded_text)

    wav, sr = load_waveform(Path(audio_path)) if with_nasality else (None, None)
    results, unit = measure_all(al, g.segments, wav, sr, calibration, surah, ayah)
    word_scores = score_words(g.text, al.decoded_text, results, surah, ayah)
    return Report(surah=surah, ayah=ayah, audio_path=str(audio_path),
                  duration=al.duration, haraka_unit_s=unit, aligner=aligner_name,
                  results=results, content_status=content_status,
                  content_cer=content_cer, decoded_text=al.decoded_text,
                  word_scores=word_scores)


def evaluate_window(audio_path: Path, surah: int, start_ayah: int, aligner, gt_source,
                    count: int = 6, with_nasality: bool = True,
                    calibration: Optional[dict] = None) -> WindowReport:
    """Note un clip contre une FENÊTRE de `count` ayahs à partir de `start_ayah`
    au lieu de supposer que le clip EST exactement une ayah donnée (voir
    RangeGroundTruth). `confirmed_ayahs` = préfixe consécutif d'ayahs dont
    TOUS les mots sont content_ok — c'est ce que l'appelant utilise pour
    avancer son curseur de récitation, quelle que soit la vitesse/l'absence
    de pauses du récitant (le bug que ceci corrige : 2026-07-07, tout un
    enregistrement continu de plusieurs ayahs finissait noté comme l'ayah 1).
    `resume_ayah` (2026-07-08) est un filet de secours si `confirmed_ayahs`
    échoue dès `start_ayah` mais qu'une ayah PLUS LOIN dans la fenêtre montre
    quand même une forte évidence — évite qu'un seul échec de confirmation
    bloque le curseur indéfiniment (voir commentaire plus bas)."""
    g = gt_source.get_range(surah, start_ayah, count)
    al = aligner.align(Path(audio_path), g.text)
    aligner_name = getattr(aligner, "name", type(aligner).__name__)
    ayah_spans = [(s.ayah, s.start, s.end) for s in g.ayah_spans]

    content_status, content_cer = "unknown", None
    if al.decoded_text is not None:
        content_status, content_cer = check_content(al.decoded_text, g.text)

    if content_status == "content_mismatch":
        return WindowReport(surah=surah, start_ayah=start_ayah, end_ayah=g.end_ayah,
                            audio_path=str(audio_path), duration=al.duration,
                            aligner=aligner_name, ayah_spans=ayah_spans,
                            content_status=content_status, content_cer=content_cer,
                            decoded_text=al.decoded_text)

    wav, sr = load_waveform(Path(audio_path)) if with_nasality else (None, None)
    # measure_all's muqattaʿāt/basmala context takes ONE (surah,ayah) pair — only
    # applied correctly for `start_ayah` itself here. Acceptable v1 simplification:
    # a window starting mid-recitation on a muqattaʿāt-opening ayah is rare, and
    # the effect is scoped to that rule's grading, not correctness of the rest.
    results, unit = measure_all(al, g.segments, wav, sr, calibration, surah, start_ayah)
    word_scores = score_words(g.text, al.decoded_text, results, surah, start_ayah)

    # Consecutive prefix of "recognized enough" ayahs from the start of the
    # window. NOTE (validated on real audio 2026-07-07): requiring ALL words
    # content_ok is too strict — the raw non-Quran-tuned CTC decode has a real
    # per-word error rate (~25-40%) even on a clean, CORRECT recitation (e.g.
    # "الْعَٰلَمِينَ" decoded "العالمن", one letter off, still flagged as a
    # content mismatch under exact-word matching). A MAJORITY threshold is far
    # more robust: still rejects genuinely wrong content (a skipped/substituted
    # ayah has most of its words unmatched), but tolerates normal ASR noise on
    # correct recitation. See docs/ROADMAP_V2.txt for the real-audio evidence.
    CONFIRM_RATIO = 0.5
    confirmed: list[int] = []
    for ayah, s, e in ayah_spans:
        in_ayah = [w for w in word_scores if w.start_idx >= s and w.end_idx <= e]
        ok_ratio = sum(1 for w in in_ayah if w.content_ok) / len(in_ayah) if in_ayah else 0.0
        if in_ayah and ok_ratio >= CONFIRM_RATIO:
            confirmed.append(ayah)
        else:
            break

    # "Stuck cursor" rescue (2026-07-08, found from a real user report): a
    # single failed confirmation at `start_ayah` would otherwise strand the
    # cursor forever — every LATER segment (containing genuinely later
    # content, since the reciter keeps going) gets compared against the same
    # un-advanced window start and can never match either, cascading into
    # "nothing ever gets recognized" for the rest of the session. If a LATER
    # ayah in the window still shows strong evidence (a stricter ratio than
    # CONFIRM_RATIO, since we're accepting a gap in the consecutive prefix),
    # resume right after it rather than blocking indefinitely. The ayah(s)
    # between start_ayah and resume_ayah are left un-graded (not falsely
    # marked wrong) — the caller (Practice.tsx) shows them as "skipped/
    # unclear" rather than red.
    RESCUE_RATIO = 0.6
    resume_ayah: Optional[int] = None
    if len(confirmed) < len(ayah_spans):
        for ayah, s, e in ayah_spans[len(confirmed):]:
            in_ayah = [w for w in word_scores if w.start_idx >= s and w.end_idx <= e]
            ratio = sum(1 for w in in_ayah if w.content_ok) / len(in_ayah) if in_ayah else 0.0
            if ratio >= RESCUE_RATIO:
                resume_ayah = ayah + 1        # keep the FURTHEST qualifying ayah

    return WindowReport(surah=surah, start_ayah=start_ayah, end_ayah=g.end_ayah,
                        audio_path=str(audio_path), duration=al.duration,
                        aligner=aligner_name, ayah_spans=ayah_spans,
                        content_status=content_status, content_cer=content_cer,
                        decoded_text=al.decoded_text, word_scores=word_scores,
                        confirmed_ayahs=confirmed, resume_ayah=resume_ayah)


def evaluate_clip(audio_path: Path, surah: int, aligner, gt_source,
                  with_nasality: bool = True, calibration: Optional[dict] = None,
                  max_ayahs: int = 999, near_ayah: Optional[int] = None) -> ClipReport:
    """Note un clip contre une SOURATE ENTIÈRE traitée comme un seul long
    paragraphe (Roadmap V2, 2026-07-08 — "on n'a pas besoin de naviguer entre
    les ayahs, une sourate c'est juste un paragraphe") : PAS de start_ayah/
    curseur à fournir. Le clip est LOCALISÉ dans la sourate via son contenu
    décodé (content_check.locate_best_span — CARACTÈRE, pas mot : voir sa
    docstring, une approche mot-par-mot a été essayée et abandonnée, pas assez
    robuste aux frontières de mots parfois mal décodées), PUIS noté seulement
    sur la petite plage identifiée — le forced_align coûteux ne porte JAMAIS
    sur toute la sourate, seulement sur les quelques ayahs identifiées (voir
    aligner.decode()/align_from_decode() : une seule passe modèle, réutilisée).

    Remplace evaluate_window pour la récitation continue : élimine la classe
    de bug "curseur bloqué" (2026-07-07/08) au lieu de la contourner — il n'y
    a plus de curseur du tout côté serveur, chaque clip est noté de façon
    STATELESS. Nécessite un aligneur qui décode réellement l'audio (decode()/
    align_from_decode() — Wav2Vec2Aligner) ; SyntheticAligner n'est pas
    supporté ici (pas de contenu à localiser sans vrai décodage).

    `near_ayah` (optionnel) : simple indice de proximité transmis tel quel à
    `locate_best_span` — départage une AMBIGUÏTÉ réelle (une même courte
    phrase apparaissant deux fois dans la sourate, ex. Al-Fātiḥa "الرحمن
    الرحيم" en fin d'ayah 1 ET comme ayah 3 entière) sans réintroduire de
    curseur : ça ne fait JAMAIS gagner un candidat objectivement moins bon,
    seulement départager des candidats déjà quasi ex æquo."""
    if not hasattr(aligner, "decode") or not hasattr(aligner, "align_from_decode"):
        raise TypeError(
            f"evaluate_clip requiert un aligneur avec decode()/align_from_decode() "
            f"(pas {type(aligner).__name__}) — pas de contenu à localiser sans décodage réel.")

    g = gt_source.get_range(surah, 1, max_ayahs)   # la sourate ENTIÈRE
    aligner_name = getattr(aligner, "name", type(aligner).__name__)
    decoded = aligner.decode(Path(audio_path))

    whole_spans = [(s.ayah, s.start, s.end) for s in g.ayah_spans]
    match = locate_best_span(decoded.decoded_text, g.text, whole_spans, near_ayah=near_ayah)
    if match is None:
        return ClipReport(surah=surah, located=False,
                          audio_path=str(audio_path), duration=decoded.duration,
                          aligner=aligner_name, content_status="content_mismatch",
                          decoded_text=decoded.decoded_text)

    ayah_from, ayah_to, content_cer = match
    # Réutilise le score de locate_best_span (PREFIX-aware) plutôt que de
    # rappeler check_content() sur tout le sous-texte : un check_content
    # naïf sur [ayah_from, ayah_to] réintroduirait exactement le biais que
    # locate_best_span corrige (une āyah longue récitée en plusieurs clips —
    # le premier clip ne couvre qu'un DÉBUT, pas toute l'āyah, cf. docstring
    # de _prefix_aware_cer). `threshold` est déjà appliqué dans
    # locate_best_span (None si dépassé) donc arriver ici = toujours "ok".
    content_status = "ok"

    # Borne le texte/segments/spans à [ayah_from, ayah_to] SEULEMENT — c'est
    # CE texte, pas la sourate entière, qui va au forced_align coûteux.
    spans_in_range = [s for s in g.ayah_spans if ayah_from <= s.ayah <= ayah_to]
    text_start, text_end = spans_in_range[0].start, spans_in_range[-1].end
    sub_text = g.text[text_start:text_end]
    sub_segments = [
        GTSegment(seg.rule, seg.start_idx - text_start, seg.end_idx - text_start, seg.segment)
        for seg in g.segments if text_start <= seg.start_idx and seg.end_idx <= text_end
    ]
    sub_ayah_spans = [(s.ayah, s.start - text_start, s.end - text_start) for s in spans_in_range]

    try:
        al = aligner.align_from_decode(decoded, sub_text)   # RÉUTILISE decoded — pas de 2e passe modèle
    except RuntimeError as e:
        # torchaudio's forced_align has a hard CTC constraint: the target
        # token sequence (with mandatory blanks between consecutive repeats)
        # must fit within the emission's frame count, or it raises
        # "targets length is too long for CTC" — NOT a Python exception type
        # specific to this case, just torchaudio's generic RuntimeError, so
        # match on the message rather than swallowing every RuntimeError.
        # Hits in practice on a genuinely very short/near-silent clip that
        # locate_best_span still matched against a comparatively long span
        # (2026-07-09: a stray trailing segment from continuous listening,
        # cut just after a real recitation — see app/ ListenRepeat.tsx's
        # autoRec.stop()-on-pass fix for the client-side half of this).
        # Was surfacing as a raw, untranslated-looking 422 to the end user
        # ("Échec de l'analyse audio : ... targets length is too long...").
        # The correct read of this failure is exactly the same as
        # locate_best_span returning no match: this candidate span doesn't
        # actually fit what's in the clip — not located, not a hard error.
        if "targets length" in str(e) and "CTC" in str(e):
            return ClipReport(surah=surah, located=False,
                              audio_path=str(audio_path), duration=decoded.duration,
                              aligner=aligner_name, content_status="content_mismatch",
                              decoded_text=decoded.decoded_text)
        raise

    wav, sr = load_waveform(Path(audio_path)) if with_nasality else (None, None)
    results, unit = measure_all(al, sub_segments, wav, sr, calibration, surah, ayah_from)
    word_scores = score_words(sub_text, decoded.decoded_text, results, surah, ayah_from)

    return ClipReport(surah=surah, located=True, ayah_from=ayah_from, ayah_to=ayah_to,
                      audio_path=str(audio_path), duration=decoded.duration,
                      aligner=aligner_name, ayah_spans=sub_ayah_spans,
                      content_status=content_status, content_cer=content_cer,
                      decoded_text=decoded.decoded_text, word_scores=word_scores)


def _make_aligner(kind: str, model: str):
    if kind == "synthetic":
        from .aligner import SyntheticAligner
        return SyntheticAligner()
    if kind == "wav2vec2":
        from .aligner import Wav2Vec2Aligner
        return Wav2Vec2Aligner(model_id=model)
    raise SystemExit(f"Aligneur inconnu : {kind}")


def _make_source(kind: str, text: Path, json_path: Path):
    if kind == "local":
        return LocalGroundTruth(text, json_path)
    if kind == "supabase":
        return SupabaseGroundTruth()
    raise SystemExit(f"Source inconnue : {kind}")


def print_report(rep: Report) -> None:
    print(f"\n=== Correction Tajweed — {rep.surah}:{rep.ayah} ===")
    print(f"Audio : {rep.audio_path}  ({rep.duration:.2f}s)  | aligneur : {rep.aligner}")
    if rep.content_status == "content_mismatch":
        print(f"⛔ Contenu suspect (CER={rep.content_cer:.2f}) — décodé : « {rep.decoded_text} »")
        print("   Pas de notation Tajweed : le texte reconnu ne correspond pas à cette ayah.")
        return
    if rep.haraka_unit_s:
        print(f"Unité ḥaraka estimée : {rep.haraka_unit_s:.3f}s")
    if not rep.results:
        print("Aucun segment Madd/Ghunnah dans cette ayah.")
        return
    for r in rep.results:
        mark = {"ok": "✅", "warn": "⚠", "missing_audio": "∅"}.get(r.status, "?")
        print(f"  {mark} {r.rule:16} «{r.segment}»  {r.measured}  — {r.message}")
    print(f"\nBilan : {rep.n_ok} ok, {rep.n_warn} à revoir, sur {len(rep.results)} segments.")
    if rep.word_scores:
        mark = {"green": "🟢", "yellow": "🟠", "red": "🔴"}
        line = " ".join(f"{mark[w.verdict]}{w.word}" for w in rep.word_scores)
        print(f"\nPar mot : {line}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Évalue le Tajweed d'un enregistrement (offline).")
    p.add_argument("--audio", type=Path, required=True)
    p.add_argument("--surah", type=int, required=True)
    p.add_argument("--ayah", type=int, required=True)
    p.add_argument("--aligner", choices=["synthetic", "wav2vec2"], default="wav2vec2")
    p.add_argument("--model", default="jonatasgrosman/wav2vec2-large-xlsr-53-arabic")
    p.add_argument("--source", choices=["local", "supabase"], default="local")
    p.add_argument("--text", type=Path, default=Path("Data/raw/quran-uthmani.txt"))
    p.add_argument("--json", type=Path,
                   default=Path("Data/raw/tajweed.hafs.uthmani-pause-sajdah.json"))
    p.add_argument("--no-nasality", action="store_true")
    p.add_argument("--calibration", type=Path, default=None,
                   help="JSON de normes apprises (tajweed.correction.calibrate).")
    p.add_argument("--out", type=Path, default=None, help="Écrire le rapport JSON.")
    args = p.parse_args(argv)

    if not args.audio.exists():
        raise SystemExit(f"Audio introuvable : {args.audio}")
    calibration = None
    if args.calibration:
        calibration = json.loads(Path(args.calibration).read_text(encoding="utf-8"))
    aligner = _make_aligner(args.aligner, args.model)
    source = _make_source(args.source, args.text, args.json)
    rep = evaluate(args.audio, args.surah, args.ayah, aligner, source,
                   with_nasality=not args.no_nasality, calibration=calibration)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(rep.to_dict(), ensure_ascii=False, indent=2),
                            encoding="utf-8")
        print(f"✅ Rapport écrit : {args.out}")
    print_report(rep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
