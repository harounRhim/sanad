#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
src/tajweed/audio_mapper.py — Indexation audio multi-récitateurs.

Parcourt data/audio/ EN STREAMING (os.walk ne lit que des chemins ; les 36 Go
restent sur le disque) et produit audio_map.json à DEUX NIVEAUX :
    { récitateur : { "sourate:ayah" : chemin_relatif } }

Le dossier de premier niveau sous --audio-root est la clé récitateur ; la
convention de nommage (sourate/ayah) est détectée sur le RESTE du chemin, donc
un nom de récitateur contenant des chiffres ne fausse pas le parsing.

Exemples :
    python -m tajweed.audio_mapper --audio-root data/audio --text data/raw/quran-uthmani.txt --dry-run
    python -m tajweed.audio_mapper --audio-root data/audio --out data/processed/audio_map.json
    python -m tajweed.audio_mapper --audio-root data/audio --flat        # force un seul niveau
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set, Tuple

KNOWN_PATTERNS: List[Tuple[str, "re.Pattern[str]"]] = [
    ("concat_3_3", re.compile(r"(?<!\d)(\d{3})(\d{3})(?!\d)")),
    ("folder", re.compile(r"(?<!\d)0*(\d{1,3})[/\\]0*(?:\d{3})?(\d{1,3})(?!\d)")),
    ("separated", re.compile(r"(?<!\d)(\d{1,3})[ _\-.](\d{1,3})(?!\d)")),
    ("labelled", re.compile(r"(?:s|sura|surah)0*(\d{1,3}).*?(?:a|aya|ayah)0*(\d{1,3})", re.I)),
]
DEFAULT_EXTS = {".mp3", ".ogg", ".m4a", ".wav", ".opus", ".flac"}
ROOT_RECITER = "_root"  # pour les fichiers posés directement sous audio_root


# --------------------------- validation versets ----------------------------

def load_valid_keys(text_path: Optional[Path]) -> Optional[Set[Tuple[int, int]]]:
    if text_path is None:
        return None
    keys: Set[Tuple[int, int]] = set()
    with text_path.open(encoding="utf-8-sig") as fh:
        for line in fh:
            p = line.split("|")
            if len(p) == 3 and p[0].strip().isdigit() and p[1].strip().isdigit():
                keys.add((int(p[0]), int(p[1])))
    return keys or None


def is_valid(surah: int, ayah: int, valid_keys: Optional[Set[Tuple[int, int]]]) -> bool:
    if valid_keys is not None:
        return (surah, ayah) in valid_keys
    return 1 <= surah <= 114 and ayah >= 1


# ----------------------------- scan streaming ------------------------------

def iter_audio_files(audio_root: Path, exts: Set[str]) -> Iterator[Tuple[str, str]]:
    """(relpath_posix, fullpath) pour chaque fichier audio. Ne lit aucun octet."""
    for dirpath, dirnames, filenames in os.walk(audio_root):
        dirnames.sort()
        for name in sorted(filenames):
            if Path(name).suffix.lower() not in exts:
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, audio_root).replace(os.sep, "/")
            yield rel, full


def split_reciter(rel: str, flat: bool) -> Tuple[str, str]:
    """Sépare (récitateur, sous-chemin). En --flat, tout est sous un seul niveau."""
    if flat:
        return ROOT_RECITER, rel
    parts = rel.split("/")
    if len(parts) >= 2:
        return parts[0], "/".join(parts[1:])
    return ROOT_RECITER, rel  # fichier directement sous audio_root


def parse_key(subpath: str, pattern: "re.Pattern[str]",
              valid_keys: Optional[Set[Tuple[int, int]]]) -> Optional[Tuple[int, int]]:
    m = pattern.search(subpath)
    if not m:
        return None
    try:
        surah, ayah = int(m.group(1)), int(m.group(2))
    except (ValueError, IndexError):
        return None
    return (surah, ayah) if is_valid(surah, ayah, valid_keys) else None


def detect_pattern(subpaths: List[str],
                   valid_keys: Optional[Set[Tuple[int, int]]]) -> Tuple[str, "re.Pattern[str]"]:
    """Choisit la convention qui matche le plus de sous-chemins (récitateur retiré)."""
    best_name, best_pat, best_hits = "", None, -1
    for name, pat in KNOWN_PATTERNS:
        hits = sum(1 for sp in subpaths if parse_key(sp, pat, valid_keys) is not None)
        if hits > best_hits:
            best_name, best_pat, best_hits = name, pat, hits
    if best_pat is None or best_hits <= 0:
        raise SystemExit(
            "Aucune convention reconnue. Fournis --regex avec 2 groupes (sourate)(ayah)."
        )
    return best_name, best_pat


# --------------------------- construction de la map ------------------------

def build_map(audio_root: Path, exts: Set[str], regex: Optional[str], flat: bool,
              valid_keys: Optional[Set[Tuple[int, int]]]) -> dict:
    files = list(iter_audio_files(audio_root, exts))  # liste de CHEMINS (léger)
    if not files:
        raise SystemExit(f"Aucun fichier audio sous {audio_root}")

    # (récitateur, sous-chemin, relpath_complet)
    split = [(*split_reciter(rel, flat), rel) for rel, _ in files]
    subpaths = [sp for _, sp, _ in split]

    if regex:
        pattern, pattern_name = re.compile(regex), "custom"
    else:
        pattern_name, pattern = detect_pattern(subpaths, valid_keys)

    mapping: Dict[str, Dict[str, str]] = defaultdict(dict)
    duplicates: List[Tuple[str, str, str]] = []   # (récitateur, clé, relpath)
    unmatched: List[str] = []

    for reciter, subpath, rel in split:
        key = parse_key(subpath, pattern, valid_keys)
        if key is None:
            unmatched.append(rel)
            continue
        skey = f"{key[0]}:{key[1]}"
        if skey in mapping[reciter]:               # doublon DANS un récitateur
            duplicates.append((reciter, skey, rel))
            continue
        mapping[reciter][skey] = rel

    return {
        "pattern_name": pattern_name,
        "mapping": {r: dict(d) for r, d in mapping.items()},
        "duplicates": duplicates,
        "unmatched": unmatched,
        "n_files": len(files),
        "flat": flat,
    }


def report(result: dict, valid_keys: Optional[Set[Tuple[int, int]]]) -> Dict[str, int]:
    mapping = result["mapping"]
    reciters = sorted(mapping)
    print(f"Convention détectée : {result['pattern_name']}")
    print(f"Fichiers audio scannés : {result['n_files']}")
    print(f"Récitateurs détectés   : {len(reciters)}  ({', '.join(reciters)})")

    missing_per: Dict[str, int] = {}
    for r in reciters:
        n = len(mapping[r])
        line = f"  • {r:20} {n} versets"
        if valid_keys is not None:
            mapped = {tuple(int(x) for x in k.split(":")) for k in mapping[r]}
            miss = len(valid_keys - mapped)
            missing_per[r] = miss
            line += f"  (manquants : {miss})"
        print(line)

    if result["duplicates"]:
        print(f"\n[ATTENTION] {len(result['duplicates'])} doublons INTRA-récitateur "
              f"(même verset, plusieurs fichiers) — premier conservé. Ex :")
        for reciter, skey, rel in result["duplicates"][:5]:
            print(f"    [{reciter}] {skey}  <-  {rel}")

    if result["unmatched"]:
        print(f"\n[INFO] {len(result['unmatched'])} fichiers non reconnus "
              f"(bismillah, sourates entières…). Ex :")
        for rel in result["unmatched"][:5]:
            print(f"    {rel}")
    return missing_per


def write_map(out_path: Path, audio_root: Path, result: dict,
              missing_per: Dict[str, int]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mapping = result["mapping"]
    reciters = sorted(mapping)
    # Tri stable des clés versets dans chaque récitateur.
    sorted_map = {
        r: dict(sorted(mapping[r].items(),
                       key=lambda kv: tuple(int(x) for x in kv[0].split(":"))))
        for r in reciters
    }
    doc = {
        "version": 2,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0)
        .isoformat().replace("+00:00", "Z"),
        "audio_root": str(audio_root).replace(os.sep, "/"),
        "pattern": result["pattern_name"],
        "multi_reciter": not result["flat"],
        "reciters": reciters,
        "count": {r: len(sorted_map[r]) for r in reciters},
        "missing_count": missing_per or {r: None for r in reciters},
        "map": sorted_map,
    }
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
    total = sum(len(v) for v in sorted_map.values())
    print(f"\n✅ Écrit : {out_path}  ({len(reciters)} récitateurs, {total} entrées)")


# ----------------------------------- CLI -----------------------------------

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Construit audio_map.json multi-récitateurs (streaming).")
    p.add_argument("--audio-root", type=Path, default=Path("data/audio"))
    p.add_argument("--out", type=Path, default=Path("data/processed/audio_map.json"))
    p.add_argument("--text", type=Path, default=None,
                   help="quran-uthmani.txt (optionnel) pour valider et mesurer la couverture.")
    p.add_argument("--regex", default=None, help="Motif personnalisé : 2 groupes (sourate)(ayah).")
    p.add_argument("--ext", action="append", default=None, help="Extension audio (répétable).")
    p.add_argument("--flat", action="store_true", help="Forcer une map à un seul niveau.")
    p.add_argument("--dry-run", action="store_true", help="Rapport seulement, n'écrit rien.")
    args = p.parse_args(argv)

    if not args.audio_root.exists():
        raise SystemExit(f"Dossier audio introuvable : {args.audio_root}")
    exts = {e if e.startswith(".") else "." + e for e in (args.ext or [])} or set(DEFAULT_EXTS)

    valid_keys = load_valid_keys(args.text)
    result = build_map(args.audio_root, exts, args.regex, args.flat, valid_keys)
    missing_per = report(result, valid_keys)

    if args.dry_run:
        print("\n(dry-run : aucun fichier écrit)")
        return 0
    write_map(args.out, args.audio_root, result, missing_per)
    return 0


if __name__ == "__main__":
    sys.exit(main())
