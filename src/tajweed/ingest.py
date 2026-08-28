#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
src/tajweed/ingest.py — Commande unique d'ingestion.

Orchestre tout le pipeline EN STREAMING :
    quran-uthmani.txt + annotations.json + audio_map.json
      -> iter_segments (ijson)
      -> enrich_with_audio
      -> SupabaseLoader (batching + dead-letter)

Exemples :
    python -m tajweed.ingest --rule ghunnah
    python -m tajweed.ingest --rule ghunnah --reciter alafasy --seed-audio
    python -m tajweed.ingest --all-rules --seed-audio --batch-size 1000

Variables d'environnement requises : SUPABASE_URL, SUPABASE_KEY (clé service_role
côté serveur recommandée pour l'ingestion en masse).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Imports tolérants : fonctionnent en package (python -m) ou à plat.
try:
    from .quran_text import load_verses
    from .metadata import (load_surahs, load_juz, load_pages, verse_rows,
                           load_translations)
    from .extractor import (iter_segments, enrich_with_audio,
                            load_audio_map, RULE_LABELS, canonical_rule)
    from .supabase_loader import SupabaseLoader
except ImportError:
    from quran_text import load_verses
    from metadata import (load_surahs, load_juz, load_pages, verse_rows,
                          load_translations)
    from extractor import (iter_segments, enrich_with_audio,
                           load_audio_map, RULE_LABELS, canonical_rule)
    from supabase_loader import SupabaseLoader

# tqdm optionnel : si absent, on dégrade proprement vers l'identité.
try:
    from tqdm import tqdm
except ImportError:
    def tqdm(it, **kw):  # type: ignore
        return it


def run(args) -> int:
    verses = load_verses(args.text)
    audio_map = load_audio_map(args.audio_map)

    # Quelles règles ingérer ?
    if args.all_rules:
        rules = list(RULE_LABELS)
    else:
        rules = [canonical_rule(args.rule)]

    loader = SupabaseLoader(
        batch_size=args.batch_size,
        dead_letter_path=args.dead_letter,
    )

    with loader:
        # 0. Amorçage métadonnées : sourates + texte uthmani des versets.
        if args.seed_meta:
            print("Amorçage de surahs depuis quran_.json…")
            surahs = load_surahs(args.quran_json)
            loader.seed_surahs(surahs)
            print(f"  -> {loader.stats['surahs_inserted']} sourates insérées.")
            print("Amorçage de juz (30)…")
            loader.seed_juz(load_juz(surahs))
            print(f"  -> {loader.stats['juz_inserted']} juz insérés.")
            print("Amorçage de pages du mushaf (604)…")
            loader.seed_pages(load_pages(surahs))
            print(f"  -> {loader.stats['pages_inserted']} pages insérées.")
            print("Amorçage de verses (texte uthmani + traduction + recherche)…")
            translations = load_translations(args.quran_json)
            loader.seed_verses(verse_rows(verses, translations))
            print(f"  -> {loader.stats['verses_inserted']} versets insérés.")

        # 1. Amorçage audio complet (optionnel, une seule fois).
        if args.seed_audio:
            print("Amorçage de ayah_audio depuis audio_map.json…")
            loader.seed_audio_from_map(audio_map)
            print(f"  -> {loader.stats['audio_inserted']} lignes audio insérées.")

        # 2. Ingestion des segments, règle par règle, en streaming.
        for rule in rules:
            label = RULE_LABELS.get(rule, rule)
            segments = iter_segments(args.json, verses, rule,
                                     surah=args.surah, ayah=args.ayah)
            enriched = enrich_with_audio(segments, audio_map, reciter=args.reciter)
            progress = tqdm(enriched, desc=f"{rule:18}", unit=" seg")
            loader.load(progress)

    s = loader.stats
    print("\n=== Bilan d'ingestion ===")
    print(f"Sourates insérées  : {s['surahs_inserted']}")
    print(f"Juz insérés        : {s['juz_inserted']}")
    print(f"Pages insérées     : {s['pages_inserted']}")
    print(f"Versets insérés    : {s['verses_inserted']}")
    print(f"Segments vus       : {s['segments_seen']}")
    print(f"Segments insérés   : {s['segments_inserted']}")
    print(f"Audio insérées     : {s['audio_inserted']}")
    print(f"Échecs segments    : {s['segments_failed']}")
    print(f"Échecs audio       : {s['audio_failed']}")
    print(f"Échecs s/j/p/v     : {s['surahs_failed']}/{s['juz_failed']}/{s['pages_failed']}/{s['verses_failed']}")
    print(f"Lots en échec      : {s['batch_failures']}")
    if (s['segments_failed'] or s['audio_failed'] or s['surahs_failed']
            or s['juz_failed'] or s['pages_failed'] or s['verses_failed']):
        print(f"\n⚠️  Des lignes sont en dead-letter ({args.dead_letter}). "
              f"Rejoue-les avec :  python -m tajweed.replay_dead_letter")
    else:
        print("\n✅ Ingestion terminée sans perte.")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Ingestion Tajweed -> Supabase (streaming).")
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--rule", help="Règle à ingérer (ex: ghunnah).")
    grp.add_argument("--all-rules", action="store_true", help="Ingérer les 18 règles.")

    p.add_argument("--surah", type=int, help="Filtrer sur une sourate.")
    p.add_argument("--ayah", type=int, help="Filtrer sur une ayah (nécessite --surah).")
    p.add_argument("--reciter", default=None,
                   help="Récitateur précis (sinon : tous, via audio_paths).")
    p.add_argument("--seed-audio", action="store_true",
                   help="Peupler ayah_audio pour TOUS les versets avant l'ingestion.")
    p.add_argument("--seed-meta", action="store_true",
                   help="Peupler surahs (noms) + verses (texte uthmani) avant l'ingestion.")

    p.add_argument("--text", type=Path, default=Path("data/raw/quran-uthmani.txt"))
    p.add_argument("--quran-json", type=Path,
                   default=Path("Data/audio/data/quran_.json"),
                   help="Métadonnées de sourates (noms, ayah_count) pour --seed-meta.")
    p.add_argument("--json", type=Path,
                   default=Path("data/raw/tajweed.hafs.uthmani-pause-sajdah.json"))
    p.add_argument("--audio-map", type=Path, default=Path("data/processed/audio_map.json"))
    p.add_argument("--dead-letter", type=Path, default=Path("data/processed/dead_letter.jsonl"))
    p.add_argument("--batch-size", type=int, default=500)

    args = p.parse_args(argv)
    if args.ayah is not None and args.surah is None:
        p.error("--ayah nécessite --surah.")
    for f in (args.text, args.json, args.audio_map):
        if not f.exists():
            raise SystemExit(f"Fichier introuvable : {f}")
    if args.seed_meta and not args.quran_json.exists():
        raise SystemExit(f"Fichier introuvable : {args.quran_json} (requis par --seed-meta)")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())