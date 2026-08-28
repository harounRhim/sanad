#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
src/tajweed/replay_dead_letter.py — Rejeu des lignes en échec.

Lit data/processed/dead_letter.jsonl (chaque ligne : {ts, table, row}), regroupe
par table et ré-upsert via SupabaseLoader.upsert_rows (mêmes clés on_conflict,
mêmes retries). Les lignes encore en échec sont écrites dans un NOUVEAU fichier
dead-letter résiduel — jamais celui qu'on est en train de lire — pour pouvoir
rejouer plusieurs fois jusqu'à convergence.

Exemples :
    python -m tajweed.replay_dead_letter
    python -m tajweed.replay_dead_letter --infile data/processed/dead_letter.jsonl
    python -m tajweed.replay_dead_letter --dry-run     # compte seulement, n'écrit pas
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

try:
    from .supabase_loader import SupabaseLoader
except ImportError:  # exécution hors package
    from supabase_loader import SupabaseLoader


def read_dead_letter(path: Path) -> Dict[str, List[dict]]:
    """Regroupe les lignes par table. Les lignes illisibles sont ignorées (signalées)."""
    by_table: Dict[str, List[dict]] = defaultdict(list)
    bad = 0
    with path.open(encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                table, row = rec["table"], rec["row"]
            except (json.JSONDecodeError, KeyError):
                bad += 1
                print(f"[WARN] ligne {n} illisible — ignorée.", file=sys.stderr)
                continue
            # On ne rejoue que les vraies tables (pas les entrées d'input malformé).
            if table.startswith("_"):
                continue
            by_table[table].append(row)
    if bad:
        print(f"[WARN] {bad} ligne(s) illisible(s) au total.", file=sys.stderr)
    return by_table


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Rejoue les lignes du dead-letter vers Supabase.")
    p.add_argument("--infile", type=Path, default=Path("data/processed/dead_letter.jsonl"))
    p.add_argument("--residual", type=Path, default=Path("data/processed/dead_letter.replay.jsonl"),
                   help="Fichier des lignes encore en échec après ce rejeu.")
    p.add_argument("--batch-size", type=int, default=500)
    p.add_argument("--dry-run", action="store_true", help="Compter seulement, ne pas insérer.")
    args = p.parse_args(argv)

    if not args.infile.exists():
        raise SystemExit(f"Fichier introuvable : {args.infile}")

    by_table = read_dead_letter(args.infile)
    if not by_table:
        print("Rien à rejouer (aucune ligne de table valide).")
        return 0

    for table, rows in by_table.items():
        print(f"{table}: {len(rows)} ligne(s) à rejouer")
    if args.dry_run:
        print("\n(dry-run : aucune insertion)")
        return 0

    # Le résiduel va dans un fichier DISTINCT de l'entrée (jamais en boucle).
    loader = SupabaseLoader(batch_size=args.batch_size, dead_letter_path=args.residual)
    total_ok = total_fail = 0
    with loader:
        for table, rows in by_table.items():
            ok, fail = loader.upsert_rows(table, rows)
            total_ok += ok
            total_fail += fail
            print(f"  {table}: {ok} ré-insérées, {fail} encore en échec")

    print(f"\nTotal : {total_ok} ré-insérées, {total_fail} en échec.")
    if total_fail:
        print(f"Lignes encore en échec écrites dans {args.residual} "
              f"(renomme-le en {args.infile.name} pour un nouveau rejeu).")
    else:
        print("✅ Dead-letter entièrement résorbé.")
    return 0


if __name__ == "__main__":
    sys.exit(main())