# -*- coding: utf-8 -*-
"""
Fragment pour src/tajweed/extractor.py — enrichissement audio des segments.

Ces deux fonctions se branchent sur le flux produit par iter_segments() :
on charge UNE fois le petit index audio_map.json en RAM (c'est voulu), puis
on enrichit chaque segment à la volée. Le streaming d'ijson n'est pas rompu :
enrich_with_audio est un générateur qui enveloppe un générateur.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterator, Optional, Tuple

# ijson : streaming du gros fichier d'annotations sans saturer la RAM.
import ijson


# ------------------------- vocabulaire des règles --------------------------
# Les 18 règles présentes dans tajweed.hafs.uthmani-pause-sajdah.json, avec un
# libellé lisible. La clé canonique est celle stockée en base (champ `rule`).
RULE_LABELS: Dict[str, str] = {
    "hamzat_wasl": "Hamzat al-Wasl",
    "madd_2": "Madd (2 temps)",
    "ikhfa": "Ikhfa",
    "ghunnah": "Ghunnah",
    "madd_246": "Madd (2/4/6 temps)",
    "silent": "Lettre muette",
    "idghaam_ghunnah": "Idghaam avec Ghunnah",
    "qalqalah": "Qalqalah",
    "madd_munfasil": "Madd Munfasil",
    "lam_shamsiyyah": "Lam Shamsiyyah",
    "madd_muttasil": "Madd Muttasil",
    "idghaam_no_ghunnah": "Idghaam sans Ghunnah",
    "idghaam_shafawi": "Idghaam Shafawi",
    "iqlab": "Iqlab",
    "ikhfa_shafawi": "Ikhfa Shafawi",
    "madd_6": "Madd (6 temps)",
    "idghaam_mutajanisayn": "Idghaam Mutajanisayn",
    "idghaam_mutaqaribayn": "Idghaam Mutaqaribayn",
}


def canonical_rule(name: str) -> str:
    """Normalise un nom de règle saisi en CLI vers sa clé canonique.

    Tolère la casse, les espaces et les tirets (« Madd 2 », « madd-2 » -> madd_2).
    Lève une erreur claire si la règle est inconnue.
    """
    key = name.strip().lower().replace(" ", "_").replace("-", "_")
    if key not in RULE_LABELS:
        raise SystemExit(
            f"Règle inconnue : '{name}'. Disponibles : {', '.join(sorted(RULE_LABELS))}"
        )
    return key


# ------------------------- extraction des segments -------------------------

def _enclosing_word(text: str, start: int, end: int) -> str:
    """Mot (délimité par des espaces) qui contient l'intervalle [start, end)."""
    left = text.rfind(" ", 0, start) + 1          # 0 si aucun espace avant
    right = text.find(" ", end)
    if right == -1:
        right = len(text)
    return text[left:right]


def iter_segments(json_path: Path, verses: Dict[Tuple[int, int], str], rule: str,
                  surah: Optional[int] = None, ayah: Optional[int] = None) -> Iterator[dict]:
    """Stream les segments d'UNE règle depuis le fichier d'annotations.

    Le fichier est un tableau d'objets { surah, ayah, annotations:[{start,end,rule}] }.
    On le parcourt en streaming via ijson (chaque objet ayah est petit), on
    filtre par règle (et éventuellement sourate/ayah), puis on tranche le texte
    uthmani pour matérialiser `segment` et le `word` englobant.

    Yield des dicts prêts pour SupabaseLoader :
        {surah, ayah, rule, start, end, segment, word}
    """
    with Path(json_path).open("rb") as fh:
        for obj in ijson.items(fh, "item"):
            s, a = int(obj["surah"]), int(obj["ayah"])
            if surah is not None and s != surah:
                continue
            if ayah is not None and a != ayah:
                continue
            text = verses.get((s, a))
            if text is None:                       # verset absent du texte -> ignoré
                continue
            for ann in obj.get("annotations", []):
                if ann.get("rule") != rule:
                    continue
                start, end = int(ann["start"]), int(ann["end"])
                yield {
                    "surah": s,
                    "ayah": a,
                    "rule": rule,
                    "start": start,
                    "end": end,
                    "segment": text[start:end],
                    "word": _enclosing_word(text, start, end),
                }


def load_audio_map(path: Path) -> dict:
    """Charge audio_map.json en entier (quelques centaines de Ko : l'index O(1))."""
    with Path(path).open(encoding="utf-8") as fh:
        doc = json.load(fh)
    if "map" not in doc:
        raise ValueError(f"{path} : format audio_map invalide (clé 'map' absente).")
    return doc


def _join(root: str, rel: Optional[str]) -> Optional[str]:
    if not rel:
        return None
    return f"{root.rstrip('/')}/{rel}" if root else rel


def enrich_with_audio(segments: Iterator[dict], audio_map: dict,
                      reciter: Optional[str] = None) -> Iterator[dict]:
    """Ajoute le(s) chemin(s) audio à chaque segment, en restant en streaming.

    - multi-récitateurs + `reciter` précisé -> champs 'reciter' et 'audio_path'
    - multi-récitateurs sans `reciter`       -> champ 'audio_paths' {récitateur: chemin}
    - map plate (mono)                        -> champ 'audio_path'

    Un verset sans audio donne un chemin None (jamais d'exception) : libre au
    consommateur de filtrer.
    """
    root = audio_map.get("audio_root", "")
    amap: Dict[str, object] = audio_map["map"]
    multi = audio_map.get("multi_reciter")
    if multi is None:  # rétro-compat : déduire de la forme du fichier
        multi = bool(amap) and isinstance(next(iter(amap.values())), dict)

    if multi and reciter is not None and reciter not in amap:
        raise SystemExit(
            f"Récitateur inconnu : '{reciter}'. Disponibles : {', '.join(sorted(amap))}"
        )

    for seg in segments:
        key = f"{seg['surah']}:{seg['ayah']}"
        if multi:
            if reciter is not None:
                seg["reciter"] = reciter
                seg["audio_path"] = _join(root, amap[reciter].get(key))
            else:
                seg["audio_paths"] = {
                    r: _join(root, verses[key])
                    for r, verses in amap.items() if key in verses
                }
        else:
            seg["audio_path"] = _join(root, amap.get(key))
        yield seg