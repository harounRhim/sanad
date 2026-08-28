# -*- coding: utf-8 -*-
"""
src/tajweed/correction/types.py — Types du moteur de correction Tajweed.

Le cœur déterministe (mapping offset→temps, mesure des règles, rapport) ne
dépend d'AUCUN modèle ML : il manipule une `Alignment` (timing par caractère du
texte uthmani) produite soit par un vrai aligneur (wav2vec2), soit par un
aligneur synthétique en test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

Span = Tuple[float, float]  # (t_début, t_fin) en secondes


@dataclass
class Alignment:
    """Timing audio par caractère du texte uthmani.

    `char_spans[i]` = (t0, t1) du i-ème caractère du texte, ou None si ce
    caractère n'a pas de support audio propre (harakat, espace). Les segments
    Tajweed indexent ce MÊME texte (start_idx/end_idx), d'où le mapping direct.
    """
    text: str
    char_spans: List[Optional[Span]]
    duration: float  # durée totale de l'audio (s)
    decoded_text: Optional[str] = None  # décodage CTC glouton (Wav2Vec2Aligner only)

    def __post_init__(self) -> None:
        if len(self.char_spans) != len(self.text):
            raise ValueError(
                f"char_spans ({len(self.char_spans)}) != len(text) ({len(self.text)})")

    def span_for(self, start_idx: int, end_idx: int) -> Optional[Span]:
        """Fenêtre temporelle couvrant text[start_idx:end_idx] (bornes incluses
        côté caractères ayant un timing). None si aucun caractère timé."""
        timed = [s for s in self.char_spans[start_idx:end_idx] if s is not None]
        if not timed:
            return None
        return (min(t0 for t0, _ in timed), max(t1 for _, t1 in timed))

    def span_for_lenient(self, start_idx: int, end_idx: int) -> Optional[Span]:
        """Comme span_for, mais si le segment ne contient que des marques
        combinantes (madd porté par un alif suscrit, petit waw/ya…), on rattache
        le timing à la DERNIÈRE lettre timée avant start_idx — là où la voyelle
        est effectivement tenue. None seulement si rien en amont n'est timé."""
        span = self.span_for(start_idx, end_idx)
        if span is not None:
            return span
        for i in range(start_idx - 1, -1, -1):
            if self.char_spans[i] is not None:
                return self.char_spans[i]
        return None


@dataclass
class SegmentResult:
    rule: str
    start_idx: int
    end_idx: int
    segment: str
    expected: str               # ex. "≈4 ḥarakāt" / "≈2 ḥarakāt (nasal)"
    measured: str               # ex. "3.1 ḥarakāt"
    measured_harakat: Optional[float] = None
    nasality: Optional[float] = None
    status: str = "unknown"     # "ok" | "warn" | "missing_audio"
    message: str = ""


@dataclass
class Report:
    surah: int
    ayah: int
    audio_path: str
    duration: float
    haraka_unit_s: Optional[float]      # durée estimée d'une ḥaraka (s)
    aligner: str
    results: List[SegmentResult] = field(default_factory=list)
    # Roadmap V2 Phase 0 — vérif. de contenu (indépendante du forced-alignment) :
    # "unknown" si l'aligneur ne décode pas (ex. SyntheticAligner en test/démo).
    content_status: str = "unknown"     # "ok" | "content_mismatch" | "unknown"
    content_cer: Optional[float] = None
    decoded_text: Optional[str] = None  # transcription CTC brute (debug/UI)
    # Roadmap V2 Phase 1 — notation combinée PAR MOT (word_score.WordScore).
    # Type non importé ici (from __future__ import annotations + duck-typing
    # dans to_dict() ci-dessous) pour éviter un import circulaire avec
    # word_score.py, qui importe SegmentResult DEPUIS ce module.
    word_scores: List["WordScore"] = field(default_factory=list)  # noqa: F821

    @property
    def n_ok(self) -> int:
        return sum(1 for r in self.results if r.status == "ok")

    @property
    def n_warn(self) -> int:
        return sum(1 for r in self.results if r.status == "warn")

    def to_dict(self) -> dict:
        return {
            "surah": self.surah, "ayah": self.ayah,
            "audio_path": self.audio_path, "duration_s": round(self.duration, 2),
            "haraka_unit_s": round(self.haraka_unit_s, 3) if self.haraka_unit_s else None,
            "aligner": self.aligner,
            "content_status": self.content_status,
            "content_cer": round(self.content_cer, 3) if self.content_cer is not None else None,
            "decoded_text": self.decoded_text,
            "summary": {"ok": self.n_ok, "warn": self.n_warn, "total": len(self.results)},
            "results": [
                {
                    "rule": r.rule, "segment": r.segment,
                    "start_idx": r.start_idx, "end_idx": r.end_idx,
                    "expected": r.expected, "measured": r.measured,
                    "measured_harakat": (round(r.measured_harakat, 2)
                                         if r.measured_harakat is not None else None),
                    "nasality": (round(r.nasality, 3) if r.nasality is not None else None),
                    "status": r.status, "message": r.message,
                }
                for r in self.results
            ],
            "word_scores": [w.to_dict() for w in self.word_scores],
        }


@dataclass
class WindowReport:
    """Rapport d'une notation par FENÊTRE de plusieurs ayahs (correction mot-
    par-mot en continu — voir RangeGroundTruth et evaluate.evaluate_window).

    `confirmed_ayahs` = préfixe CONSÉCUTIF d'ayahs entièrement reconnues depuis
    `start_ayah` (tous leurs mots content_ok) — c'est ce qui remplace l'ancienne
    hypothèse "cet audio EST l'ayah N" : au lieu de supposer, on mesure jusqu'où
    la récitation est allée, ce qui reste correct même sans pause entre ayahs."""
    surah: int
    start_ayah: int
    end_ayah: int
    audio_path: str
    duration: float
    aligner: str
    ayah_spans: List[Tuple[int, int, int]] = field(default_factory=list)  # (ayah, start_idx, end_idx)
    content_status: str = "unknown"
    content_cer: Optional[float] = None
    decoded_text: Optional[str] = None
    word_scores: List["WordScore"] = field(default_factory=list)  # noqa: F821
    confirmed_ayahs: List[int] = field(default_factory=list)
    # Roadmap V2 — "stuck cursor" fix (2026-07-08): if `confirmed_ayahs` doesn't
    # reach the end of the window (or is empty), but a LATER ayah in the window
    # still shows strong evidence of a match, `resume_ayah` = the ayah right
    # after it. Without this, a single failed confirmation (mic noise, a rough
    # first attempt) permanently strands the cursor: every LATER segment (which
    # by then contains later content) keeps getting compared against the same
    # un-advanced window start and can never match either. See evaluate_window.
    resume_ayah: Optional[int] = None

    def _ayah_for(self, start_idx: int) -> Optional[int]:
        for ayah, s, e in self.ayah_spans:
            if s <= start_idx < e:
                return ayah
        return None

    def _word_dict(self, w: "WordScore") -> dict:  # noqa: F821
        """Comme `w.to_dict()`, mais start_idx/end_idx REBASÉS pour être
        relatifs au début de LEUR PROPRE ayah, pas au début de toute la
        fenêtre/plage notée. `ayah_spans` (et donc `w.start_idx` d'origine)
        indexent le texte CONCATÉNÉ de plusieurs ayahs — le frontend
        (GradedSurah.tsx) les traite comme des offsets dans le texte d'UNE
        SEULE ayah (`v.text`, par verset). Sans ce rebasage, un mot de
        n'importe quelle ayah APRÈS la première de la plage a un start_idx
        bien plus grand que la longueur de son propre verset -> ne se colore
        jamais, silencieusement (trouvé 2026-07-08 sur une vraie session
        micro : ayah 4 marquée "pass" côté statut mais rendue en texte NOIR,
        non coloré, car sa plage notée avait commencé à une ayah précédente)."""
        ayah = self._ayah_for(w.start_idx)
        base = next((s for a, s, _e in self.ayah_spans if a == ayah), 0)
        d = w.to_dict()
        d["start_idx"] = w.start_idx - base
        d["end_idx"] = w.end_idx - base
        d["ayah"] = ayah
        return d

    def to_dict(self) -> dict:
        return {
            "surah": self.surah, "start_ayah": self.start_ayah, "end_ayah": self.end_ayah,
            "audio_path": self.audio_path, "duration_s": round(self.duration, 2),
            "aligner": self.aligner,
            "content_status": self.content_status,
            "content_cer": round(self.content_cer, 3) if self.content_cer is not None else None,
            "decoded_text": self.decoded_text,
            "confirmed_ayahs": self.confirmed_ayahs,
            "resume_ayah": self.resume_ayah,
            "word_scores": [self._word_dict(w) for w in self.word_scores],
        }


@dataclass
class ClipReport:
    """Rapport d'une notation "sourate = un seul paragraphe" (Roadmap V2,
    2026-07-08) — voir evaluate.evaluate_clip. Remplace WindowReport pour la
    récitation continue : pas de `start_ayah` fourni par l'appelant, pas de
    `confirmed_ayahs`/`resume_ayah` à gérer côté client — le clip est
    LOCALISÉ dans la sourate entière via son contenu décodé (content_check.
    locate_best_span), puis noté seulement sur la plage identifiée. Élimine
    la classe de bug "curseur bloqué" plutôt que de la contourner : il n'y a
    plus de curseur à faire avancer côté serveur non plus."""
    surah: int
    located: bool             # False si RIEN dans toute la sourate n'a matché
    audio_path: str
    duration: float
    aligner: str
    ayah_from: Optional[int] = None
    ayah_to: Optional[int] = None
    ayah_spans: List[Tuple[int, int, int]] = field(default_factory=list)  # (ayah, start_idx, end_idx) DANS LA PLAGE identifiée
    content_status: str = "unknown"    # "ok" | "content_mismatch" | "unknown"
    content_cer: Optional[float] = None
    decoded_text: Optional[str] = None
    word_scores: List["WordScore"] = field(default_factory=list)  # noqa: F821

    def _ayah_for(self, start_idx: int) -> Optional[int]:
        for ayah, s, e in self.ayah_spans:
            if s <= start_idx < e:
                return ayah
        return None

    def _word_dict(self, w: "WordScore") -> dict:  # noqa: F821
        """Comme `w.to_dict()`, mais start_idx/end_idx REBASÉS pour être
        relatifs au début de LEUR PROPRE ayah, pas au début de toute la plage
        localisée (`ayah_from`..`ayah_to`). `ayah_spans` (et donc le
        start_idx d'origine de `w`) indexent le texte CONCATÉNÉ de la plage
        entière — le frontend (GradedSurah.tsx) traite start_idx/end_idx
        comme des offsets dans le texte d'UNE SEULE ayah (`v.text`, par
        verset). Sans ce rebasage, un mot de n'importe quelle ayah APRÈS la
        première de la plage localisée a un start_idx bien plus grand que la
        longueur de son propre verset -> ne se colore jamais, silencieusement
        (trouvé 2026-07-08 sur une vraie session micro : une ayah marquée
        "pass" côté statut mais rendue en texte NOIR, non coloré, parce que
        ce clip avait été localisé sur une plage commençant à une ayah
        précédente)."""
        ayah = self._ayah_for(w.start_idx)
        base = next((s for a, s, _e in self.ayah_spans if a == ayah), 0)
        d = w.to_dict()
        d["start_idx"] = w.start_idx - base
        d["end_idx"] = w.end_idx - base
        d["ayah"] = ayah
        return d

    def to_dict(self) -> dict:
        return {
            "surah": self.surah, "located": self.located,
            "ayah_from": self.ayah_from, "ayah_to": self.ayah_to,
            "audio_path": self.audio_path, "duration_s": round(self.duration, 2),
            "aligner": self.aligner,
            "content_status": self.content_status,
            "content_cer": round(self.content_cer, 3) if self.content_cer is not None else None,
            "decoded_text": self.decoded_text,
            "word_scores": [self._word_dict(w) for w in self.word_scores],
        }
