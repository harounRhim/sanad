# -*- coding: utf-8 -*-
"""
src/tajweed/correction/calibrate.py — Calibration des normes par le corpus.

Aligne un échantillon de récitateurs de RÉFÉRENCE (supposés corrects) et apprend,
par règle Tajweed, la distribution empirique des ḥarakāt mesurées (et de la
nasalité pour la ghunnah). Ces normes — médiane ± k·MAD — remplacent ensuite les
valeurs « manuel » dans rules.py, ce qui ABSORBE le biais systématique de la
mesure inter-onset : la référence définit ce que « correct » produit SOUS notre
mesure, donc l'écart d'un utilisateur reste significatif.

Coût : un alignement CTC (CPU) par (récitateur, ayah). On échantillonne donc
(quelques récitateurs × sourates courtes), ce qui suffit car chaque ayah fournit
plusieurs segments.

Exemple :
    python -m tajweed.correction.calibrate \
        --reciters alafasy husary abdul_basit_murattal \
        --surah-min 105 --surah-max 114 \
        --out Data/processed/tajweed_calibration.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .rules import (MADD_HARAKAT, GHUNNAH_RULES, effective_rule,
                    MADD_LOWER_ONLY, madd_calib_floor)
from .ground_truth import LocalGroundTruth
from .evaluate import load_waveform

try:  # package ou script isolé
    from ..extractor import iter_segments
except ImportError:  # pragma: no cover
    from tajweed.extractor import iter_segments  # type: ignore

Key = Tuple[int, int]


def select_focus_ayahs(json_path: Path, verses: Dict[Key, str],
                       focus_rules: List[str], per_rule: Optional[int] = None
                       ) -> List[Key]:
    """Ayahs ciblées, triées par longueur croissante (alignement CPU rapide).

    Pour garantir la couverture de CHAQUE règle rare (et que la plus fréquente ne
    monopolise pas l'échantillon), on prend les `per_rule` ayahs les plus COURTES
    par règle, puis l'union. `per_rule=None` → toutes les ayahs contenant la règle.
    """
    keys: set = set()
    for rule in focus_rules:
        rule_keys = {(s["surah"], s["ayah"])
                     for s in iter_segments(json_path, verses, rule)}
        shortest = sorted(rule_keys, key=lambda k: len(verses.get(k, "")))
        keys.update(shortest[:per_rule] if per_rule else shortest)
    return sorted(keys, key=lambda k: len(verses.get(k, "")))


def _percentile(sorted_vals: List[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    i = max(0, min(len(sorted_vals) - 1, int(round(q * (len(sorted_vals) - 1)))))
    return sorted_vals[i]


def summarize_samples(samples: Dict[str, Dict[str, List[float]]],
                      k_mad: float = 3.0, min_n: int = 5) -> dict:
    """Agrège {règle:{harakat:[…], nasality:[…]}} en normes robustes par règle."""
    rules: Dict[str, dict] = {}
    for rule, data in sorted(samples.items()):
        vals = sorted(data.get("harakat", []))
        lower_only = rule in MADD_LOWER_ONLY
        if lower_only:
            # écarter les effondrements d'alignement (mesures quasi nulles) qui,
            # sur un corpus de RÉFÉRENCE (supposé correct), ne sont pas de vraies
            # récitations courtes et fausseraient le plancher. Seuil par règle :
            # madd lāzim ≥3 ḥ, madd ʿāriḍ (246) dès ~0.8 ḥ (valide court).
            vals = [v for v in vals if v >= madd_calib_floor(rule)]
        if len(vals) < min_n:
            continue
        med = statistics.median(vals)
        mad = statistics.median([abs(v - med) for v in vals]) or 1e-9
        entry = {
            "n": len(vals),
            "median": round(med, 2),
            "mad": round(mad, 3),
            "lo": round(max(0.0, med - k_mad * mad), 2),
            "hi": round(med + k_mad * mad, 2),
            "p10": round(_percentile(vals, 0.10), 2),
            "p90": round(_percentile(vals, 0.90), 2),
        }
        if lower_only:
            # gate à sens unique : plancher robuste = 5e centile (sous-allongement),
            # borne haute purement indicative (jamais signalée « trop long »).
            entry["one_sided"] = True
            entry["lo"] = round(_percentile(vals, 0.05), 2)
            entry["hi"] = round(_percentile(vals, 0.95), 2)
        nas = sorted(v for v in data.get("nasality", []) if v is not None)
        if rule in GHUNNAH_RULES and len(nas) >= min_n:
            nmed = statistics.median(nas)
            entry["nasality"] = {
                "n": len(nas), "median": round(nmed, 3),
                "lo": round(_percentile(nas, 0.10), 3),  # seuil = 10e centile
            }
        rules[rule] = entry
    return rules


def load_checkpoint(path: Path) -> Tuple[Dict[str, Dict[str, List[float]]], set]:
    """Relit un checkpoint JSONL → (samples agrégés, ensemble (récitateur,s,a) faits)."""
    samples: Dict[str, Dict[str, List[float]]] = {}
    done: set = set()
    if not path.exists():
        return samples, done
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        done.add((rec["reciter"], rec["surah"], rec["ayah"]))
        for r in rec.get("results", []):
            # Split rétroactif : un madd_6 muqattaʿāt enregistré « madd_6 » par
            # d'anciennes passes est reclassé d'après la sourate/ayah de la ligne.
            rule = effective_rule(r["rule"], rec["surah"], rec["ayah"])
            b = samples.setdefault(rule, {"harakat": [], "nasality": []})
            b["harakat"].append(r["harakat"])
            if r.get("nasality") is not None:
                b["nasality"].append(r["nasality"])
    return samples, done


def collect(aligner, gt: LocalGroundTruth, audio_root: Path, reciters: List[str],
            ayah_keys: List[Key], with_nasality: bool = True, verbose: bool = True,
            checkpoint: Optional[Path] = None
            ) -> Tuple[Dict[str, Dict[str, List[float]]], int]:
    """Aligne et mesure chaque (récitateur, ayah). RÉSISTANT AUX INTERRUPTIONS :
    si `checkpoint` est fourni, chaque ayah traitée est persistée immédiatement
    (JSONL), on saute celles déjà faites au redémarrage, et un kill ne perd rien."""
    from .rules import measure_all
    samples, done_keys = load_checkpoint(checkpoint) if checkpoint else ({}, set())
    if checkpoint and done_keys and verbose:
        print(f"  reprise : {len(done_keys)} (récitateur,ayah) déjà faits")
    fh = open(checkpoint, "a", encoding="utf-8") if checkpoint else None
    seen = 0
    total = len(reciters) * len(ayah_keys)
    try:
        for reciter in reciters:
            for (surah, ayah) in ayah_keys:
                seen += 1
                if (reciter, surah, ayah) in done_keys:
                    continue
                path = audio_root / reciter / f"{surah:03d}{ayah:03d}.mp3"
                if not path.exists():
                    continue
                try:
                    g = gt.get(surah, ayah)
                    al = aligner.align(path, g.text)
                    wav, sr = load_waveform(path) if with_nasality else (None, None)
                    results, _unit = measure_all(al, g.segments, wav, sr,
                                                 surah=surah, ayah=ayah)
                except Exception as e:  # noqa: BLE001 — un fichier KO ne stoppe pas tout
                    if verbose:
                        print(f"  [skip] {reciter} {surah}:{ayah} — {e!r}")
                    continue
                line_results = []
                for r in results:
                    if r.measured_harakat is None or r.status == "missing_audio":
                        continue
                    b = samples.setdefault(r.rule, {"harakat": [], "nasality": []})
                    b["harakat"].append(r.measured_harakat)
                    if r.nasality is not None:
                        b["nasality"].append(r.nasality)
                    line_results.append({"rule": r.rule, "harakat": r.measured_harakat,
                                         "nasality": r.nasality})
                done_keys.add((reciter, surah, ayah))
                if fh:
                    fh.write(json.dumps({"reciter": reciter, "surah": surah,
                                         "ayah": ayah, "results": line_results}) + "\n")
                    fh.flush()
                if verbose and seen % 10 == 0:
                    print(f"  …{seen}/{total}  ({reciter} {surah}:{ayah})")
    finally:
        if fh:
            fh.close()
    return samples, len(done_keys)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Apprend les normes Tajweed sur le corpus de référence.")
    p.add_argument("--audio-root", type=Path, default=Path("Data/audio/ayahs"))
    p.add_argument("--text", type=Path, default=Path("Data/raw/quran-uthmani.txt"))
    p.add_argument("--json", type=Path,
                   default=Path("Data/raw/tajweed.hafs.uthmani-pause-sajdah.json"))
    p.add_argument("--reciters", nargs="+", required=True)
    p.add_argument("--surah-min", type=int, default=105)
    p.add_argument("--surah-max", type=int, default=114)
    p.add_argument("--focus-rules", nargs="+", default=None,
                   help="Cibler les ayahs contenant ces règles (rares), au lieu "
                        "de la plage de sourates. Ex : madd_muttasil ikhfa_shafawi.")
    p.add_argument("--per-rule", type=int, default=80,
                   help="Avec --focus-rules : nb d'ayahs (les plus courtes) par règle.")
    p.add_argument("--max-ayahs", type=int, default=None,
                   help="Plafond d'ayahs (échantillon) — défaut : toutes.")
    p.add_argument("--model", default="jonatasgrosman/wav2vec2-large-xlsr-53-arabic")
    p.add_argument("--k-mad", type=float, default=3.0)
    p.add_argument("--no-nasality", action="store_true")
    p.add_argument("--checkpoint", type=Path,
                   default=Path("Data/processed/calib_checkpoint.jsonl"),
                   help="JSONL résistant aux interruptions (reprise auto). '' pour désactiver.")
    p.add_argument("--summarize-only", action="store_true",
                   help="Ne pas aligner : résumer le checkpoint existant en calibration.")
    p.add_argument("--out", type=Path, default=Path("Data/processed/tajweed_calibration.json"))
    args = p.parse_args(argv)

    checkpoint = args.checkpoint if str(args.checkpoint) else None

    gt = LocalGroundTruth(args.text, args.json)
    if args.focus_rules:
        keys = select_focus_ayahs(args.json, gt._verses, args.focus_rules,
                                  per_rule=args.per_rule)
        scope = f"ciblage {','.join(args.focus_rules)} (≤{args.per_rule}/règle)"
    else:
        keys = sorted(k for k in gt._verses if args.surah_min <= k[0] <= args.surah_max)
        scope = f"sourates {args.surah_min}–{args.surah_max}"
    if args.max_ayahs:
        keys = keys[:args.max_ayahs]

    if args.summarize_only:
        samples, done = load_checkpoint(checkpoint) if checkpoint else ({}, set())
        print(f"Résumé depuis checkpoint : {len(done)} (récitateur,ayah).")
    else:
        print(f"Calibration : {len(args.reciters)} récitateurs × {len(keys)} ayahs "
              f"({scope})  modèle={args.model}  checkpoint={checkpoint}")
        from .aligner import Wav2Vec2Aligner
        aligner = Wav2Vec2Aligner(model_id=args.model)
        samples, done = collect(aligner, gt, args.audio_root, args.reciters, keys,
                                with_nasality=not args.no_nasality, checkpoint=checkpoint)
    rules = summarize_samples(samples, k_mad=args.k_mad)

    doc = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0)
        .isoformat().replace("+00:00", "Z"),
        "model": args.model,
        "reciters": args.reciters,
        "surah_range": [args.surah_min, args.surah_max],
        "n_ayahs": len(keys),
        "k_mad": args.k_mad,
        "rules": rules,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ Calibration écrite : {args.out}")
    for rule, c in rules.items():
        extra = (f"  nasalité≥{c['nasality']['lo']}" if "nasality" in c else "")
        print(f"  {rule:16} n={c['n']:4}  médiane {c['median']:.1f}  "
              f"bande [{c['lo']:.1f}, {c['hi']:.1f}] ḥ{extra}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
