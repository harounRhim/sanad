# -*- coding: utf-8 -*-
"""
src/tajweed/correction/batch.py — Notation d'un DOSSIER d'enregistrements.

Évalue toutes les récitations d'un dossier en une passe (le modèle wav2vec2 est
chargé UNE fois puis réutilisé) et agrège les résultats en un rapport combiné :
taux de réussite global, détail par règle Tajweed, et liste des segments à revoir
regroupés par ayah. Les règles « indicatives » (muqattaʿāt) sont comptées à part,
jamais en échec ; les segments sans alignement audio fiable sont exclus du score.

Le (sourate, ayah) de chaque fichier est déduit de son nom :
    001007.mp3      → 1:7      (convention du corpus : SSSAAA)
    2_255.wav       → 2:255    (séparateur _ - ou .)
    recite-112-1.m4a → 112:1   (dernier couple de nombres trouvé)

Exemples :
    # noter un dossier avec les normes calibrées (aligneur réel, source locale)
    python -m tajweed.correction.batch --dir mes_recitations \
        --calibration Data/processed/tajweed_calibration.json --out rapport.json

    # démo sans modèle ML (aligneur synthétique)
    python -m tajweed.correction.batch --dir demo --aligner synthetic
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .types import Report
from .rules import ADVISORY_RULES
from .evaluate import evaluate, _make_aligner, _make_source, print_report

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".opus", ".aac"}

# Un couple de nombres (1-3 chiffres) séparés, OU un bloc SSSAAA de 6 chiffres.
_PAIR_RE = re.compile(r"(\d{1,3})[._\- ](\d{1,3})")
_SIX_RE = re.compile(r"(?<!\d)(\d{3})(\d{3})(?!\d)")


def parse_ayah_from_name(path: Path) -> Optional[Tuple[int, int]]:
    """(sourate, ayah) déduits du nom de fichier, ou None si indéterminable.

    On privilégie un bloc SSSAAA de 6 chiffres (convention du corpus) ; à défaut
    on prend le DERNIER couple « nombre<sep>nombre » du nom. Les valeurs hors
    plage (sourate 1-114, ayah ≥ 1) sont rejetées."""
    stem = path.stem
    six = list(_SIX_RE.finditer(stem))
    if six:
        s, a = int(six[-1].group(1)), int(six[-1].group(2))
        if 1 <= s <= 114 and a >= 1:
            return s, a
    pair = list(_PAIR_RE.finditer(stem))
    if pair:
        s, a = int(pair[-1].group(1)), int(pair[-1].group(2))
        if 1 <= s <= 114 and a >= 1:
            return s, a
    return None


def discover_audio(audio_dir: Path) -> List[Path]:
    """Fichiers audio du dossier (récursif), triés, extensions connues."""
    return sorted(p for p in Path(audio_dir).rglob("*")
                  if p.is_file() and p.suffix.lower() in AUDIO_EXTS)


# ------------------------------ agrégation ---------------------------------

@dataclass
class BatchReport:
    audio_dir: str
    n_recordings: int
    n_ok: int
    n_warn: int
    by_rule: Dict[str, Dict[str, int]]        # rule -> {ok, warn}
    advisory: Dict[str, int]                   # règles indicatives -> nb segments
    flags: List[dict]                          # segments à revoir (warn)
    skipped: List[dict]                        # fichiers non notés + raison
    reports: List[Report] = field(default_factory=list)

    @property
    def n_graded(self) -> int:
        return self.n_ok + self.n_warn

    @property
    def pass_rate(self) -> Optional[float]:
        return (self.n_ok / self.n_graded) if self.n_graded else None

    def to_dict(self) -> dict:
        return {
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0)
            .isoformat().replace("+00:00", "Z"),
            "audio_dir": self.audio_dir,
            "n_recordings": self.n_recordings,
            "n_graded_segments": self.n_graded,
            "n_ok": self.n_ok,
            "n_warn": self.n_warn,
            "pass_rate": round(self.pass_rate, 4) if self.pass_rate is not None else None,
            "by_rule": {
                r: {**c, "pass_rate": round(c["ok"] / (c["ok"] + c["warn"]), 3)
                    if (c["ok"] + c["warn"]) else None}
                for r, c in sorted(self.by_rule.items())
            },
            "advisory": self.advisory,
            "skipped": self.skipped,
            "flags": self.flags,
            "recordings": [r.to_dict() for r in self.reports],
        }


def aggregate_reports(reports: List[Report], skipped: List[Tuple[Path, str]],
                      audio_dir: Path) -> BatchReport:
    """Combine des Report par-ayah en un BatchReport. Logique PURE (testable
    sans modèle) : échec/réussite par règle, indicatifs à part, missing_audio
    exclu du score."""
    by_rule: Dict[str, Dict[str, int]] = {}
    advisory: Dict[str, int] = {}
    flags: List[dict] = []
    n_ok = n_warn = 0
    for rep in reports:
        for r in rep.results:
            if r.rule in ADVISORY_RULES:
                advisory[r.rule] = advisory.get(r.rule, 0) + 1
                continue
            if r.status == "missing_audio":
                continue                       # alignement non fiable → hors score
            slot = by_rule.setdefault(r.rule, {"ok": 0, "warn": 0})
            if r.status == "warn":
                slot["warn"] += 1
                n_warn += 1
                flags.append({
                    "surah": rep.surah, "ayah": rep.ayah, "rule": r.rule,
                    "segment": r.segment, "measured": r.measured,
                    "message": r.message,
                })
            else:                              # "ok"
                slot["ok"] += 1
                n_ok += 1
    flags.sort(key=lambda f: (f["surah"], f["ayah"], f["rule"]))
    return BatchReport(
        audio_dir=str(audio_dir), n_recordings=len(reports),
        n_ok=n_ok, n_warn=n_warn, by_rule=by_rule, advisory=advisory,
        flags=flags, skipped=[{"file": str(p), "reason": why} for p, why in skipped],
        reports=reports,
    )


def batch_evaluate(audio_dir: Path, aligner, gt_source, calibration: Optional[dict] = None,
                   with_nasality: bool = True, verbose: bool = True) -> BatchReport:
    """Découvre, évalue et agrège tous les enregistrements d'un dossier."""
    files = discover_audio(audio_dir)
    reports: List[Report] = []
    skipped: List[Tuple[Path, str]] = []
    if verbose:
        print(f"{len(files)} fichier(s) audio dans {audio_dir}")
    for f in files:
        key = parse_ayah_from_name(f)
        if key is None:
            skipped.append((f, "nom de fichier sans (sourate,ayah) déductible"))
            if verbose:
                print(f"  [skip] {f.name} — nom illisible")
            continue
        surah, ayah = key
        try:
            rep = evaluate(f, surah, ayah, aligner, gt_source,
                           with_nasality=with_nasality, calibration=calibration)
        except Exception as e:  # noqa: BLE001 — un fichier KO ne stoppe pas le lot
            skipped.append((f, repr(e)))
            if verbose:
                print(f"  [skip] {f.name} ({surah}:{ayah}) — {e!r}")
            continue
        reports.append(rep)
        if verbose:
            print(f"  {f.name} → {surah}:{ayah}  ({rep.n_ok} ok, {rep.n_warn} à revoir)")
    return aggregate_reports(reports, skipped, audio_dir)


def print_batch(rep: BatchReport, show_flags: int = 40) -> None:
    print(f"\n=== Rapport combiné — {rep.audio_dir} ===")
    print(f"Enregistrements notés : {rep.n_recordings}"
          + (f"  |  non notés : {len(rep.skipped)}" if rep.skipped else ""))
    if rep.pass_rate is not None:
        print(f"Segments gradés : {rep.n_graded}  →  "
              f"{rep.n_ok} ok, {rep.n_warn} à revoir  "
              f"({rep.pass_rate*100:.0f}% conformes)")
    else:
        print("Aucun segment gradable.")
    if rep.by_rule:
        print("\nPar règle :")
        for r, c in sorted(rep.by_rule.items()):
            tot = c["ok"] + c["warn"]
            pr = (c["ok"] / tot * 100) if tot else 0.0
            print(f"  {r:16} {c['ok']:3} ok / {c['warn']:3} à revoir  ({pr:3.0f}%)")
    if rep.advisory:
        adv = ", ".join(f"{r}×{n}" for r, n in sorted(rep.advisory.items()))
        print(f"\nIndicatif (non noté) : {adv}")
    if rep.flags:
        print(f"\nÀ revoir ({len(rep.flags)}) :")
        for f in rep.flags[:show_flags]:
            print(f"  ⚠ {f['surah']}:{f['ayah']:<3} {f['rule']:14} «{f['segment']}»  — {f['message']}")
        if len(rep.flags) > show_flags:
            print(f"  … et {len(rep.flags) - show_flags} autre(s).")
    if rep.skipped:
        print(f"\nNon notés ({len(rep.skipped)}) :")
        for s in rep.skipped[:10]:
            print(f"  ∅ {Path(s['file']).name} — {s['reason']}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Note un dossier d'enregistrements Tajweed en un rapport combiné.")
    p.add_argument("--dir", type=Path, required=True, help="Dossier des enregistrements.")
    p.add_argument("--aligner", choices=["synthetic", "wav2vec2"], default="wav2vec2")
    p.add_argument("--model", default="jonatasgrosman/wav2vec2-large-xlsr-53-arabic")
    p.add_argument("--source", choices=["local", "supabase"], default="local")
    p.add_argument("--text", type=Path, default=Path("Data/raw/quran-uthmani.txt"))
    p.add_argument("--json", type=Path,
                   default=Path("Data/raw/tajweed.hafs.uthmani-pause-sajdah.json"))
    p.add_argument("--no-nasality", action="store_true")
    p.add_argument("--calibration", type=Path, default=None,
                   help="JSON de normes apprises (recommandé).")
    p.add_argument("--out", type=Path, default=None, help="Écrire le rapport combiné JSON.")
    args = p.parse_args(argv)

    if not args.dir.is_dir():
        raise SystemExit(f"Dossier introuvable : {args.dir}")
    calibration = None
    if args.calibration:
        calibration = json.loads(Path(args.calibration).read_text(encoding="utf-8"))
    aligner = _make_aligner(args.aligner, args.model)      # modèle chargé une fois
    source = _make_source(args.source, args.text, args.json)
    rep = batch_evaluate(args.dir, aligner, source, calibration=calibration,
                         with_nasality=not args.no_nasality)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(rep.to_dict(), ensure_ascii=False, indent=2),
                            encoding="utf-8")
        print(f"✅ Rapport combiné écrit : {args.out}")
    print_batch(rep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
