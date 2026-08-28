# -*- coding: utf-8 -*-
"""
src/tajweed/quran_text.py — Chargement du texte uthmani.

Le fichier tajweed n'embarque QUE des offsets de caractères (start/end) ; le
texte réel des segments doit donc être tranché dans le verset correspondant.
Cette fonction construit l'index { (sourate, ayah) : texte } consommé par
extractor.iter_segments.

Format attendu (quran-uthmani.txt, encodage utf-8-sig) :
    sourate|ayah|texte
Les lignes vides ou mal formées (séparateurs de sourate, BOM, etc.) sont
ignorées silencieusement.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple


def load_verses(path: Path) -> Dict[Tuple[int, int], str]:
    """Renvoie { (sourate, ayah) : texte_uthmani } depuis quran-uthmani.txt."""
    verses: Dict[Tuple[int, int], str] = {}
    with Path(path).open(encoding="utf-8-sig") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("|")
            if len(parts) != 3:
                continue
            surah, ayah, text = (p.strip() for p in parts)
            if not (surah.isdigit() and ayah.isdigit()):
                continue
            verses[(int(surah), int(ayah))] = text
    if not verses:
        raise SystemExit(f"Aucun verset chargé depuis {path} (format inattendu ?).")
    return verses
