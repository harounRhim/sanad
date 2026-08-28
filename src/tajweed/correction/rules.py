# -*- coding: utf-8 -*-
"""
src/tajweed/correction/rules.py — Mesure acoustique des règles Tajweed (v1).

v1 = les deux règles les plus OBJECTIVES :
  - MADD (allongement) : durée tenue vs ḥarakāt attendues (2 / 4-5 / 6) ;
  - GHUNNAH (nasalisation) : durée (~2 ḥarakāt) + score de nasalité (énergie
    basse-fréquence) si la forme d'onde est fournie.

Tout est RELATIF à la récitation : l'unité « 1 ḥaraka » est estimée DANS l'ayah
(idéalement via les segments madd_2, qui valent 2 ḥarakāt par définition). Aucun
modèle ML ici : on consomme une `Alignment` (timing par caractère).
"""

from __future__ import annotations

import statistics
from typing import List, Optional, Sequence, Tuple

from .types import Alignment, SegmentResult
from .ground_truth import GTSegment

# (min, max) ḥarakāt attendues par règle de madd.
MADD_HARAKAT = {
    "madd_2": (2.0, 2.0),
    "madd_muttasil": (4.0, 5.0),
    "madd_munfasil": (4.0, 5.0),
    "madd_6": (6.0, 6.0),
    "madd_6_muqattaat": (6.0, 12.0),   # madd lāzim sur lettres muqattaʿāt : 6 ḥ nominal, mais tenu plus long et très variable
    "madd_246": (2.0, 6.0),
}
GHUNNAH_RULES = {"ghunnah", "idghaam_ghunnah", "ikhfa", "iqlab", "ikhfa_shafawi"}

# Ayahs « muqattaʿāt » (lettres disjointes en ouverture de sourate). Le madd_6 y
# porte sur ces lettres, tenu de façon très variable (8–25+ ḥ selon le récitateur),
# ce qui pollue la norme du vrai madd lāzim (~6 ḥ). On les sépare donc en
# « madd_6_muqattaat ». 29 sourates (ayah 1) + ash-Shūrā 42:2 (عٓسٓقٓ).
_MUQATTAAT_SURAHS = (2, 3, 7, 10, 11, 12, 13, 14, 15, 19, 20, 26, 27, 28, 29,
                     30, 31, 32, 36, 38, 40, 41, 42, 43, 44, 45, 46, 50, 68)
MUQATTAAT_AYAHS = {(s, 1) for s in _MUQATTAAT_SURAHS} | {(42, 2)}


def effective_rule(rule: str, surah: Optional[int], ayah: Optional[int]) -> str:
    """Reclasse un madd_6 porté par des lettres muqattaʿāt en « madd_6_muqattaat ».
    Idempotent et neutre pour toute autre règle (ou si surah/ayah inconnus)."""
    if rule == "madd_6" and surah is not None and (surah, ayah) in MUQATTAAT_AYAHS:
        return "madd_6_muqattaat"
    return rule

# Règles de madd « à sens unique » : leur valeur nominale est un MINIMUM tenu plus
# ou moins long selon le récitateur (style mujawwad, allongement de pause), si bien
# que « trop long » n'est jamais une faute. On ne signale que le SOUS-allongement.
#   - madd_6 : madd lāzim, 6 ḥ obligatoires, mesuré ~8–16 ḥ (bord bas net p5≈6) ;
#   - madd_246 : madd ʿāriḍ/līn, 2 / 4 / 6 ḥ TOUS valides (+ allongement de pause),
#     donc légitimement court (~2 ḥ) — gate très permissif, plancher bas.
MADD_LOWER_ONLY = {"madd_6", "madd_6_muqattaat", "madd_246"}
# Par règle : (seuil_fiable, seuil_calib).
#   seuil_fiable — en NOTATION, une tenue plus brève trahit un effondrement
#     d'alignement CTC (voyelle perdue), pas une vraie faute → « missing_audio » ;
#   seuil_calib  — en CALIBRATION, un échantillon de RÉFÉRENCE plus bref est un
#     échec d'alignement → écarté du plancher appris (sinon il le tire vers 0).
# Pour madd_246, valeur valide dès ~2 ḥ : seuils bas pour ne rien écarter de légitime.
_MADD_LOWER_DEFAULT = (1.0, 3.0)
_MADD_LOWER_THRESHOLDS = {
    "madd_6":           (1.0, 3.0),
    "madd_6_muqattaat": (1.0, 3.0),
    "madd_246":         (0.3, 0.8),
}


def madd_reliable_floor(rule: str) -> float:
    """ḥarakāt en dessous desquelles une mesure de madd est jugée non fiable."""
    return _MADD_LOWER_THRESHOLDS.get(rule, _MADD_LOWER_DEFAULT)[0]


def madd_calib_floor(rule: str) -> float:
    """ḥarakāt en dessous desquelles un échantillon de référence est écarté."""
    return _MADD_LOWER_THRESHOLDS.get(rule, _MADD_LOWER_DEFAULT)[1]


# Le madd lāzim des lettres muqattaʿāt (الٓمٓ …) est trop instable à aligner
# (≈70 % d'effondrements, tenue jusqu'à 200+ ḥ) : on le MESURE à titre indicatif
# mais on ne le NOTE pas.
ADVISORY_RULES = {"madd_6_muqattaat"}


def is_lower_only(rule: str) -> bool:
    """Règles notées à sens unique (jamais « trop long »). Deux familles :
    - madd ā tenue libre (madd_6, madd_246 : allongement de pause/style légitime) ;
    - ghunnah/nasales : c'est la NASALITÉ, pas la durée, qui gouverne la qualité ;
      une tenue nasale plus longue n'est pas une faute, et la mesure de durée
      inter-onset y est trop bruitée (même نّ mesuré 2.7–7.5 ḥ selon le débit).
    La durée reste une borne BASSE (repère de sous-tenue), jamais une borne haute."""
    return rule in MADD_LOWER_ONLY or rule in GHUNNAH_RULES

GHUNNAH_HARAKAT = (1.3, 2.7)        # tenue nasale ~2 ḥarakāt
HARAKA_TOL = 0.8                    # tolérance (ḥarakāt) avant de signaler
NASALITY_BAND_HZ = 1000.0          # bande « basse » pour le murmure nasal
NASALITY_MIN = 0.55                # part d'énergie basse attendue pour une ghunnah


def _seg_duration(al: Alignment, seg: GTSegment) -> Optional[float]:
    span = al.span_for_lenient(seg.start_idx, seg.end_idx)
    return None if span is None else span[1] - span[0]


def estimate_haraka_unit(al: Alignment, segments: Sequence[GTSegment]
                         ) -> Optional[float]:
    """Durée (s) d'UNE ḥaraka, estimée dans la récitation.

    Priorité aux segments madd_2 (= 2 ḥarakāt par définition). À défaut, on
    retombe sur la durée médiane par caractère timé hors segments spéciaux.
    """
    madd2 = [d for s in segments if s.rule == "madd_2"
             for d in (_seg_duration(al, s),) if d and d > 0]
    if madd2:
        return statistics.median(madd2) / 2.0

    special = set()
    for s in segments:
        if s.rule in MADD_HARAKAT or s.rule in GHUNNAH_RULES or s.rule == "silent":
            special.update(range(s.start_idx, s.end_idx))
    per_char = [t1 - t0 for i, sp in enumerate(al.char_spans)
                if sp is not None and i not in special
                for (t0, t1) in (sp,) if t1 - t0 > 0]
    return statistics.median(per_char) if per_char else None


def _nasality(waveform: Optional[Sequence[float]], sr: Optional[int],
              span: Tuple[float, float]) -> Optional[float]:
    """Part d'énergie spectrale sous NASALITY_BAND_HZ sur [t0,t1]. None si pas
    de forme d'onde / numpy. Les nasales ont un fort murmure basse-fréquence."""
    if waveform is None or sr is None:
        return None
    try:
        import numpy as np
    except ImportError:  # pragma: no cover
        return None
    t0, t1 = span
    a, b = int(t0 * sr), int(t1 * sr)
    seg = np.asarray(waveform[a:b], dtype=float)
    if seg.size < 32:
        return None
    spec = np.abs(np.fft.rfft(seg * np.hanning(seg.size)))
    freqs = np.fft.rfftfreq(seg.size, 1.0 / sr)
    total = float(spec.sum()) or 1e-9
    low = float(spec[freqs < NASALITY_BAND_HZ].sum())
    return low / total


def _status(measured: float, lo: float, hi: float,
            lower_only: bool = False) -> Tuple[str, str]:
    if measured < lo - HARAKA_TOL:
        attendu = f"≥{lo:g}" if lower_only else f"{lo:g}–{hi:g}"
        return "warn", f"trop court ({measured:.1f}, attendu {attendu})"
    if not lower_only and measured > hi + HARAKA_TOL:
        return "warn", f"trop long ({measured:.1f}, attendu {lo:g}–{hi:g})"
    attendu = f"≥{lo:g}" if lower_only else f"{lo:g}–{hi:g}"
    return "ok", f"{measured:.1f} ḥarakāt (attendu {attendu})"


def _band_for(rule: str, calibration: Optional[dict]
              ) -> Tuple[float, float, str, Optional[float]]:
    """(lo, hi ḥarakāt, libellé attendu, nasalité_min). La calibration (apprise
    sur le corpus de référence) prime sur les valeurs « manuel »."""
    lower_only = is_lower_only(rule)
    if calibration and rule in calibration.get("rules", {}):
        c = calibration["rules"][rule]
        nas_min = (c.get("nasality") or {}).get("lo") if rule in GHUNNAH_RULES else None
        label = (f"≥{c['lo']:.1f} ḥ (calibré, n={c['n']})" if lower_only
                 else f"{c['lo']:.1f}–{c['hi']:.1f} ḥ (calibré, n={c['n']})")
        return c["lo"], c["hi"], label, nas_min
    if rule in MADD_HARAKAT:
        lo, hi = MADD_HARAKAT[rule]
        if lower_only:
            label = f"≥{lo:g} ḥarakāt"
        else:
            label = f"≈{lo:g}–{hi:g} ḥarakāt" if lo != hi else f"{lo:g} ḥarakāt"
        return lo, hi, label, None
    lo, hi = GHUNNAH_HARAKAT
    return lo, hi, "≈2 ḥarakāt nasal", NASALITY_MIN


def measure_segment(al: Alignment, seg: GTSegment, unit: Optional[float],
                    waveform: Optional[Sequence[float]] = None,
                    sr: Optional[int] = None,
                    calibration: Optional[dict] = None,
                    surah: Optional[int] = None,
                    ayah: Optional[int] = None) -> Optional[SegmentResult]:
    """Mesure une règle de madd ou de ghunnah. None si la règle n'est pas couverte v1.

    Si `calibration` est fourni, les bornes attendues viennent du corpus de
    référence (médiane ± k·MAD par règle) au lieu des valeurs « manuel », ce qui
    absorbe le biais systématique de la mesure inter-onset.

    `surah`/`ayah` (optionnels) servent à reclasser le madd_6 muqattaʿāt en
    « madd_6_muqattaat », noté et gradé contre sa propre bande (plus permissive).
    """
    is_madd = seg.rule in MADD_HARAKAT
    is_ghunnah = seg.rule in GHUNNAH_RULES
    if not (is_madd or is_ghunnah):
        return None

    eff_rule = effective_rule(seg.rule, surah, ayah)
    span = al.span_for_lenient(seg.start_idx, seg.end_idx)
    base = SegmentResult(rule=eff_rule, start_idx=seg.start_idx, end_idx=seg.end_idx,
                         segment=seg.segment, expected="", measured="—")
    if span is None or unit is None or unit <= 0:
        base.status = "missing_audio"
        base.message = "pas d'alignement audio pour ce segment"
        base.expected = "n/a"
        return base

    dur = span[1] - span[0]
    measured = dur / unit
    base.measured_harakat = measured
    lo, hi, expected, nas_min = _band_for(eff_rule, calibration)
    base.expected = expected
    is_madd_lower = eff_rule in MADD_LOWER_ONLY
    lower_only = is_lower_only(eff_rule)

    if eff_rule in ADVISORY_RULES:
        # muqattaʿāt : mesuré à titre indicatif, jamais noté (aligneur non fiable).
        base.status = "ok"
        base.message = f"{measured:.1f} ḥarakāt (indicatif — muqattaʿāt non noté)"
    elif is_madd_lower and measured < madd_reliable_floor(eff_rule):
        # tenue quasi nulle → effondrement d'alignement, pas une vraie faute.
        base.status = "missing_audio"
        base.message = f"tenue trop brève pour être fiable ({measured:.1f} ḥ) — alignement douteux"
    else:
        base.status, base.message = _status(measured, lo, hi, lower_only)

    if is_ghunnah:
        nas = _nasality(waveform, sr, span)
        base.nasality = nas
        if nas is not None and nas_min is not None and nas < nas_min and base.status == "ok":
            base.status = "warn"
            base.message = f"nasalité faible ({nas:.2f}), durée ok ({measured:.1f})"
        base.measured = (f"{measured:.1f} ḥarakāt ({dur:.2f}s)"
                         + (f", nasalité {nas:.2f}" if nas is not None else ""))
    else:
        base.measured = f"{measured:.1f} ḥarakāt ({dur:.2f}s)"
    return base


def measure_all(al: Alignment, segments: Sequence[GTSegment],
                waveform: Optional[Sequence[float]] = None,
                sr: Optional[int] = None,
                calibration: Optional[dict] = None,
                surah: Optional[int] = None,
                ayah: Optional[int] = None
                ) -> Tuple[List[SegmentResult], Optional[float]]:
    unit = estimate_haraka_unit(al, segments)
    out: List[SegmentResult] = []
    for seg in segments:
        r = measure_segment(al, seg, unit, waveform, sr, calibration, surah, ayah)
        if r is not None:
            out.append(r)
    return out, unit
