# -*- coding: utf-8 -*-
"""
src/tajweed/correction/ground_truth.py — Référence (texte + segments Tajweed).

La « vérité terrain » d'une ayah = son texte uthmani + ses segments Tajweed
(règle, start_idx, end_idx indexant CE texte). Deux sources :
  - LOCAL  : quran-uthmani.txt + tajweed JSON (hors-ligne, sans réseau) ;
  - SUPABASE : tables `verses` et `tajweed_segments` (déjà peuplées).

Les deux renvoient le même objet `GroundTruth`, consommé par evaluate.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:  # package ou script isolé
    from ..quran_text import load_verses
    from ..extractor import RULE_LABELS
except ImportError:  # pragma: no cover
    from tajweed.quran_text import load_verses  # type: ignore
    from tajweed.extractor import RULE_LABELS  # type: ignore

import ijson


@dataclass
class GTSegment:
    rule: str
    start_idx: int
    end_idx: int
    segment: str


@dataclass
class GroundTruth:
    surah: int
    ayah: int
    text: str
    segments: List[GTSegment]


@dataclass
class AyahSpan:
    """Char offsets of ONE ayah's text within a RangeGroundTruth's concatenated
    `text` — lets callers map a word/segment position back to its owning ayah."""
    ayah: int
    start: int
    end: int


@dataclass
class RangeGroundTruth:
    """Vérité terrain sur une FENÊTRE de plusieurs ayahs consécutives (Roadmap V2
    — correction mot-par-mot en continu, pas ayah-par-ayah).

    Pourquoi : une récitation fluide (peu/pas de pause entre ayahs) ne peut PAS
    être découpée fiablement en segments "une ayah = un silence" — voir le bug
    2026-07-07 (tout finissait attribué à l'ayah 1). Au lieu de supposer QUELLE
    ayah a été récitée, on aligne le clip contre une fenêtre de PLUSIEURS ayahs
    à venir et on mesure jusqu'où ça matche (cf. evaluate.evaluate_window)."""
    surah: int
    start_ayah: int
    end_ayah: int          # dernière ayah RÉELLEMENT incluse (peut être < start_ayah+count-1 si fin de sourate)
    text: str              # texte concaténé (ayahs séparées par un espace)
    segments: List[GTSegment]     # segments Tajweed, offsets réajustés dans `text`
    ayah_spans: List[AyahSpan]    # bornes de chaque ayah dans `text`, dans l'ordre


# ------------------------------- local -------------------------------------

class LocalGroundTruth:
    """Source hors-ligne depuis les fichiers du dépôt.

    Index les segments Tajweed en RAM au premier accès (une seule passe
    streaming sur le JSON — quelques Mo, ~6236 ayahs × 18 règles), pas à
    chaque get()/get_range(). AVANT ce cache (jusqu'au 2026-07-08),
    get()/get_range() rappelaient `iter_segments` — qui RE-SCANNE le fichier
    JSON entier depuis le disque — une fois PAR RÈGLE PAR AYAH (18×N appels).
    Pour une seule ayah (get()) c'était lent mais tolérable (~18 scans) ; pour
    une SOURATE ENTIÈRE (get_range avec un grand `count`, voir evaluate_clip
    et "sourate = un paragraphe") ça devenait 18×286 ≈ 5000 scans pour
    Al-Baqara — mesuré à l'origine de ce fix : ~15s perdues à charger la
    vérité terrain d'Al-Fatiha (7 ayahs) à CHAQUE appel, pour une seule passe
    de décodage modèle de 2s. Le cache ramène ça à UNE lecture fichier pour
    toute la durée de vie du processus serveur."""

    def __init__(self, text_path: Path, json_path: Path):
        self.json_path = Path(json_path)
        self._verses: Dict[Tuple[int, int], str] = load_verses(Path(text_path))
        self._segments_by_ayah: Optional[Dict[Tuple[int, int], List[GTSegment]]] = None

    def _index(self) -> Dict[Tuple[int, int], List[GTSegment]]:
        if self._segments_by_ayah is None:
            index: Dict[Tuple[int, int], List[GTSegment]] = {}
            with self.json_path.open("rb") as fh:
                for obj in ijson.items(fh, "item"):
                    s, a = int(obj["surah"]), int(obj["ayah"])
                    text = self._verses.get((s, a))
                    if text is None:
                        continue
                    segs = []
                    for ann in obj.get("annotations", []):
                        rule = ann.get("rule")
                        if rule not in RULE_LABELS:
                            continue
                        start, end = int(ann["start"]), int(ann["end"])
                        segs.append(GTSegment(rule, start, end, text[start:end]))
                    segs.sort(key=lambda g: (g.start_idx, g.end_idx))
                    index[(s, a)] = segs
            self._segments_by_ayah = index
        return self._segments_by_ayah

    def get(self, surah: int, ayah: int) -> GroundTruth:
        text = self._verses.get((surah, ayah))
        if text is None:
            raise KeyError(f"Ayah introuvable dans le texte : {surah}:{ayah}")
        segs = list(self._index().get((surah, ayah), []))
        return GroundTruth(surah, ayah, text, segs)

    def get_range(self, surah: int, start_ayah: int, count: int) -> RangeGroundTruth:
        """Concatène jusqu'à `count` ayahs à partir de `start_ayah` (moins si la
        sourate se termine avant) en UN texte, avec segments + bornes par-ayah
        réajustés dans ce texte combiné."""
        index = self._index()
        spans: List[AyahSpan] = []
        segments: List[GTSegment] = []
        combined = ""
        end_ayah: Optional[int] = None
        ayah = start_ayah
        for _ in range(count):
            text = self._verses.get((surah, ayah))
            if text is None:
                break
            if combined:
                combined += " "
            start = len(combined)
            combined += text
            end = len(combined)
            spans.append(AyahSpan(ayah, start, end))
            for seg in index.get((surah, ayah), []):
                segments.append(GTSegment(seg.rule, seg.start_idx + start,
                                          seg.end_idx + start, seg.segment))
            end_ayah = ayah
            ayah += 1
        if not spans or end_ayah is None:
            raise KeyError(f"Aucune ayah trouvée à partir de {surah}:{start_ayah}")
        segments.sort(key=lambda g: (g.start_idx, g.end_idx))
        return RangeGroundTruth(surah, start_ayah, end_ayah, combined, segments, spans)


# ------------------------------ supabase -----------------------------------

class SupabaseGroundTruth:
    """Source en ligne depuis les tables Supabase déjà peuplées."""

    def __init__(self, client=None):
        if client is None:
            try:
                from ..config import supabase_credentials
            except ImportError:  # pragma: no cover
                from tajweed.config import supabase_credentials  # type: ignore
            from supabase import create_client
            url, key = supabase_credentials()
            client = create_client(url, key)
        self.client = client

    def get(self, surah: int, ayah: int) -> GroundTruth:
        v = (self.client.table("verses").select("text")
             .eq("surah", surah).eq("ayah", ayah).maybe_single().execute())
        if not v.data:
            raise KeyError(f"Ayah introuvable dans verses : {surah}:{ayah}")
        text = v.data["text"]
        rows = (self.client.table("tajweed_segments")
                .select("rule,start_idx,end_idx,segment")
                .eq("surah", surah).eq("ayah", ayah).execute()).data or []
        segs = [GTSegment(r["rule"], r["start_idx"], r["end_idx"], r["segment"])
                for r in rows]
        segs.sort(key=lambda g: (g.start_idx, g.end_idx))
        return GroundTruth(surah, ayah, text, segs)

    def get_range(self, surah: int, start_ayah: int, count: int) -> RangeGroundTruth:
        last_ayah = start_ayah + count - 1
        rows = (self.client.table("verses").select("ayah,text")
                .eq("surah", surah).gte("ayah", start_ayah).lte("ayah", last_ayah)
                .order("ayah").execute()).data or []
        if not rows:
            raise KeyError(f"Aucune ayah trouvée à partir de {surah}:{start_ayah}")
        seg_rows = (self.client.table("tajweed_segments")
                    .select("ayah,rule,start_idx,end_idx,segment")
                    .eq("surah", surah).gte("ayah", start_ayah).lte("ayah", last_ayah)
                    .execute()).data or []
        by_ayah: Dict[int, List[dict]] = {}
        for r in seg_rows:
            by_ayah.setdefault(r["ayah"], []).append(r)

        spans: List[AyahSpan] = []
        segments: List[GTSegment] = []
        combined = ""
        end_ayah: Optional[int] = None
        for row in rows:
            ayah, text = row["ayah"], row["text"]
            if combined:
                combined += " "
            start = len(combined)
            combined += text
            end = len(combined)
            spans.append(AyahSpan(ayah, start, end))
            for s in by_ayah.get(ayah, []):
                segments.append(GTSegment(s["rule"], s["start_idx"] + start,
                                          s["end_idx"] + start, s["segment"]))
            end_ayah = ayah
        segments.sort(key=lambda g: (g.start_idx, g.end_idx))
        return RangeGroundTruth(surah, start_ayah, end_ayah, combined, segments, spans)
