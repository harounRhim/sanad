# -*- coding: utf-8 -*-
"""
src/tajweed/correction/word_score.py — Notation par MOT (Roadmap V2, Phase 1).

Combine deux signaux indépendants pour CHAQUE mot du texte de l'ayah :
  (a) CONTENU — ce mot a-t-il été reconnu dans le décodage CTC glouton
      (aligner.py / content_check.py) ? Alignement GLOBAL niveau CARACTÈRE
      (pas mot) entre le texte attendu et le texte décodé, projeté ensuite
      sur chaque mot via ses positions dans le texte original (cf.
      `_char_align_matched` / `_normalize_with_map` ci-dessous).
  (b) TAJWEED — les résultats de règles déjà calculés par rules.measure_all,
      reprojetés sur le mot qu'ils recouvrent (aucun recalcul).

Verdict combiné par mot :
  RED    = mot manquant/mal reconnu — le CONTENU prime : noter le Tajweed
           d'un mot qui n'a pas été dit n'a aucun sens.
  YELLOW = mot reconnu, mais au moins une règle Tajweed dessus est "warn".
  GREEN  = mot reconnu ET toutes ses règles "ok" (ou aucune règle dessus).

Pourquoi CARACTÈRE et pas MOT (2026-07-08, deuxième itération) : une première
version comparait des LISTES DE MOTS (`decoded_text.split()` vs le texte de
l'ayah), avec un alignement WER classique puis flou (coût de substitution =
CER du mot). Ça tolérait un mot mal transcrit isolé, mais pas le vrai
problème observé sur une session micro CONTINUE : le token de séparation "|"
du décodage CTC glouton devient de moins en moins fiable à mesure que l'audio
s'allonge, au point de purement et simplement SUPPRIMER l'espace entre deux
ayahs consécutives ("الرَّحيِالْحَمْدُ" = fin de 1:1 + début de 1:2 collés
sans aucun espace). Un alignement au niveau MOT n'a alors plus rien à quoi se
raccrocher : ce bloc fusionné ne ressemble à AUCUN mot de référence pris
isolément, donc les DEUX mots réels ressortaient rouges même correctement
récités. Solution : ne plus jamais découper le texte décodé en mots — traiter
`decoded_text` comme un pur flux de LETTRES (espaces retirés, comme
`content_check.locate_best_span` le fait déjà pour la localisation, même
raisonnement) et faire UN SEUL alignement caractère-par-caractère global sur
tout le texte de référence, puis, pour chaque mot, mesurer quelle fraction de
SES PROPRES lettres a trouvé une correspondance dans cet alignement. Un mot
réellement absent/faux aura toujours un score bas (ses lettres ne
correspondent à rien de proche dans l'audio) ; un mot juste séparé par un
espace mal prédit reste, lui, pleinement reconnu.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from .types import SegmentResult

try:  # package ou script isolé (cf. autres modules du paquet)
    from ..metadata import normalize_arabic, _ARABIC_MARKS
except ImportError:  # pragma: no cover
    from tajweed.metadata import normalize_arabic, _ARABIC_MARKS  # type: ignore


@dataclass
class WordScore:
    word: str
    start_idx: int
    end_idx: int
    content_ok: bool
    rules: List[SegmentResult] = field(default_factory=list)
    verdict: str = "green"          # "green" | "yellow" | "red"

    def to_dict(self) -> dict:
        return {
            "word": self.word, "start_idx": self.start_idx, "end_idx": self.end_idx,
            "content_ok": self.content_ok, "verdict": self.verdict,
            "rules": [
                {"rule": r.rule, "status": r.status, "message": r.message,
                 "measured_harakat": r.measured_harakat}
                for r in self.rules
            ],
        }


def split_words(text: str) -> List[Tuple[str, int, int]]:
    """(mot, start_idx, end_idx) pour chaque mot séparé par un espace.

    Mêmes offsets que ceux des segments Tajweed (indexent CE MÊME texte
    uthmani) — directement réutilisables sans reprojection."""
    words: List[Tuple[str, int, int]] = []
    i, n = 0, len(text)
    while i < n:
        while i < n and text[i].isspace():
            i += 1
        if i >= n:
            break
        start = i
        while i < n and not text[i].isspace():
            i += 1
        words.append((text[start:i], start, i))
    return words


# Mêmes substitutions de lettres que `metadata.normalize_arabic`, mais
# appliquées caractère par caractère avec un index vers le texte D'ORIGINE —
# nécessaire pour reprojeter ensuite l'alignement caractère sur les positions
# (start_idx/end_idx) de chaque mot, qui sont exprimées dans le texte NON
# normalisé (mêmes offsets que les segments Tajweed).
_ARABIC_SUBS = {
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ى": "ي", "ؤ": "و", "ئ": "ي", "ة": "ه",
}


def _normalize_with_map(text: str) -> Tuple[str, List[int]]:
    """→ (texte normalisé sans espaces, [index dans `text` de chaque
    caractère de sortie]) — permet de reprojeter un alignement fait sur la
    sortie vers les offsets du texte original."""
    out_chars: List[str] = []
    out_map: List[int] = []
    for i, ch in enumerate(text):
        if ch.isspace() or _ARABIC_MARKS.match(ch):
            continue
        out_chars.append(_ARABIC_SUBS.get(ch, ch))
        out_map.append(i)
    return "".join(out_chars), out_map


def _char_align_matched(hyp: str, ref: str) -> List[Optional[int]]:
    """Alignement de Levenshtein GLOBAL, niveau caractère, avec backtrace.

    → pour CHAQUE caractère de `ref` : l'INDEX (dans `hyp`) du caractère
    IDENTIQUE auquel il est aligné dans l'alignement optimal (diagonale de
    coût 0), ou `None` s'il est substitué ou supprimé. Aucune notion de
    "mot" ici — c'est précisément le but (cf. docstring du module).

    On renvoie une POSITION, pas juste un booléen, pour que l'appelant
    puisse vérifier que les lettres d'un même mot s'alignent bien sur une
    zone CONTIGUË de `hyp` (cf. `_word_match_ratios`) — un alignement
    global Levenshtein pur laisse sinon un mot COURT (2-3 lettres communes,
    ex. "احد") "matcher" par pur hasard des lettres éparpillées n'importe où
    dans un `hyp` totalement étranger, simplement parce que ça ne coûte rien
    de plus au total. Trouvé en écrivant les tests de non-régression pour ce
    module (2026-07-08) : sans cette contrainte de localité, une ayah
    complètement différente (112:1 vs audio de 1:1) faisait quand même
    ressortir un de ses mots courts "reconnu" à tort."""
    nh, nr = len(hyp), len(ref)
    dp = [[0] * (nr + 1) for _ in range(nh + 1)]
    # back[i][j]: 3 = diagonale (match/substitution), 1 = insertion (lettre
    # hyp en trop), 2 = suppression (lettre ref manquante). Précalculé
    # pendant la passe avant (pas de recomparaison pendant le backtrace).
    back = [[0] * (nr + 1) for _ in range(nh + 1)]
    for i in range(1, nh + 1):
        dp[i][0] = i
        back[i][0] = 1
    for j in range(1, nr + 1):
        dp[0][j] = j
        back[0][j] = 2
    for i in range(1, nh + 1):
        hc = hyp[i - 1]
        row, prow, brow = dp[i], dp[i - 1], back[i]
        for j in range(1, nr + 1):
            cost = 0 if hc == ref[j - 1] else 1
            diag = prow[j - 1] + cost
            up = prow[j] + 1
            left = row[j - 1] + 1
            if diag <= up and diag <= left:
                row[j], brow[j] = diag, 3
            elif left <= up:
                row[j], brow[j] = left, 2
            else:
                row[j], brow[j] = up, 1

    matched: List[Optional[int]] = [None] * nr
    i, j = nh, nr
    while i > 0 or j > 0:
        b = back[i][j] if (i > 0 and j > 0) else (1 if i > 0 else 2)
        if b == 3:
            if hyp[i - 1] == ref[j - 1]:
                matched[j - 1] = i - 1
            i, j = i - 1, j - 1
        elif b == 2:
            j -= 1                     # suppression : ref[j-1] non matché
        else:
            i -= 1                     # insertion : ne concerne aucun caractère ref
    return matched


# Fraction des lettres D'UN MOT qui doivent trouver une correspondance dans
# l'alignement caractère pour que ce mot compte comme reconnu. Volontairement
# < 1.0 : le décodeur CTC glouton non spécialisé Coran/harakat rate souvent
# UNE lettre par-ci par-là même sur une récitation correcte (ex. "مالك" ->
# "مالث", dernière lettre confondue) ; on veut attraper un mot manquant ou
# vraiment différent, pas pénaliser un mot dont 3 lettres sur 4 ont été
# entendues juste. Validé sur audio réel (récitation husary complète
# d'Al-Fātiḥa, .build_tmp/probe_word_score_fix.py) : à ce seuil, 0 faux
# rouge sur 6 des 7 ayahs, 1 seul résidu sur la 7e (fusion de deux mots par
# le CTC, cas plus dur qu'une simple lettre ratée).
WORD_MATCH_RATIO = 0.6


# Ce dataset PRÉFIXE la basmala au TEXTE de l'ayah 1 de chaque sourate (sauf 1,
# où la basmala EST l'ayah, et 9, qui n'en a pas), alors que l'AUDIO de
# l'ayah 1 ne la contient en général PAS (le récitateur l'omet). Même
# donnée/logique que `audio_verify.BASMALA_NORM` (dupliquée ici plutôt
# qu'importée : audio_verify.py entraîne mutagen, un couplage inutile pour ce
# module). Sans ça, les 4 mots de la basmala ressortaient FAUSSEMENT "red"
# (non reconnus) sur toute ayah-1 correctement récitée (trouvé 2026-07-06 en
# validant sur 112:1 réel).
BASMALA_NORM = normalize_arabic("بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ").replace(" ", "")


def _strip_basmala_prefix(words: List[Tuple[str, int, int]],
                          surah: Optional[int], ayah: Optional[int]
                          ) -> List[Tuple[str, int, int]]:
    """Retire les 4 mots de la basmala PRÉFIXÉE AU TEXTE de l'ayah 1 (pas à
    l'audio), sauf sourates 1 et 9 (cf. constante ci-dessus). Sans surah/ayah
    fournis (None), ne fait rien — rétro-compatible avec les appels sans
    contexte (tests, ou aligneur synthétique sans notion d'ayah)."""
    if surah is None or ayah != 1 or surah in (1, 9) or len(words) < 4:
        return words
    prefix_norm = "".join(normalize_arabic(w) for w, _, _ in words[:4]).replace(" ", "")
    if prefix_norm == BASMALA_NORM:
        return words[4:]
    return words


# Nombre de "trous" toléré DANS la zone couverte par les lettres matchées
# d'un même mot — pas une marge sur la LONGUEUR du mot (une version testée
# avec un seuil de longueur donnait soit des faux positifs sur les mots
# courts, soit des faux négatifs sur une simple lettre parasite insérée dans
# un mot par ailleurs bien reconnu ; le bon signal s'est avéré être la
# COMPACITÉ du match, indépendante de la longueur du mot) :
#   trou = (span des positions hyp matchées) - (nombre de lettres matchées)
# Un vrai mot correctement récité, même avec UNE lettre ratée ou UNE lettre
# parasite insérée par le décodeur, garde ses lettres matchées quasi
# adjacentes (trou 0 ou 1). Un match par pur hasard sur un texte étranger
# pioche des lettres communes espacées (trou ≥ 2) — cas réel trouvé en test
# (2026-07-08, 112:1 noté "reconnu" contre l'audio de 1:1) : "احد" (3
# lettres) piochait un ا et un ح dans "الرحيم" à 4 positions d'écart pour
# seulement 2 lettres matchées (trou = 4 - 2 = 2).
WORD_GAP_SLACK = 1


# A word beyond this many ref_norm characters past the FURTHEST point the
# decode reached gets EXCLUDED entirely (see `_word_match_ratios`) rather
# than marked red — enough slack to cover one imperfectly-decoded trailing
# word, not so much that a genuinely absent tail gets waved through.
NOT_REACHED_SLACK = 4


def _local_reached_region(hyp_norm: str, ref_norm: str) -> Optional[Tuple[int, int]]:
    """Best-fitting contiguous region of `ref_norm` that `hyp_norm` (fully
    consumed) explains, free at BOTH ends — handles a clip being the
    BEGINNING, END, or a MIDDLE segment of the located āyah uniformly.

    An earlier version of this only freed the TRAILING end (anchored hyp to
    ref's own START), on the assumption a clip always begins where the
    āyah does. That's true for the FIRST rolling window of an āyah, but
    WRONG for any later one: with a ~3.2s window against, say, a 15s āyah
    (Al-Fātiḥa 1:7), most windows land somewhere in the MIDDLE. Found for
    real 2026-07-08: a genuine husary clip of "المغضوب عليهم..." (clearly a
    mid-āyah segment) still marked "المغضوب" red even though the decode
    contained it almost perfectly — the old DP was forced to try explaining
    it as starting from the āyah's own opening ("صراط..."), which it
    obviously doesn't, so its "reached" boundary came out nowhere near
    where the clip's content actually was.

    Deliberately bounded to a SINGLE ALREADY-LOCATED āyah's text (tens of
    characters, not a whole sūrah) — this is exactly the scale where a free-
    both-ends ("local") alignment is safe. `content_check.locate_best_span`
    rejected a similar approach for finding WHICH āyah a clip belongs to,
    searched across an ENTIRE sūrah, because a short hyp could match almost
    anywhere by chance; here hyp typically covers several words (15-30+
    normalized characters from a ~3s window) against one small āyah, a much
    safer ratio, and this only affects which words get GRADED AT ALL, not
    the content_ok verdict itself (still separately gap-checked per word).

    Returns (start, end) inclusive `ref_norm` indices, or `None` if either
    string is empty."""
    if not hyp_norm or not ref_norm:
        return None
    nh, nr = len(hyp_norm), len(ref_norm)
    dp = [[0] * (nr + 1) for _ in range(nh + 1)]
    start_at = [[0] * (nr + 1) for _ in range(nh + 1)]
    for j in range(nr + 1):
        dp[0][j] = 0            # free leading gap: hyp can start matching anywhere
        start_at[0][j] = j
    for i in range(1, nh + 1):
        dp[i][0] = i
        start_at[i][0] = 0
        hc = hyp_norm[i - 1]
        drow, prow, srow, sprow = dp[i], dp[i - 1], start_at[i], start_at[i - 1]
        for j in range(1, nr + 1):
            cost = 0 if hc == ref_norm[j - 1] else 1
            diag = prow[j - 1] + cost
            up = prow[j] + 1
            left = drow[j - 1] + 1
            best = min(diag, up, left)
            drow[j] = best
            if best == diag:
                srow[j] = sprow[j - 1]
            elif best == left:
                srow[j] = srow[j - 1]
            else:
                srow[j] = sprow[j]
    last = dp[nh]
    best_cost = min(last)
    # Prefer the LARGEST j (and correspondingly its own start_at) achieving
    # the minimum cost — same reasoning as the old _reached_bound: several
    # trailing positions routinely tie once hyp is fully "spent", and the
    # larger one credits hyp with explaining more of ref rather than less.
    best_j = max(j for j in range(nr + 1) if last[j] == best_cost)
    start = start_at[nh][best_j]
    end = max(start, best_j - 1)
    return start, end


def _word_match_ratios(text: str, decoded_text: str,
                       words: Sequence[Tuple[str, int, int]]) -> List[Optional[float]]:
    """Pour chaque `(word, start, end)` de `words` (offsets dans `text`,
    texte NON normalisé) : fraction de ses lettres normalisées qui trouvent
    une correspondance identique et COMPACTE (pas éparpillée — cf.
    `WORD_GAP_SLACK`) dans `decoded_text`, via UN SEUL alignement caractère
    global sur tout `text` (pas un alignement par mot — cf. docstring du
    module pour pourquoi). `None` = ce mot n'a PAS ENCORE été atteint par le
    clip (à exclure, pas à noter rouge — cf. `NOT_REACHED_SLACK`).

    Pourquoi distinguer "pas encore atteint par CE clip" de "mal récité"
    (2026-07-08) : avec la fenêtre GLISSANTE (rolling recorder), un clip ne
    couvre jamais qu'une PETITE portion d'une longue ayah en cours de
    récitation (ex. 1:7, la plus longue d'Al-Fātiḥa, 9 mots) — le DÉBUT
    (pas encore dit), la FIN (déjà défilée hors de la fenêtre), OU une
    portion du MILIEU (cf. `_local_reached_region`). L'alignement caractère
    GLOBAL (hyp et ref entièrement consommés) traite tout ce qui est hors de
    cette portion comme des SUPPRESSIONS (aucune lettre matchée),
    indiscernable d'un vrai mot mal prononcé. Un mot ENTIÈREMENT hors de la
    région effectivement couverte par ce clip (des deux côtés) n'a
    simplement pas d'information CE TOUR-CI -> exclu du rapport (rendu
    neutre côté UI, comme un mot jamais noté ; un mot déjà confirmé par un
    tour PRÉCÉDENT reste affiché grâce à la fusion "sticky" côté frontend),
    pas marqué rouge. Un mot qui échoue DANS la région effectivement
    couverte reste noté rouge normalement."""
    ref_norm, ref_map = _normalize_with_map(text)
    hyp_norm, _ = _normalize_with_map(decoded_text)

    # Restrict "reached" to only the FIRST SURVIVING word onward, not all of
    # `text` -- when `_strip_basmala_prefix` has removed a prefix, that's a
    # DATA ARTIFACT (present in the text column, never in the audio) rather
    # than unrecited content; letting the region-finder consider it (found
    # 2026-07-08) made a decode that matched 112:1 perfectly still look like
    # it had "reached" almost nothing, since it obviously never matches the
    # basmala -- excluding every real word instead of grading any of them.
    first_start = words[0][1] if words else 0
    k0 = 0
    while k0 < len(ref_map) and ref_map[k0] < first_start:
        k0 += 1
    region = _local_reached_region(hyp_norm, ref_norm[k0:])
    reached_start, reached_end = (k0, k0 - 1) if region is None else (k0 + region[0], k0 + region[1])
    # Detailed per-word matching runs against only the REACHED region of
    # ref_norm (padded by NOT_REACHED_SLACK on both sides), not the whole
    # thing — `_char_align_matched` is a GLOBAL (fully-consuming) alignment,
    # forced to explain the ENTIRE reference even when hyp is much shorter.
    # Handed a full multi-word āyah for a short partial decode, it scatters
    # its few genuine matches unpredictably while forcing the rest into
    # deletions — even a clearly-decoded word can come out unmatched,
    # because the DP's globally-cheapest path doesn't have to align it
    # cleanly to explain the OVERALL string. Restricting to the reached
    # region first gives hyp a similarly-sized reference to align against,
    # matching cleanly instead of arbitrarily.
    ref_lo = max(0, reached_start - NOT_REACHED_SLACK)
    ref_hi = min(len(ref_norm), reached_end + 1 + NOT_REACHED_SLACK)
    char_matched = _char_align_matched(hyp_norm, ref_norm[ref_lo:ref_hi])

    ratios: List[Optional[float]] = []
    k = 0  # ref_map est croissant (même ordre que text) -> avance en une passe
    for _, start, end in words:
        while k < len(ref_map) and ref_map[k] < start:
            k += 1
        word_ref_start = k
        # Word entirely outside the (padded) reached region on EITHER side
        # -- not yet spoken (clip starts later) or already scrolled out of
        # this particular clip's view (clip starts/ends elsewhere) -- either
        # way this clip has nothing to say about it; leave it for whichever
        # clip (earlier or later) actually covers it.
        word_ref_end = word_ref_start
        while word_ref_end < len(ref_map) and ref_map[word_ref_end] < end:
            word_ref_end += 1
        if word_ref_end <= ref_lo or word_ref_start >= ref_hi:
            ratios.append(None)
            continue
        total = 0
        hyp_positions: List[int] = []
        m = k
        while m < len(ref_map) and ref_map[m] < end:
            total += 1
            hp = char_matched[m - ref_lo] if ref_lo <= m < ref_hi else None
            if hp is not None:
                hyp_positions.append(hp)
            m += 1
        if total == 0:
            ratios.append(1.0)
            continue
        if not hyp_positions:
            ratios.append(0.0)
            continue
        span = max(hyp_positions) - min(hyp_positions) + 1
        gap = span - len(hyp_positions)
        if gap > WORD_GAP_SLACK:
            ratios.append(0.0)     # lettres éparpillées -> coïncidence
        else:
            ratios.append(len(hyp_positions) / total)
    return ratios


def score_words(text: str, decoded_text: Optional[str],
                rule_results: Sequence[SegmentResult],
                surah: Optional[int] = None, ayah: Optional[int] = None
                ) -> List[WordScore]:
    """Combine contenu (mot par mot) + résultats Tajweed déjà calculés en un
    verdict rouge/jaune/vert PAR MOT.

    `decoded_text=None` (aligneur sans décodage, ex. SyntheticAligner en
    test/démo) → content_ok=True partout par défaut : pas de garde-fou de
    contenu possible sans ML, cohérent avec content_status="unknown".

    `surah`/`ayah` (optionnels) : si fournis, retire le préfixe basmala du
    TEXTE de l'ayah 1 avant notation (cf. `_strip_basmala_prefix`) — sinon
    ces 4 mots sont notés "red" à tort sur un enregistrement pourtant correct
    (l'audio omet en général la basmala pour l'ayah 1, seul le texte l'a).

    Un mot dont `_word_match_ratios` renvoie `None` (pas encore atteint par
    ce clip, cf. sa docstring) est OMIS du résultat plutôt que noté rouge —
    le mot reste simplement non coloré côté UI tant qu'aucun clip n'en donne
    de verdict, exactement comme un mot jamais encore soumis."""
    words = _strip_basmala_prefix(split_words(text), surah, ayah)
    if decoded_text is not None:
        ratios = _word_match_ratios(text, decoded_text, words)
        graded = [(w, r >= WORD_MATCH_RATIO) for w, r in zip(words, ratios) if r is not None]
    else:
        graded = [(w, True) for w in words]

    scores: List[WordScore] = []
    for (word, start, end), ok in graded:
        touching = [r for r in rule_results
                    if r.start_idx < end and r.end_idx > start]
        if not ok:
            verdict = "red"
        elif any(r.status == "warn" for r in touching):
            verdict = "yellow"
        else:
            verdict = "green"
        scores.append(WordScore(word=word, start_idx=start, end_idx=end,
                                content_ok=ok, rules=touching, verdict=verdict))
    return scores
