# -*- coding: utf-8 -*-
"""
src/tajweed/correction/content_check.py — Vérification de contenu (Roadmap V2, Phase 0).

Le forced-alignment ne vérifie jamais QUOI a été dit : il étire le texte
ATTENDU sur l'audio fourni et ne mesure QUE la durée. Conséquence démontrée le
2026-07-06 : réciter du français/anglais (ou une autre ayah) produit quand
même un rapport "gradé" plausible — un vrai problème de confiance pour un
coach.

Ce module ajoute un garde-fou bon marché : le décodage CTC glouton (mêmes
logits que forced_align, calculé dans Wav2Vec2Aligner.align() — AUCUNE passe
modèle supplémentaire) comparé au texte attendu via une distance d'édition
normalisée. Ce n'est PAS un ASR de qualité (le modèle n'est pas fine-tuné sur
le Coran ni sur les diacritiques) : juste "est-ce que ça ressemble à cette
ayah", pas "est-ce parfaitement prononcé" (ça, c'est le reste du moteur —
rules.py — qui s'en charge sur l'audio une fois le contenu jugé plausible).
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

try:  # package ou script isolé (cf. autres modules du paquet)
    from ..metadata import normalize_arabic
except ImportError:  # pragma: no cover
    from tajweed.metadata import normalize_arabic  # type: ignore

# CER au-delà de ce seuil -> le contenu ne correspond probablement pas à
# l'ayah attendue. Volontairement PERMISSIF (v1) : un décodeur CTC glouton non
# spécialisé fait déjà beaucoup d'erreurs sur une récitation CORRECTE
# (harakat, tajwid mélodique, madd tenus). On veut attraper le contenu
# clairement étranger (autre langue, autre ayah, silence/bruit), pas
# pénaliser une transcription imparfaite d'une bonne récitation. À resserrer
# une fois validé sur davantage d'audio réel (cf. docs/ROADMAP_V2.txt).
CONTENT_MISMATCH_CER = 0.75


def _levenshtein(a: str, b: str) -> int:
    """Distance d'édition classique (O(len(a)*len(b)) — largement suffisant
    pour la longueur d'une ayah)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[-1]


def char_error_rate(decoded: str, expected: str) -> float:
    """CER normalisé (0.0 = identique ; peut dépasser 1.0 si `decoded` est
    beaucoup plus long que `expected`, ex. bruit continu).

    Compare le SQUELETTE CONSONANTIQUE (normalize_arabic, espaces retirés) :
    le décodage CTC glouton n'est pas fiable sur les harakat/frontières de
    mots, seule l'identité des lettres compte pour ce garde-fou.
    """
    ref = normalize_arabic(expected).replace(" ", "")
    hyp = normalize_arabic(decoded).replace(" ", "")
    if not ref:
        return 0.0 if not hyp else 1.0
    return _levenshtein(hyp, ref) / len(ref)


def check_content(decoded: str, expected: str,
                   threshold: float = CONTENT_MISMATCH_CER) -> Tuple[str, float]:
    """→ (status, cer). status = "ok" | "content_mismatch"."""
    cer = char_error_rate(decoded, expected)
    return ("content_mismatch" if cer > threshold else "ok"), cer


def _prefix_fit_cer(hyp_norm: str, window_norm: str) -> float:
    """Edit distance to align ALL of `hyp_norm` starting at `window_norm`'s
    own start, with `window_norm` free to extend PAST `hyp_norm` at no cost
    (a proper "semi-global" alignment — free trailing gap on the window side
    only, hyp's start anchored to window's start) — NOT a guessed-length
    prefix slice.

    Why free-gap DP instead of slicing `window_norm[:some_guessed_length]`
    (the original 2026-07-08 design): `char_error_rate`'s whole-window
    denominator is correct when comparing a roughly-full recitation against
    its roughly-full expected text, but WRONG for candidate LOCALIZATION — a
    short clip is very often only the BEGINNING of a longer āyah's
    recitation (Āyat al-Kursī, ~52s, spans many segments). Scoring it against
    the WHOLE target āyah's length would count the entire unrecited
    remainder as "errors" (found 2026-07-08: a 6s clip of Āyat al-Kursī's
    opening located the wrong, short 2:163 instead of 2:255). A first fix
    guessed a prefix length from `hyp_norm`'s own length plus a slack
    constant — but that guess could be WRONG when the candidate window
    itself is short (found later the same day, via the SUFFIX case below:
    the slack could swallow the whole window, or too little of it), so this
    version lets the DP itself find the best-fitting boundary instead of
    pre-committing to one.

    Normalized by `len(hyp_norm)` (not the matched window length): the
    caller reuses this directly as `content_cer` for the located span.
    """
    if not hyp_norm:
        return 0.0
    if not window_norm:
        return 1.0
    nh, nw = len(hyp_norm), len(window_norm)
    prev = list(range(nw + 1))         # dp[0][j] = j
    for i in range(1, nh + 1):
        cur = [i] + [0] * nw           # dp[i][0] = i
        hc = hyp_norm[i - 1]
        for j in range(1, nw + 1):
            cost = 0 if hc == window_norm[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return min(prev) / nh              # free trailing gap: best over every possible "hyp ends here"


def _suffix_fit_cer(hyp_norm: str, window_norm: str) -> float:
    """Mirror of `_prefix_fit_cer`, but `hyp_norm`'s END is anchored to
    `window_norm`'s END instead (free LEADING gap on the window side) — the
    proper alignment for a clip that's only the TAIL of what it's matching.

    Why this matters: a clip isn't always the beginning of what it's
    matching — Practice.tsx's rolling recorder (2026-07-08) grades a
    SLIDING time window holding only the last ~3.2s of audio, so once a long
    āyah's OPENING scrolls out of the window, all that's left is its ENDING.
    `_prefix_fit_cer` alone can't recognize that (it only ever anchors to a
    candidate's own beginning). Found for real: reciting ONLY Al-Fātiḥa 1:1
    ("بسم الله الرحمن الرحيم") got misidentified as 1:3 ("الرحمن الرحيم" —
    coincidentally exactly 1:1's own ending) once the window scrolled past
    "بسم الله": 1:1 scored badly under prefix-fit (anchored to its own
    OPENING, no longer in the clip) while 1:3 scored perfectly (its whole
    text IS the clip). `locate_best_span` takes
    `min(_prefix_fit_cer(...), _suffix_fit_cer(...))` so either alignment can
    win — this makes a genuine tail-of-1:1 clip score well against 1:1 too,
    turning a wrong, confident answer into a genuine tie that `near_ayah`
    can then correctly resolve toward continuity.

    Implemented as `_prefix_fit_cer` on both strings REVERSED: edit distance
    is invariant under simultaneous reversal, and "hyp's end anchored to
    window's end, window free on the left" is exactly "hyp's start anchored
    to window's start, window free on the right" once both are reversed —
    no second DP to write or keep in sync.
    """
    return _prefix_fit_cer(hyp_norm[::-1], window_norm[::-1])


def _char_bigrams(s: str) -> "Counter":
    from collections import Counter
    if len(s) < 2:
        return Counter([s]) if s else Counter()
    return Counter(s[i:i + 2] for i in range(len(s) - 1))


# En dessous de cette longueur (caractères normalisés), le préfiltre
# bigrammes n'a quasiment AUCUN pouvoir discriminant — une āyah muqattaʿāt de
# 3 lettres ("الم") a ~2 bigrammes ; n'importe quelle fenêtre en a autant par
# hasard, donc le "meilleur" score bigramme n'indique rien (c'est CE cas
# précis, 2:1 dans Al-Baqara, qui a révélé le problème). La recherche EXACTE
# reste bon marché quand `hyp` est court de toute façon (coût
# O(n×max_span×len(hyp)), petit) — donc en dessous de ce seuil, pas de
# préfiltre du tout, comparaison précise sur TOUTES les fenêtres.
SHORT_HYP_CHARS = 12


def locate_best_span(decoded: str, full_text: str,
                     ayah_spans: Sequence[Tuple[int, int, int]],
                     max_span: int = 6, top_k: int = 6,
                     threshold: float = CONTENT_MISMATCH_CER,
                     near_ayah: Optional[int] = None,
                     tie_epsilon: float = 0.05,
                     ) -> Optional[Tuple[int, int, float]]:
    """Which consecutive-āyah span of `full_text` (e.g. a whole sūrah —
    `ayah_spans` = [(ayah, char_start, char_end), ...] in order) best matches
    `decoded` — CHARACTER-level, not word-level (Roadmap V2 — "sūrah = one
    paragraph", 2026-07-08).

    Character-level, deliberately: a WORD-level approach (word_score.
    align_words) was tried first and found NOT robust enough — the greedy CTC
    decode's word-delimiter ("|") token predictions can scramble word splits
    (merge/split words wrong) even when the underlying LETTERS are basically
    correct, e.g. a real, correctly-recited 1:5 decoded with mangled word
    boundaries and matched ZERO words against the true text despite being an
    accurate letter-for-letter transcription.

    ADAPTIVE two-path design, arrived at after two failed simpler attempts:
      1. A single Smith-Waterman local-alignment DP pass over the WHOLE
         sūrah — fast in theory, but pure-Python nested loops made it ~20s+
         on a long āyah (Āyat al-Kursī), AND a SHORT āyah (2:1, "الم", 3
         letters) matched a WRONG spot elsewhere by chance — local alignment
         has no notion of "this match is suspiciously weak/short", so a tiny
         hyp scores well almost anywhere in a long text.
      2. A flat "bigram-prefilter then precise-CER-on-top-k" — fixed the
         long-āyah speed AND the short-āyah correctness mostly, but the
         short-āyah case STILL sometimes failed to locate at all: a 3-letter
         hyp has ~2 bigrams total, so the prefilter's ranking is close to
         random noise and can fail to put the true match in the top_k.
    Fix: for a SHORT decoded clip (< SHORT_HYP_CHARS), skip the prefilter
    ENTIRELY and run the exact/precise search over every candidate — cheap
    regardless of sūrah length when `hyp` itself is short, and this is
    exactly the case where the prefilter has no signal to offer anyway. Only
    a genuinely LONG decoded clip (where exact search would be expensive)
    goes through the cheap bigram prefilter, computed via per-āyah
    PRECOMPUTED bigram counters accumulated incrementally as the window
    grows (O(n×max_span) counter merges, not O(n×max_span²) — no
    re-normalizing/re-counting the same overlapping text repeatedly).

    Final scoring takes the BETTER of a PREFIX-fit and a SUFFIX-fit CER (see
    `_prefix_fit_cer`/`_suffix_fit_cer`), not whole-window CER — critical for
    long āyahs recited across multiple segments, where a clip may cover only
    the BEGINNING of its āyah (a fresh window mid-recitation) OR only its
    ENDING (a sliding time window that has scrolled past the āyah's opening —
    found 2026-07-08 via the rolling-window redesign).

    None if even the best candidate's score exceeds `threshold`; otherwise
    (ayah_from, ayah_to, cer) — the caller can reuse `cer` directly as the
    content-match quality for this span instead of re-running a whole-text
    comparison (which would reintroduce the same partial-recitation bias).

    `near_ayah` (optional, 2026-07-08): a SOFT proximity hint, not a
    constraint — this stays fully stateless (no cursor to get stuck on, the
    whole point of this design). Some short phrases genuinely repeat
    word-for-word at more than one point in the SAME sūrah (e.g. Al-Fātiḥa's
    "الرحمن الرحيم" is both the tail of āyah 1 and the whole of āyah 3) —
    with no positional information at all, a stateless search has no way to
    prefer the occurrence the reciter is actually AT, and can occasionally
    lock onto the wrong one, making progress appear to jump ahead of (or
    behind) where the reciter really is. When multiple candidates score
    within `tie_epsilon` of the best CER, `near_ayah` (if given, e.g. the
    frontend's last-known position) breaks the tie toward whichever
    candidate is CLOSEST to it — a candidate that's a clearly BETTER match
    (outside the epsilon) still wins regardless of distance, so this never
    overrides genuine content evidence, only resolves genuine ambiguity.
    """
    hyp_norm = normalize_arabic(decoded).replace(" ", "")
    if not hyp_norm:
        return None
    n = len(ayah_spans)
    norm_ayah = [normalize_arabic(full_text[s:e]).replace(" ", "")
                for _, s, e in ayah_spans]

    if len(hyp_norm) < SHORT_HYP_CHARS:
        candidates = [(i, j) for i in range(n) for j in range(i, min(i + max_span, n))]
    else:
        # PREFIX-bounded, like the final CER stage below — a window's score
        # must NOT keep shrinking as more āyahs are appended beyond what the
        # (short) clip could possibly cover, or a long correct āyah loses to
        # a short wrong one purely on bigram-density dilution (found
        # 2026-07-08: this exact bias, first fixed in the final CER stage,
        # was STILL present here in the prefilter — capping only the final
        # stage wasn't enough, since a long-āyah candidate never reached the
        # top_k to BE precisely re-scored in the first place).
        cap = int(len(hyp_norm) * 1.3) + 5
        hyp_bigrams = _char_bigrams(hyp_norm)

        prefilter_scored: list = []
        for i in range(n):
            prefix_acc = ""
            suffix_acc = ""
            for j in range(i, min(i + max_span, n)):
                if len(prefix_acc) < cap:
                    prefix_acc += norm_ayah[j]
                # Suffix accumulator re-truncated to `cap` every step (not
                # left to grow with `j`) — a clip can be the TAIL of a
                # candidate window just as easily as its head (a sliding
                # time window scrolls PAST an āyah's opening — see
                # `_suffix_aware_cer`), so the prefilter must be able to
                # rank that candidate highly too, not just prefix matches.
                suffix_acc = (suffix_acc + norm_ayah[j])[-cap:]
                overlap = max(
                    sum((hyp_bigrams & _char_bigrams(prefix_acc[:cap])).values()),
                    sum((hyp_bigrams & _char_bigrams(suffix_acc)).values()),
                )
                score = overlap / max(len(hyp_bigrams), min(len(prefix_acc), cap), 1)
                prefilter_scored.append((score, i, j))
        prefilter_scored.sort(key=lambda t: -t[0])
        candidates = [(i, j) for _, i, j in prefilter_scored[:top_k]]

    scored: List[Tuple[float, int, int]] = []  # (cer, ayah_from, ayah_to)
    for i, j in candidates:
        window_norm = "".join(norm_ayah[i:j + 1])
        cer = min(_prefix_fit_cer(hyp_norm, window_norm),
                  _suffix_fit_cer(hyp_norm, window_norm))
        scored.append((cer, ayah_spans[i][0], ayah_spans[j][0]))
    if not scored:
        return None

    # Drop any window DOMINATED by a strictly-narrower sub-window scoring at
    # least as well (exact ties only, hence the tiny epsilon). The prefix/
    # suffix free-gap scoring above makes this possible: a window of āyahs
    # 1-2 matches a clip of just āyah 2 with the SAME perfect CER as the
    # tight (2,2) window — the free leading gap simply skips all of āyah 1,
    # meaning that extra āyah contributed ZERO matched characters and there
    # is no evidence it was recited at all. Without this prune, min() picks
    # whichever tied window enumerates first (the wider one), systematically
    # inflating ayah_from/ayah_to past what the reciter actually said —
    # caught 2026-07-11 by test_evaluate_clip_locates_and_grades_without_
    # start_ayah, which regressed when the suffix-fit path was added (#46)
    # without re-running the full suite.
    scored = [
        (cer, a_from, a_to)
        for cer, a_from, a_to in scored
        if not any(
            c2 <= cer + 1e-9 and f2 >= a_from and t2 <= a_to and (t2 - f2) < (a_to - a_from)
            for c2, f2, t2 in scored
        )
    ]

    best_cer = min(cer for cer, _, _ in scored)
    if best_cer > threshold:
        return None
    if near_ayah is None:
        cer, ayah_from, ayah_to = min(scored, key=lambda t: t[0])
        return ayah_from, ayah_to, cer

    near_ties = [c for c in scored if c[0] <= best_cer + tie_epsilon]
    cer, ayah_from, ayah_to = min(near_ties, key=lambda t: (abs(t[1] - near_ayah), t[0]))
    return ayah_from, ayah_to, cer
