#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
src/tajweed/audio_correct.py — Correction pilotée par le rapport audio_verify.

Consomme `audio_verify_report.json` et applique deux corrections RÉVERSIBLES :

  1. RÉÉCRITURE de audio_map.json  — retire les entrées (récitateur, ayah)
     identifiées comme mauvaises, met à jour count/missing_count. L'original est
     sauvegardé en .bak.<timestamp> avant écrasement.
  2. SIGNALEMENT dans ayah_audio   — passe `verified=false` + `flag_reason` sur
     les lignes concernées (jamais de DELETE : on garde la trace, l'app filtre
     sur verified=true). Idempotent ; `--reset-flags` annule tous les signalements.

Deux familles d'anomalies, traitées différemment :
  - INTÉGRITÉ (empty/tiny/corrupt/unreadable/zero_duration/missing) — confirmées
    cassées → corrigées par défaut.
  - PLAUSIBILITÉ (durée aberrante) — file de REVUE, pas une preuve (ex. un
    récitateur-enseignant). Incluses seulement avec --include-plausibility.

SÉCURITÉ : par défaut DRY-RUN (n'écrit rien, ne touche pas la base). Il faut
--apply pour écrire la map et pousser les updates. La clé service_role vient de
.env (jamais en dur), via config.supabase_credentials().

Exemples :
    # aperçu : ce qui serait corrigé (intégrité seule)
    python -m tajweed.audio_correct --report Data/processed/audio_verify_report_full.json

    # appliquer : réécrire la map + signaler en base (intégrité + revue)
    python -m tajweed.audio_correct --report ..._full.json --include-plausibility --apply

    # tout ré-autoriser (verified=true partout)
    python -m tajweed.audio_correct --reset-flags --apply
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

try:  # package ou script isolé
    from .config import supabase_credentials
except ImportError:
    from config import supabase_credentials  # type: ignore

Key = Tuple[int, int]
INTEGRITY_STATUSES = {"empty", "tiny", "corrupt", "unreadable", "zero_duration", "missing"}


# --------------------------- lecture du rapport ----------------------------

def _parse_key(skey: str) -> Key:
    s, a = skey.split(":")
    return int(s), int(a)


def collect_bad(report: dict, include_plausibility: bool,
                ratio_high: float = 5.0, ratio_low: float = 0.2
                ) -> Dict[str, Dict[Key, str]]:
    """{ récitateur : { (s,a) : raison } } à partir du rapport.

    Toujours l'intégrité (cassée, confirmée). La plausibilité seulement si
    demandée ET SEULEMENT le grossier : ratio durée/attendu ≥ ratio_high ou
    ≤ ratio_low — la majorité des aberrants de durée relève du style (mujawwad,
    madd) et ne doit PAS être signalée. En cas de double signalement, l'intégrité
    prime sur la revue.
    """
    bad: Dict[str, Dict[Key, str]] = {}
    for reciter, entry in report.get("reciters", {}).items():
        if "error" in entry:
            continue
        per: Dict[Key, str] = {}
        if include_plausibility:
            for o in entry.get("plausibility", {}).get("outliers", []):
                ratio = o.get("ratio", 1.0)
                if ratio >= ratio_high or ratio <= ratio_low:
                    per[_parse_key(o["key"])] = f"review:{o['reason']}({ratio}x)"
        for b in entry.get("integrity", {}).get("bad", []):
            if b.get("status") in INTEGRITY_STATUSES:
                per[_parse_key(b["key"])] = f"integrity:{b['status']}"  # prime
        if per:
            bad[reciter] = per
    return bad


def _warn_if_capped(report: dict) -> None:
    """Le rapport peut tronquer les listes (cap). Prévenir si on risque d'en manquer."""
    for reciter, e in report.get("reciters", {}).items():
        integ = e.get("integrity", {})
        n_listed = len(integ.get("bad", []))
        n_real = integ.get("checked", 0) - integ.get("ok", 0)
        if n_real > n_listed:
            print(f"  [ATTENTION] {reciter}: {n_real} fichiers KO mais seulement "
                  f"{n_listed} listés (rapport tronqué par --cap). Relance "
                  f"audio_verify avec --cap élevé pour une correction exhaustive.")


# ----------------------- 1. réécriture de l'audio_map ----------------------

def rewrite_map(map_path: Path, bad: Dict[str, Dict[Key, str]],
                apply: bool, total_ayahs: int = 6236) -> Tuple[int, dict]:
    doc = json.loads(map_path.read_text(encoding="utf-8"))
    amap = doc.get("map", {})
    removed_total = 0
    for reciter, verses in amap.items():
        bad_keys = bad.get(reciter, {})
        if not bad_keys:
            continue
        before = len(verses)
        for (s, a) in bad_keys:
            verses.pop(f"{s}:{a}", None)
        removed = before - len(verses)
        removed_total += removed
        doc.setdefault("count", {})[reciter] = len(verses)
        doc.setdefault("missing_count", {})[reciter] = total_ayahs - len(verses)
    if apply and removed_total:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = map_path.with_suffix(map_path.suffix + f".bak.{ts}")
        shutil.copy2(map_path, backup)
        doc["corrected_at"] = ts
        map_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        print(f"  audio_map réécrite ({removed_total} entrées retirées). "
              f"Sauvegarde : {backup.name}")
    return removed_total, doc


# ----------------------- 2. signalement dans la base -----------------------

def flag_db(bad: Dict[str, Dict[Key, str]], apply: bool, table: str = "ayah_audio"
            ) -> int:
    flat: List[Tuple[str, int, int, str]] = [
        (reciter, s, a, reason)
        for reciter, per in bad.items()
        for (s, a), reason in per.items()
    ]
    if not apply:
        return len(flat)
    url, key = supabase_credentials()
    from supabase import create_client
    client = create_client(url, key)
    done = 0
    for reciter, s, a, reason in flat:
        client.table(table).update(
            {"verified": False, "flag_reason": reason}
        ).eq("surah", s).eq("ayah", a).eq("reciter", reciter).execute()
        done += 1
        if done % 100 == 0:
            print(f"    …{done}/{len(flat)} lignes signalées")
    return done


def reset_flags(apply: bool, table: str = "ayah_audio") -> int:
    if not apply:
        print("  (dry-run) remettrait verified=true partout. Ajoute --apply.")
        return 0
    url, key = supabase_credentials()
    from supabase import create_client
    client = create_client(url, key)
    res = client.table(table).update(
        {"verified": True, "flag_reason": None}
    ).eq("verified", False).execute()
    n = len(res.data or [])
    print(f"  {n} lignes ré-autorisées (verified=true).")
    return n


# --------------------------------- CLI -------------------------------------

def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Corrige map + base à partir du rapport audio_verify (réversible).")
    p.add_argument("--report", type=Path,
                   default=Path("Data/processed/audio_verify_report.json"))
    p.add_argument("--audio-map", type=Path,
                   default=Path("Data/processed/audio_map.json"))
    p.add_argument("--include-plausibility", action="store_true",
                   help="Signaler aussi les aberrants de durée GROSSIERS (file de revue).")
    p.add_argument("--flag-ratio-high", type=float, default=5.0,
                   help="Seuil haut ratio durée/attendu pour signaler (déf. 5.0×).")
    p.add_argument("--flag-ratio-low", type=float, default=0.2,
                   help="Seuil bas ratio durée/attendu pour signaler (déf. 0.2×).")
    p.add_argument("--no-map", action="store_true", help="Ne pas toucher l'audio_map.")
    p.add_argument("--no-db", action="store_true", help="Ne pas toucher la base.")
    p.add_argument("--reset-flags", action="store_true",
                   help="Remettre verified=true partout, puis quitter.")
    p.add_argument("--apply", action="store_true",
                   help="Écrire réellement (sinon dry-run).")
    args = p.parse_args(argv)

    mode = "APPLIQUÉ" if args.apply else "DRY-RUN (rien écrit)"
    print(f"=== Correction audio — {mode} ===")

    if args.reset_flags:
        reset_flags(args.apply)
        return 0

    if not args.report.exists():
        raise SystemExit(f"Rapport introuvable : {args.report} "
                         f"(lance d'abord `python -m tajweed.audio_verify --deep …`).")
    report = json.loads(args.report.read_text(encoding="utf-8"))
    _warn_if_capped(report)

    bad = collect_bad(report, args.include_plausibility,
                      args.flag_ratio_high, args.flag_ratio_low)
    n_reciters = len(bad)
    n_keys = sum(len(v) for v in bad.values())
    print(f"Anomalies retenues : {n_keys} entrées sur {n_reciters} récitateurs "
          f"(plausibilité {'INCLUSE' if args.include_plausibility else 'exclue'}).")
    for reciter, per in sorted(bad.items()):
        sample = ", ".join(f"{s}:{a}({r})" for (s, a), r in list(per.items())[:5])
        more = "" if len(per) <= 5 else f" …(+{len(per) - 5})"
        print(f"  • {reciter:28} {len(per):4}  {sample}{more}")
    if not bad:
        print("Rien à corriger. ✅")
        return 0

    if not args.no_map:
        print("\n[1] audio_map.json")
        removed, _ = rewrite_map(args.audio_map, bad, args.apply)
        if not args.apply:
            print(f"  (dry-run) retirerait {removed} entrées de {args.audio_map}.")

    if not args.no_db:
        print("\n[2] ayah_audio (verified=false)")
        n = flag_db(bad, args.apply)
        if not args.apply:
            print(f"  (dry-run) signalerait {n} lignes. Ajoute --apply pour exécuter.")

    if not args.apply:
        print("\nDRY-RUN terminé. Relance avec --apply pour appliquer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
