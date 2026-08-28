# -*- coding: utf-8 -*-
"""
tests/test_correction.py — Moteur de correction Tajweed (cœur déterministe).

Aucun modèle ML : on fabrique des `Alignment` contrôlés et un aligneur
synthétique pour valider mapping offset→temps, estimation de l'unité ḥaraka,
mesure Madd/Ghunnah, filtrage des règles hors-v1, et structure du rapport.

Exécution :
    pytest -q
    python tests/test_correction.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from tajweed.correction.types import Alignment            # noqa: E402
from tajweed.correction.ground_truth import GTSegment     # noqa: E402
from tajweed.correction import rules                       # noqa: E402
from tajweed.correction.aligner import SyntheticAligner, text_to_tokens  # noqa: E402
from tajweed.correction.content_check import (             # noqa: E402
    char_error_rate, check_content, CONTENT_MISMATCH_CER, locate_best_span)
from tajweed.correction.word_score import (                 # noqa: E402
    split_words, score_words)
from tajweed.correction.ground_truth import AyahSpan, RangeGroundTruth  # noqa: E402
from tajweed.correction.evaluate import evaluate_window, evaluate_clip  # noqa: E402


def build_alignment(items):
    """items: [(char, dur|None)] → Alignment à timing consécutif (None = pas de span)."""
    text = "".join(c for c, _ in items)
    spans = []
    t = 0.0
    for _c, d in items:
        if d is None:
            spans.append(None)
        else:
            spans.append((t, t + d))
            t += d
    return Alignment(text, spans, t)


# ------------------------------ mapping ------------------------------------

def test_span_for_offsets():
    al = build_alignment([("ا", 0.2), ("ل", 0.3), (" ", None), ("م", 0.5)])
    assert al.span_for(0, 1) == (0.0, 0.2)
    assert al.span_for(0, 2) == (0.0, 0.5)        # ا..ل
    assert al.span_for(2, 3) is None              # l'espace seul → pas de timing
    assert al.span_for(3, 4) == (0.5, 1.0)        # م


def test_alignment_length_guard():
    try:
        Alignment("abc", [(0.0, 0.1)], 0.1)
    except ValueError:
        return
    raise AssertionError("longueur incohérente non détectée")


# -------------------------- unité ḥaraka -----------------------------------

def test_haraka_unit_from_madd2():
    # un madd_2 d'une lettre tenue 0.4s → unité = 0.2s.
    al = build_alignment([("و", 0.4), ("ا", 0.2)])
    segs = [GTSegment("madd_2", 0, 1, "و")]
    assert abs(rules.estimate_haraka_unit(al, segs) - 0.2) < 1e-9


def test_haraka_unit_fallback_without_madd2():
    al = build_alignment([("ا", 0.2), ("ل", 0.2), ("م", 0.2)])
    unit = rules.estimate_haraka_unit(al, [])
    assert abs(unit - 0.2) < 1e-9


# ----------------------------- Madd ----------------------------------------

def test_madd6_ok_and_too_short():
    # unité 0.2 via madd_2 ; madd_6 attendu ~6 ḥarakāt = 1.2s.
    al = build_alignment([
        ("و", 0.4),    # 0: madd_2 ref (2 ḥ)
        ("ا", 1.2),    # 1: madd_6 correct (6 ḥ)
        ("ي", 0.4),    # 2: madd_6 trop court (2 ḥ)
    ])
    segs = [GTSegment("madd_2", 0, 1, "و"),
            GTSegment("madd_6", 1, 2, "ا"),
            GTSegment("madd_6", 2, 3, "ي")]
    res, unit = rules.measure_all(al, segs)
    assert abs(unit - 0.2) < 1e-9
    by_idx = {r.start_idx: r for r in res}
    assert by_idx[1].status == "ok" and abs(by_idx[1].measured_harakat - 6.0) < 0.1
    assert by_idx[2].status == "warn" and "court" in by_idx[2].message


def test_muqattaat_madd6_split():
    from tajweed.correction.rules import effective_rule, MUQATTAAT_AYAHS
    # reclassement direct
    assert effective_rule("madd_6", 2, 1) == "madd_6_muqattaat"     # الٓمٓ
    assert effective_rule("madd_6", 112, 1) == "madd_6"             # sourate non-muqattaʿāt
    assert effective_rule("madd_2", 2, 1) == "madd_2"               # autre règle intacte
    assert (2, 1) in MUQATTAAT_AYAHS and (42, 2) in MUQATTAAT_AYAHS

    # un madd_6 SOUS-tenu (2 ḥ) : « warn trop court » en madd lāzim, mais seulement
    # « indicatif » (non noté) sur des lettres muqattaʿāt (aligneur non fiable).
    al = build_alignment([("و", 0.4), ("م", 0.4)])   # unit .2 via madd_2 ; 0.4/.2 = 2 ḥ
    segs = [GTSegment("madd_2", 0, 1, "و"), GTSegment("madd_6", 1, 2, "م")]
    res_plain, _ = rules.measure_all(al, segs)                      # sans contexte ayah
    m_plain = [r for r in res_plain if r.rule == "madd_6"][0]
    assert m_plain.status == "warn" and "court" in m_plain.message

    res_muq, _ = rules.measure_all(al, segs, surah=2, ayah=1)
    assert not any(r.rule == "madd_6" for r in res_muq)             # plus de madd_6 brut
    m_muq = [r for r in res_muq if r.rule == "madd_6_muqattaat"][0]
    assert m_muq.status == "ok" and abs(m_muq.measured_harakat - 2.0) < 0.1


def test_madd6_one_sided_gate():
    # Le madd lāzim est noté À SENS UNIQUE : seul le sous-allongement est une faute.
    # Tenu très long (15 ḥ) → correct (jamais « trop long »).
    al = build_alignment([("و", 0.4), ("ا", 3.0)])   # unit .2 ; 3.0/.2 = 15 ḥ
    segs = [GTSegment("madd_2", 0, 1, "و"), GTSegment("madd_6", 1, 2, "ا")]
    m = [r for r in rules.measure_all(al, segs)[0] if r.rule == "madd_6"][0]
    assert m.status == "ok" and abs(m.measured_harakat - 15.0) < 0.1

    # Tenue quasi nulle (<1 ḥ) → effondrement d'alignement : mesure douteuse, pas faute.
    al2 = build_alignment([("و", 0.4), ("ا", 0.1)])  # 0.1/.2 = 0.5 ḥ < seuil fiable
    segs2 = [GTSegment("madd_2", 0, 1, "و"), GTSegment("madd_6", 1, 2, "ا")]
    m2 = [r for r in rules.measure_all(al2, segs2)[0] if r.rule == "madd_6"][0]
    assert m2.status == "missing_audio"


def test_madd246_one_sided():
    # madd ʿāriḍ/līn tenu long à la pause (10 ḥ) : valide (2/4/6 + allongement),
    # jamais « trop long ». Avant le passage à sens unique, ceci warnait.
    al = build_alignment([("و", 0.4), ("ا", 2.0)])   # unit .2 ; 2.0/.2 = 10 ḥ
    segs = [GTSegment("madd_2", 0, 1, "و"), GTSegment("madd_246", 1, 2, "ا")]
    m = [r for r in rules.measure_all(al, segs)[0] if r.rule == "madd_246"][0]
    assert m.status == "ok" and "≥" in m.expected


def test_madd_muttasil_range():
    al = build_alignment([("و", 0.4), ("ا", 0.9)])  # unit .2 ; 0.9/.2=4.5 ḥ
    segs = [GTSegment("madd_2", 0, 1, "و"), GTSegment("madd_muttasil", 1, 2, "ا")]
    res, _ = rules.measure_all(al, segs)
    mutt = [r for r in res if r.rule == "madd_muttasil"][0]
    assert mutt.status == "ok"  # 4.5 ∈ [4,5]


# ---------------------------- Ghunnah --------------------------------------

def test_ghunnah_duration_only():
    al = build_alignment([("و", 0.4), ("ن", 0.4)])  # unit .2 ; 0.4/.2 = 2 ḥ
    segs = [GTSegment("madd_2", 0, 1, "و"), GTSegment("ghunnah", 1, 2, "ن")]
    res, _ = rules.measure_all(al, segs)             # pas de waveform → nasalité None
    gh = [r for r in res if r.rule == "ghunnah"][0]
    assert gh.status == "ok"
    assert gh.nasality is None
    assert abs(gh.measured_harakat - 2.0) < 0.1


def test_ghunnah_one_sided_duration():
    # ghunnah tenue longue (5 ḥ, ex. نّ avant un madd, débit rapide) : jamais
    # « trop long » — c'est la nasalité, pas la durée, qui gouverne la ghunnah.
    al = build_alignment([("و", 0.4), ("ن", 1.0)])   # unit .2 ; 1.0/.2 = 5 ḥ
    segs = [GTSegment("madd_2", 0, 1, "و"), GTSegment("ghunnah", 1, 2, "ن")]
    gh = [r for r in rules.measure_all(al, segs)[0] if r.rule == "ghunnah"][0]
    assert gh.status == "ok" and "long" not in gh.message      # jamais « trop long »

    # avec calibration : même tenue longue reste ok, et la bande s'affiche « ≥ ».
    cal = {"rules": {"ghunnah": {"lo": 0.3, "hi": 1.6, "n": 800,
                                 "nasality": {"lo": 0.2}}}}
    gh_c = [r for r in rules.measure_all(al, segs, calibration=cal)[0]
            if r.rule == "ghunnah"][0]
    assert gh_c.status == "ok" and "≥" in gh_c.expected


# -------------------------- filtrage v1 ------------------------------------

def test_noncovered_rules_skipped():
    al = build_alignment([("ا", 0.2), ("ق", 0.2)])
    segs = [GTSegment("qalqalah", 1, 2, "ق"),       # hors v1
            GTSegment("hamzat_wasl", 0, 1, "ا")]    # hors v1
    res, _ = rules.measure_all(al, segs)
    assert res == []


def test_missing_audio_segment():
    # marque seule, AUCUNE lettre timée en amont → vraiment pas d'audio.
    al = build_alignment([("ٰ", None)])
    segs = [GTSegment("madd_6", 0, 1, "ٰ")]
    res, _ = rules.measure_all(al, segs)
    assert res[0].status == "missing_audio"


def test_madd_mark_uses_preceding_letter():
    # madd porté par un alif suscrit (marque) : le timing vient de la lettre d'avant.
    al = build_alignment([("و", 0.4), ("ر", 1.2), ("ٰ", None)])  # unit .2 via madd_2
    segs = [GTSegment("madd_2", 0, 1, "و"),
            GTSegment("madd_6", 2, 3, "ٰ")]   # la marque hérite du span de "ر"
    res, _ = rules.measure_all(al, segs)
    madd6 = [r for r in res if r.rule == "madd_6"][0]
    assert madd6.status == "ok" and abs(madd6.measured_harakat - 6.0) < 0.1


# -------------------------- aligneur synthétique ---------------------------

def test_synthetic_aligner_shapes():
    text = "وَالْفَجْرِ"
    al = SyntheticAligner(duration=2.0).align(Path("dummy.mp3"), text)
    assert len(al.char_spans) == len(text)
    assert al.duration == 2.0
    toks, idx = text_to_tokens(text)
    # exactement les positions-lettres sont timées
    timed = [i for i, s in enumerate(al.char_spans) if s is not None]
    assert timed == idx and len(toks) == len(timed)


# --------------------------- calibration -----------------------------------

def test_summarize_samples_robust_band():
    from tajweed.correction.calibrate import summarize_samples
    samples = {
        "madd_munfasil": {"harakat": [8.0, 8.2, 7.8, 8.1, 7.9, 8.3, 30.0], "nasality": []},
        "ghunnah": {"harakat": [2.0, 2.1, 1.9, 2.0, 2.2, 1.8],
                    "nasality": [0.7, 0.72, 0.68, 0.75, 0.66, 0.8]},
        "madd_2": {"harakat": [2.0, 2.0]},  # < min_n → ignoré
    }
    cal = summarize_samples(samples, k_mad=3.0, min_n=5)
    assert "madd_2" not in cal                       # trop peu d'échantillons
    mun = cal["madd_munfasil"]
    assert abs(mun["median"] - 8.1) < 0.3            # l'aberrant 30 n'a pas tiré la médiane
    assert mun["lo"] < mun["median"] < mun["hi"]
    assert "nasality" in cal["ghunnah"] and cal["ghunnah"]["nasality"]["lo"] > 0


def test_checkpoint_roundtrip_aggregates(tmp_path):
    from tajweed.correction.calibrate import load_checkpoint
    import json as _json
    cp = tmp_path / "cp.jsonl"
    cp.write_text("\n".join([
        _json.dumps({"reciter": "a", "surah": 1, "ayah": 1,
                     "results": [{"rule": "madd_2", "harakat": 2.0, "nasality": None},
                                 {"rule": "ghunnah", "harakat": 1.0, "nasality": 0.3}]}),
        _json.dumps({"reciter": "b", "surah": 1, "ayah": 1, "results": []}),
    ]) + "\n", encoding="utf-8")
    samples, done = load_checkpoint(cp)
    assert done == {("a", 1, 1), ("b", 1, 1)}      # les 2 ayahs marquées faites
    assert samples["madd_2"]["harakat"] == [2.0]
    assert samples["ghunnah"]["nasality"] == [0.3]


def test_calibration_overrides_textbook_band():
    # un madd_munfasil mesuré à 8 ḥarakāt : "warn" en manuel (attendu 4-5),
    # mais "ok" avec une calibration qui a appris une bande autour de 8.
    al = build_alignment([("و", 0.4), ("ا", 1.6)])   # unit .2 via madd_2 ; 1.6/.2 = 8 ḥ
    segs = [GTSegment("madd_2", 0, 1, "و"), GTSegment("madd_munfasil", 1, 2, "ا")]
    res_textbook, _ = rules.measure_all(al, segs)
    mun_tb = [r for r in res_textbook if r.rule == "madd_munfasil"][0]
    assert mun_tb.status == "warn"

    cal = {"rules": {"madd_munfasil": {"lo": 6.0, "hi": 10.0, "n": 50}}}
    res_cal, _ = rules.measure_all(al, segs, calibration=cal)
    mun_cal = [r for r in res_cal if r.rule == "madd_munfasil"][0]
    assert mun_cal.status == "ok" and "calibré" in mun_cal.expected


# ------------------------------ batch mode ---------------------------------

def test_parse_ayah_from_name():
    from tajweed.correction.batch import parse_ayah_from_name
    assert parse_ayah_from_name(Path("001007.mp3")) == (1, 7)
    assert parse_ayah_from_name(Path("2_255.wav")) == (2, 255)
    assert parse_ayah_from_name(Path("recite-112-1.m4a")) == (112, 1)
    assert parse_ayah_from_name(Path("my_002255_take2.mp3")) == (2, 255)  # SSSAAA prioritaire
    assert parse_ayah_from_name(Path("noname.mp3")) is None
    assert parse_ayah_from_name(Path("999_1.mp3")) is None                # sourate hors plage


def test_aggregate_reports():
    from tajweed.correction.batch import aggregate_reports
    from tajweed.correction.types import Report, SegmentResult

    def R(surah, ayah, segs):
        return Report(surah=surah, ayah=ayah, audio_path="x", duration=1.0,
                      haraka_unit_s=0.2, aligner="synthetic", results=segs)

    def S(rule, status):
        return SegmentResult(rule=rule, start_idx=0, end_idx=1, segment="x",
                             expected="", measured="", status=status, message=status)

    reps = [
        R(1, 7, [S("madd_2", "ok"), S("madd_6", "warn"), S("madd_6_muqattaat", "ok")]),
        R(2, 1, [S("ghunnah", "ok"), S("madd_6", "missing_audio")]),
    ]
    br = aggregate_reports(reps, [(Path("bad.mp3"), "illisible")], Path("d"))
    assert br.n_recordings == 2
    assert br.n_ok == 2 and br.n_warn == 1                    # madd_2 + ghunnah ok ; madd_6 warn
    assert br.by_rule["madd_6"] == {"ok": 0, "warn": 1}       # le missing_audio est exclu
    assert br.advisory == {"madd_6_muqattaat": 1}             # indicatif compté à part
    assert len(br.flags) == 1 and br.flags[0]["surah"] == 1 and br.flags[0]["rule"] == "madd_6"
    assert len(br.skipped) == 1
    assert abs(br.pass_rate - 2 / 3) < 1e-9


# ------------------------- vérif. de contenu (Phase 0) ----------------------

def test_cer_identical_ignores_harakat():
    # squelette consonantique identique malgré harakat/tashkeel différents.
    assert char_error_rate("بسم الله", "بِسْمِ اللَّهِ") == 0.0


def test_cer_foreign_language_is_near_max():
    # aucune lettre arabe en commun -> CER proche de 1 (garde-fou du 2026-07-06 :
    # réciter en français/anglais ne doit JAMAIS passer le seuil).
    cer = char_error_rate("hello world how are you today", "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ")
    assert cer > CONTENT_MISMATCH_CER


def test_cer_wrong_ayah_is_high():
    # texte arabe réel mais D'UNE AUTRE AYAH (assez longue/lexicalement distincte
    # pour ne pas juste partager les lettres les + fréquentes de l'arabe) ->
    # doit aussi dépasser le seuil. NOTE (Roadmap V2, décisions ouvertes) :
    # deux ayahs COURTES peuvent partager ~70% de lettres par hasard (ex. 112:1
    # vs 1:1 mesure ~0.74, tout juste sous le seuil 0.75) — cas limite connu à
    # affiner empiriquement plus tard, pas résolu ici.
    cer = char_error_rate(
        "اللَّهُ لَا إِلَٰهَ إِلَّا هُوَ الْحَيُّ الْقَيُّومُ لَا تَأْخُذُهُ سِنَةٌ وَلَا نَوْمٌ",
        "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ")
    assert cer > CONTENT_MISMATCH_CER


def test_check_content_status():
    assert check_content("بسم الله الرحمن الرحيم", "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ")[0] == "ok"
    assert check_content("hello world", "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ")[0] == "content_mismatch"


def _build_spans(ayah_texts):
    """(ayah, text) pairs -> (full_text, [(ayah, start, end), ...]) — the
    shape locate_best_span actually takes (mirrors RangeGroundTruth)."""
    spans, combined = [], ""
    for ayah, text in ayah_texts:
        if combined:
            combined += " "
        start = len(combined)
        combined += text
        spans.append((ayah, start, len(combined)))
    return combined, spans


def test_locate_best_span_finds_matching_ayah():
    full_text, spans = _build_spans([
        (1, "بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ"),
        (2, "ٱلْحَمْدُ لِلَّهِ رَبِّ ٱلْعَٰلَمِينَ"),
        (3, "ٱلرَّحْمَٰنِ ٱلرَّحِيمِ"),
        (4, "مَٰلِكِ يَوْمِ ٱلدِّينِ"),
    ])
    # correct decode of ayah 2 ALONE -> should locate ayah 2 specifically,
    # not drift to a neighboring ayah or span the whole thing.
    rng = locate_best_span("الحمد لله رب العالمين", full_text, spans)
    assert rng[:2] == (2, 2)


def test_locate_best_span_robust_to_scrambled_word_boundaries():
    # Real finding (2026-07-08): a correct decode can have MERGED/SPLIT word
    # boundaries (bad "|" token predictions) even when the letters are right.
    # Word-level matching fails this case entirely; char-level must not.
    full_text, spans = _build_spans([(5, "إِيَّاكَ نَعْبُدُ وَإِيَّاكَ نَسْتَعِينُ")])
    scrambled = "إياك نعب دوإيا كنستعين"   # same letters, wrong spaces
    rng = locate_best_span(scrambled, full_text, spans)
    assert rng[:2] == (5, 5)


def test_locate_best_span_multi_ayah():
    full_text, spans = _build_spans([
        (1, "بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ"),
        (2, "ٱلْحَمْدُ لِلَّهِ رَبِّ ٱلْعَٰلَمِينَ"),
        (3, "ٱلرَّحْمَٰنِ ٱلرَّحِيمِ"),
    ])
    rng = locate_best_span("بسم الله الرحمن الرحيم الحمد لله رب العالمين", full_text, spans)
    assert rng[:2] == (1, 2)


def test_locate_best_span_near_ayah_breaks_tie():
    # Two āyahs with IDENTICAL text -- a genuine tie in match quality, the
    # kind of ambiguity a short phrase that legitimately repeats elsewhere in
    # the SAME sūrah can create (e.g. Al-Fātiḥa's "الرحمن الرحيم", both the
    # tail of āyah 1 and the whole of āyah 3). With no positional hint,
    # either candidate is an equally valid "best" match; `near_ayah` should
    # resolve it toward whichever is closest to the reciter's last-known
    # position, not silently default to whichever happens first (found
    # 2026-07-08: without this, a window's mislocated match could make
    # progress appear to jump ahead of where the reciter actually was).
    full_text, spans = _build_spans([
        (1, "قل هو الله احد"),
        (2, "شيء غير مرتبط"),
        (3, "قل هو الله احد"),
    ])
    decoded = "قل هو الله احد"
    assert locate_best_span(decoded, full_text, spans, near_ayah=1)[:2] == (1, 1)
    assert locate_best_span(decoded, full_text, spans, near_ayah=3)[:2] == (3, 3)


def test_locate_best_span_tail_of_longer_ayah_ties_with_shorter_repeat():
    # Real bug found 2026-07-08 via the rolling-window redesign: a clip that
    # is only the TAIL of a longer āyah (a sliding time window scrolls PAST
    # the āyah's opening once more time passes than the window covers) can
    # coincidentally be a PERFECT match for a DIFFERENT, shorter āyah
    # elsewhere -- e.g. reciting Al-Fātiḥa 1:1 in full, but by the time the
    # window is graded it only still holds "الرحمن الرحيم", which is 1:3's
    # ENTIRE text. PREFIX-only comparison confidently (and wrongly) preferred
    # 1:3, since 1:1 was only ever compared against its own BEGINNING ("بسم
    # الله..."), which isn't in a tail-only clip at all.
    full_text, spans = _build_spans([
        (1, "بسم الله الرحمن الرحيم"),
        (2, "شيء غير مرتبط تماما"),
        (3, "الرحمن الرحيم"),
    ])
    decoded = "الرحمن الرحيم"   # only the TAIL of āyah 1, not the whole thing
    # With no hint, either is now a legitimate near-tie (both near-perfect
    # matches once suffix-awareness is applied) -- with a hint pointing at
    # where the reciter actually still was (āyah 1), it must resolve back to
    # 1, not silently prefer 3 just because that match happens to be exact.
    assert locate_best_span(decoded, full_text, spans, near_ayah=1)[:2] == (1, 1)


def test_locate_best_span_none_for_unrelated_content():
    full_text, spans = _build_spans([(1, "بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ")])
    assert locate_best_span("hello world how are you today", full_text, spans) is None


def test_locate_best_span_partial_recitation_of_long_ayah():
    # Real bug (2026-07-08, found on real Āyat al-Kursī audio): a SHORT clip
    # covering only the BEGINNING of a LONG āyah must still locate that long
    # āyah, not drift to an unrelated SHORT āyah that happens to be closer in
    # length. No shared words between the two fixture āyahs, unlike an
    # earlier version of this test that accidentally reused "جدا" in both.
    full_text, spans = _build_spans([
        (10, "بسم الله الرحمن الرحيم"),                                    # short, unrelated
        (11, "الحمد لله رب العالمين الرحمن الرحيم مالك يوم الدين"),          # long
    ])
    partial_decode = "الحمد لله رب"   # only the OPENING of ayah 11 was "recited"
    rng = locate_best_span(partial_decode, full_text, spans)
    assert rng[:2] == (11, 11)


def test_evaluate_skips_grading_on_content_mismatch():
    # SyntheticAligner ne décode jamais (decoded_text=None) -> content_status
    # reste "unknown" et la notation Tajweed tourne normalement (pas de ML
    # disponible pour juger le contenu). On simule ici un aligneur "menteur"
    # qui décode du texte étranger pour vérifier le court-circuit d'evaluate().
    from tajweed.correction.evaluate import evaluate
    from tajweed.correction.ground_truth import GroundTruth

    class FakeMismatchAligner:
        name = "fake"

        def align(self, audio_path, text):
            return Alignment(text=text, char_spans=[None] * len(text),
                             duration=3.0, decoded_text="hello world")

    class FakeSource:
        def get(self, surah, ayah):
            text = "قُلْ هُوَ اللَّهُ أَحَدٌ"
            return GroundTruth(surah, ayah, text,
                               [GTSegment("madd_2", 0, 1, text[0])])

    rep = evaluate(Path("dummy.wav"), 112, 1, FakeMismatchAligner(), FakeSource())
    assert rep.content_status == "content_mismatch"
    assert rep.results == []                 # notation court-circuitée
    assert rep.content_cer is not None and rep.content_cer > CONTENT_MISMATCH_CER


# ---------------------- notation par mot (Phase 1) ---------------------------

def test_split_words_offsets():
    text = "بِسْمِ اللَّهِ الرَّحِيمِ"
    words = split_words(text)
    assert [w for w, _, _ in words] == ["بِسْمِ", "اللَّهِ", "الرَّحِيمِ"]
    for w, s, e in words:
        assert text[s:e] == w                 # offsets réutilisables tels quels


def test_split_words_multiple_spaces():
    words = split_words("  ا  ب ")             # espaces multiples/en bord
    assert [w for w, _, _ in words] == ["ا", "ب"]


def test_score_words_exact_match():
    text = "بسم الله الرحيم"
    scores = score_words(text, text, [])
    assert all(s.content_ok for s in scores)


def test_score_words_substitution_and_deletion():
    text = "بسم الله الرحيم"
    # "الله" supprimé (raté) -> RED ; les mots autour restent verts.
    scores = score_words(text, "بسم الرحيم", [])
    by_word = {s.word: s.content_ok for s in scores}
    assert by_word == {"بسم": True, "الله": False, "الرحيم": True}

    # "الله" substitué par un mot vraiment différent -> toujours RED.
    scores2 = score_words(text, "بسم شيء الرحيم", [])
    by_word2 = {s.word: s.content_ok for s in scores2}
    assert by_word2 == {"بسم": True, "الله": False, "الرحيم": True}


def test_score_words_extra_insertion_does_not_break_others():
    text = "بسم الله"
    # mot en trop en tête dans le décodage -> n'affecte pas les mots de ref.
    scores = score_words(text, "يا بسم الله", [])
    assert all(s.content_ok for s in scores)


def test_score_words_ignores_harakat():
    # harakat différents mais même squelette consonantique -> matché quand même.
    scores = score_words("بِسْمِ", "بسم", [])
    assert all(s.content_ok for s in scores)


def test_score_words_tolerates_fused_words_no_space():
    # LE bug trouvé sur la 1ère vraie session micro (2026-07-08) : sur un
    # décodage CONTINU (plusieurs ayahs à la suite), le token de séparation
    # "|" du CTC glouton peut disparaître entre deux mots ("الرحيم"+"الحمد"
    # -> "الرحيالحمد", aucun espace) même si les DEUX mots sont bien
    # récités. Un alignement niveau MOT casse là-dessus ; l'alignement
    # niveau CARACTÈRE ne doit PAS en souffrir, puisqu'il ne dépend jamais
    # des espaces prédits par le décodeur.
    text = "الرحيم الحمد لله"
    decoded = "الرحيالحمد لله"   # espace manquant entre "الرحيم" et "الحمد"
    scores = score_words(text, decoded, [])
    assert all(s.content_ok for s in scores)


def test_score_words_catches_missing_word_amid_fusion():
    # Même scénario de fusion, mais un mot RÉELLEMENT absent (pas juste mal
    # séparé) doit quand même ressortir rouge — la tolérance à la fusion ne
    # doit pas devenir une tolérance à un mot manquant.
    text = "الرحيم الحمد لله رب العالمين"
    decoded = "الرحيالحمد لله"    # "رب العالمين" jamais prononcés
    scores = score_words(text, decoded, [])
    by_word = {s.word: s.content_ok for s in scores}
    assert by_word["الرحيم"] and by_word["الحمد"] and by_word["لله"]
    assert not by_word["رب"] and not by_word["العالمين"]


def test_score_words_excludes_unreached_tail_of_long_ayah():
    # Real bug found 2026-07-08 via the rolling-window redesign: a clip only
    # ever covers what's been recited SO FAR -- for a long, multi-word āyah
    # (Al-Fātiḥa 1:7, the longest, 9 words) still being recited word by
    # word, the trailing NOT-YET-SPOKEN words used to show up RED (global
    # character alignment treats "no audio for this yet" the same as "wrong
    # word"), making it look like the reciter had already failed before they
    # even finished. A word substantially beyond where the decode's content
    # actually reaches must be OMITTED from the result, not marked red — see
    # NOT_REACHED_SLACK. (The word immediately following what WAS decoded is
    # deliberately NOT covered by this test — from a single clip alone
    # there's no way to tell "hasn't been said yet" from "recitation
    # genuinely stopped here", and test_score_words_catches_missing_word_
    # amid_fusion above requires that adjacent case to still read as a
    # mismatch. This test is about the FAR tail, several words out, which is
    # unambiguous either way.)
    text = "صراط الذين انعمت عليهم غير المغضوب عليهم ولا الضالين"
    decoded = "صراط الذين انعمت"   # only the first 3 of 9 words recited so far
    scores = score_words(text, decoded, [])
    by_word = {s.word: s for s in scores}
    assert by_word["صراط"].content_ok
    assert by_word["الذين"].content_ok
    assert by_word["انعمت"].content_ok
    # Several words further out clearly haven't been reached yet -- must be
    # absent from the report entirely, not present-and-red.
    for missing in ("المغضوب", "ولا", "الضالين"):
        assert missing not in by_word, f"{missing!r} should be omitted, not graded"


def test_score_words_red_on_mismatch_yellow_on_tajweed_warn():
    from tajweed.correction.types import SegmentResult
    text = "بسم الله الرحيم"
    # "الله" mal reconnu (décodage l'omet) -> RED, quel que soit le tajweed dessus.
    decoded = "بسم شيء الرحيم"
    rules_ = [SegmentResult(rule="madd_2", start_idx=text.index("الرحيم"),
                            end_idx=len(text), segment="ي",
                            expected="", measured="", status="warn", message="court")]
    scores = score_words(text, decoded, rules_)
    by_word = {s.word: s for s in scores}
    assert by_word["الله"].verdict == "red" and not by_word["الله"].content_ok
    assert by_word["الرحيم"].verdict == "yellow"   # reconnu mais règle "warn" dessus
    assert by_word["بسم"].verdict == "green"       # reconnu, aucune règle dessus


def test_score_words_unknown_aligner_defaults_content_ok():
    # decoded_text=None (SyntheticAligner) -> pas de garde-fou contenu, tout "ok".
    text = "بسم الله"
    scores = score_words(text, None, [])
    assert all(s.content_ok and s.verdict == "green" for s in scores)


def test_score_words_strips_basmala_prefix_on_ayah1():
    # Le dataset préfixe la basmala au TEXTE de l'ayah 1 (sauf sourates 1 et 9)
    # alors que l'AUDIO l'omet en général -> ces 4 mots ne doivent PAS être
    # notés (ni "red" à tort, ni présents du tout dans le rapport). Trouvé en
    # validant sur 112:1 réel (2026-07-06) : sans ce correctif, les 4 mots de
    # la basmala ressortaient "red" sur une récitation pourtant parfaite.
    text = "بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ قُلْ هُوَ ٱللَّهُ أَحَدٌ"
    decoded = "قل هو الله احد"     # l'audio réel ne contient QUE l'ayah, pas la basmala
    scores = score_words(text, decoded, [], surah=112, ayah=1)
    assert len(scores) == 4                              # basmala exclue, pas notée
    assert all(s.verdict == "green" for s in scores)
    assert [s.word for s in scores] == ["قُلْ", "هُوَ", "ٱللَّهُ", "أَحَدٌ"]

    # sourate 1 (la basmala EST l'ayah) : pas de préfixe à retirer.
    text_fatiha = "بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ"
    scores_fatiha = score_words(text_fatiha, "بسم الله الرحمن الرحيم", [], surah=1, ayah=1)
    assert len(scores_fatiha) == 4                        # rien retiré


def test_score_words_catches_short_ayah_mismatch_word_level():
    # Le CER global (Phase 0) peut rester sous le seuil sur deux ayahs courtes
    # (cf. Roadmap V2, cas 1:1 audio vs 112:1 texte mesuré cer=0.43 < 0.75,
    # donc "ok" à tort). La notation PAR MOT doit quand même l'attraper.
    text_112 = "قُلْ هُوَ ٱللَّهُ أَحَدٌ"
    decoded_basmala = "بسم الله الرحمن الرحيم"   # audio réel = 1:1, PAS 112:1
    scores = score_words(text_112, decoded_basmala, [], surah=112, ayah=1)
    assert all(s.verdict == "red" for s in scores)        # aucun mot ne correspond


# --------------------- fenêtre multi-ayah (continuous recitation) -----------

class _FakeWindowAligner:
    """Renvoie un decoded_text FIXE, quel que soit l'audio — pour tester la
    logique de evaluate_window (confirmed_ayahs) sans modèle ML."""
    name = "fake"

    def __init__(self, decoded: str):
        self.decoded = decoded

    def align(self, audio_path, text):
        return Alignment(text=text, char_spans=[None] * len(text),
                         duration=5.0, decoded_text=self.decoded)


class _FakeRangeSource:
    """Vérité terrain à 2 ayahs courtes fixes, pour tester confirmed_ayahs
    sans dépendre du vrai corpus."""

    def get_range(self, surah, start_ayah, count):
        texts = ["بسم الله", "قل هو"][:count]
        spans, combined = [], ""
        for i, t in enumerate(texts):
            if combined:
                combined += " "
            s = len(combined)
            combined += t
            spans.append(AyahSpan(start_ayah + i, s, len(combined)))
        return RangeGroundTruth(surah, start_ayah, start_ayah + len(texts) - 1,
                                combined, [], spans)


class _FakeClipAligner:
    """decode()/align_from_decode() fixes — pour tester evaluate_clip sans
    modèle ML (pas de forced_align réel : Alignment vide, seul decoded_text
    compte pour la localisation testée ici)."""
    name = "fake"

    def __init__(self, decoded_text: str, duration: float = 5.0):
        self._decoded_text = decoded_text
        self._duration = duration

    def decode(self, audio_path):
        from types import SimpleNamespace
        return SimpleNamespace(decoded_text=self._decoded_text, duration=self._duration)

    def align_from_decode(self, decoded, text):
        return Alignment(text=text, char_spans=[None] * len(text),
                         duration=decoded.duration, decoded_text=decoded.decoded_text)


def test_evaluate_clip_locates_and_grades_without_start_ayah():
    # PAS de start_ayah fourni -- evaluate_clip doit trouver seul QUELLE ayah
    # correspond (ici la 2e, "قل هو"), à partir du contenu décodé seul.
    rep = evaluate_clip(Path("dummy.wav"), 1, _FakeClipAligner("قل هو"), _FakeRangeSource())
    assert rep.located and rep.ayah_from == 2 and rep.ayah_to == 2


def test_evaluate_clip_superset_window_not_preferred_even_near_earlier_ayah():
    # Régression 2026-07-11 (piège superset, variante near_ayah) : la fenêtre
    # (1,2) matche « قل هو » avec le MÊME CER parfait que (2,2) via le
    # suffix-fit (l'ayah 1 entière absorbée par le gap libre = zéro caractère
    # apparié). Même avec near_ayah=1 (dont |1-1|=0 favoriserait ayah_from=1),
    # la fenêtre superset doit être ÉLAGUÉE avant le tie-break — prétendre
    # que l'ayah 1 a été récitée sans aucune preuve n'est jamais correct.
    rep = evaluate_clip(Path("dummy.wav"), 1, _FakeClipAligner("قل هو"),
                        _FakeRangeSource(), near_ayah=1)
    assert rep.located and rep.ayah_from == 2 and rep.ayah_to == 2


def test_evaluate_clip_not_located_returns_content_mismatch():
    rep = evaluate_clip(Path("dummy.wav"), 1, _FakeClipAligner("hello world"), _FakeRangeSource())
    assert not rep.located and rep.content_status == "content_mismatch"


class _FakeClipAlignerCTCFail(_FakeClipAligner):
    """align_from_decode raises torchaudio's real "targets length is too
    long for CTC" RuntimeError — reproduces a live bug found 2026-07-09: a
    short/near-silent trailing clip (from continuous listening picking up a
    stray blip right after a real recitation) got matched by locate_best_span
    against a comparatively long candidate span, and forced_align crashed
    instead of the mismatch being handled gracefully. Surfaced to the end
    user as a raw 422 ("Échec de l'analyse audio : ... targets length...")
    with a ✅ already showing for the PRIOR, real, correct recitation —
    confusing and alarming for no real reason, since this is just a bad
    location, not a hard failure."""

    def align_from_decode(self, decoded, text):
        raise RuntimeError(
            "targets length is too long for CTC. Found log_probs length: 65, "
            "targets length: 120, and number of repeats: 4"
        )


def test_evaluate_clip_ctc_forced_align_failure_reads_as_not_located():
    rep = evaluate_clip(Path("dummy.wav"), 1, _FakeClipAlignerCTCFail("بسم الله"), _FakeRangeSource())
    assert not rep.located and rep.content_status == "content_mismatch"


class _FakeClipAlignerOtherRuntimeError(_FakeClipAligner):
    """A RuntimeError NOT matching the CTC-too-long message — must still
    propagate. Guards against the CTC-specific catch in evaluate_clip
    accidentally swallowing every RuntimeError and masking real bugs."""

    def align_from_decode(self, decoded, text):
        raise RuntimeError("some unrelated real failure")


def test_evaluate_clip_unrelated_runtime_error_still_propagates():
    try:
        evaluate_clip(Path("dummy.wav"), 1, _FakeClipAlignerOtherRuntimeError("بسم الله"), _FakeRangeSource())
    except RuntimeError as e:
        assert "unrelated real failure" in str(e)
        return
    raise AssertionError("unrelated RuntimeError was swallowed instead of propagating")


def test_evaluate_clip_to_dict_rebases_offsets_per_ayah():
    # Un clip localisé sur PLUSIEURS ayahs (1-2, "بسم الله" + "قل هو") ne doit
    # PAS renvoyer au frontend des start_idx/end_idx relatifs au début de
    # toute la plage -- GradedSurah.tsx les traite comme des offsets dans le
    # texte de CHAQUE verset pris isolément. Sans rebasage, les mots de
    # l'ayah 2 ("قل"/"هو") auraient un start_idx décalé de la longueur de
    # l'ayah 1 ("بسم الله "), bien au-delà de la longueur de leur propre
    # texte "قل هو" -> ne se colorent jamais côté UI (trouvé 2026-07-08 sur
    # une vraie session micro).
    rep = evaluate_clip(Path("dummy.wav"), 1, _FakeClipAligner("بسم الله قل هو"),
                        _FakeRangeSource())
    assert rep.located and rep.ayah_from == 1 and rep.ayah_to == 2
    words = rep.to_dict()["word_scores"]
    by_word = {w["word"]: w for w in words}
    assert by_word["قل"]["ayah"] == 2 and by_word["هو"]["ayah"] == 2
    # "قل هو" ne fait que 5 caractères -- tout start_idx/end_idx doit rester
    # DANS cette longueur, pas décalé par l'ayah 1 qui la précède.
    assert 0 <= by_word["قل"]["start_idx"] < by_word["قل"]["end_idx"] <= len("قل هو")
    assert 0 <= by_word["هو"]["start_idx"] < by_word["هو"]["end_idx"] <= len("قل هو")


def test_evaluate_window_confirms_majority_at_boundary():
    # ayah 1 fully matches; ayah 2 matches exactly 1/2 words (50%) -> the
    # >= threshold is INCLUSIVE, so ayah 2 should still be confirmed.
    rep = evaluate_window(Path("dummy.wav"), 1, 1,
                          _FakeWindowAligner("بسم الله قل غير"),
                          _FakeRangeSource(), count=2)
    assert rep.confirmed_ayahs == [1, 2]


def test_evaluate_window_stops_on_genuine_miss():
    # ayah 1 fully matches; ayah 2 has 0/2 words matching -> confirmed prefix
    # must stop at ayah 1, NOT include a clearly-wrong ayah 2.
    rep = evaluate_window(Path("dummy.wav"), 1, 1,
                          _FakeWindowAligner("بسم الله غير غير"),
                          _FakeRangeSource(), count=2)
    assert rep.confirmed_ayahs == [1]


def test_evaluate_window_resumes_past_a_stuck_start_ayah():
    # ayah 1 totally fails (0/2 words) -> confirmed_ayahs empty, would
    # otherwise strand the cursor forever. ayah 2 shows STRONG evidence
    # (2/2) despite the gap -> resume_ayah should skip past it (= 3), not
    # leave the caller stuck retrying ayah 1 against ever-later audio.
    rep = evaluate_window(Path("dummy.wav"), 1, 1,
                          _FakeWindowAligner("غير غير قل هو"),
                          _FakeRangeSource(), count=2)
    assert rep.confirmed_ayahs == []
    assert rep.resume_ayah == 3


def test_evaluate_window_no_resume_when_nothing_matches():
    # Nothing in the window matches at all -> no false rescue; resume_ayah
    # must stay None (better to keep retrying than to jump on pure noise).
    rep = evaluate_window(Path("dummy.wav"), 1, 1,
                          _FakeWindowAligner("غير غير غير غير"),
                          _FakeRangeSource(), count=2)
    assert rep.confirmed_ayahs == []
    assert rep.resume_ayah is None


def test_evaluate_window_word_ayah_tagging():
    rep = evaluate_window(Path("dummy.wav"), 1, 1,
                          _FakeWindowAligner("بسم الله قل هو"),
                          _FakeRangeSource(), count=2)
    by_word = {w.word: rep._ayah_for(w.start_idx) for w in rep.word_scores}
    assert by_word["بسم"] == 1 and by_word["الله"] == 1
    assert by_word["قل"] == 2 and by_word["هو"] == 2


# ----------------------------- runner --------------------------------------

def _run_without_pytest() -> int:
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  FAIL  {t.__name__}: {e!r}")
    print(f"\n{len(tests) - failed}/{len(tests)} tests passés.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_without_pytest())
