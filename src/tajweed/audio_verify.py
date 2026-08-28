#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
src/tajweed/audio_verify.py — Pipeline de vérification & correction audio.

Vérifie les ~193 000 fichiers (30+ récitateurs × 6236 ayahs, ~36 Go) SANS les
charger en RAM : on ne lit que des chemins (os.walk + os.stat) et, pour la
couche intégrité, uniquement les EN-TÊTES MP3 via mutagen (pas de décodage du
flux, pas de ffmpeg).

Trois couches indépendantes, du moins cher au plus fin :

  1. inventory   — couverture vs le corpus canonique (6236 ayahs) par récitateur
                   + orphelins (clés hors corpus), doublons, dossiers inconnus.
                   Coût : stat seulement → secondes.
  2. integrity   — taille >= plancher, en-tête MP3 lisible, durée/bitrate > 0.
                   Coût : un open() d'en-tête par fichier → minutes.
  3. plausibility— durée vs longueur de l'ayah : ajustement robuste par
                   récitateur (médiane des sec/lettre + MAD), signale les durées
                   aberrantes (récitations échangées / tronquées / mal nommées).
                   Coût : réutilise les durées de la couche 2 → négligeable.

Sortie : un rapport JSON exploitable (Data/processed/audio_verify_report.json)
+ un résumé console. La CORRECTION consomme ce rapport (worklist de
re-téléchargement, régénération de l'audio_map filtrée, purge des lignes
ayah_audio invalides) — voir --emit-worklist ici, le reste dans ingest.

Exemples :
    # inventaire rapide (tous les récitateurs)
    python -m tajweed.audio_verify --audio-root Data/audio/ayahs \
        --text Data/raw/quran-uthmani.txt

    # vérif complète d'un seul récitateur (intégrité + plausibilité)
    python -m tajweed.audio_verify --reciter alafasy --deep

    # échantillon de 200 fichiers/récitateur, 8 threads, worklist de réparation
    python -m tajweed.audio_verify --deep --sample 200 --workers 8 --emit-worklist
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

# Import du corpus : fonctionne en package (-m tajweed.audio_verify) ou à plat.
try:  # pragma: no cover - dépend du mode d'exécution
    from .quran_text import load_verses
    from .metadata import normalize_arabic
except ImportError:  # exécuté comme script isolé
    from quran_text import load_verses  # type: ignore
    from metadata import normalize_arabic  # type: ignore

AUDIO_EXTS = {".mp3", ".ogg", ".m4a", ".wav", ".opus", ".flac"}
Key = Tuple[int, int]

# Lettres muqattaʿāt (« lettres isolées » en tête de 29 sourates). Récitées avec
# un madd marqué : 3 lettres peuvent durer ~10 s. Le modèle durée≈f(lettres) les
# sous-estime massivement → faux positifs systématiques. On les EXCLUT de la
# plausibilité. Détection indépendante du dataset : ayah dont les lettres
# normalisées (sans espace) sont toutes dans ce jeu et de longueur ≤ 6.
MUQATTAAT_LETTERS = set("الٓمٓصٓرٰكهيعٓطسٓحٓقٓنٓ") | set("المصركهيعطسحقن")

# Ce dataset PRÉFIXE la basmala à l'ayah 1 de chaque sourate (sauf 1 et 9),
# alors que l'audio de l'ayah 1 ne la contient en général PAS → le modèle
# durée≈f(lettres) sur-estime les ouvertures de sourate. On retire ce préfixe du
# compte de lettres de l'ayah 1 pour aligner texte et audio.
BASMALA_NORM = normalize_arabic("بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ").replace(" ", "")


def _is_muqattaat(normalized_no_space: str) -> bool:
    s = normalized_no_space
    return 0 < len(s) <= 6 and set(s) <= MUQATTAAT_LETTERS


# --------------------------- corpus canonique ------------------------------

def load_corpus(text_path: Path) -> Tuple[Dict[Key, int], Set[Key]]:
    """((sourate,ayah)→nb_lettres, {clés muqattaʿāt}) depuis quran-uthmani.txt.

    Le nb de lettres = longueur du texte NORMALISÉ (sans harakat ni espaces) :
    proxy stable de la « quantité de récitation » pour la couche plausibilité.
    """
    verses = load_verses(text_path)
    out: Dict[Key, int] = {}
    muqattaat: Set[Key] = set()
    for key, text in verses.items():
        letters = normalize_arabic(text).replace(" ", "")
        # Ayah 1 (hors Fatiha) : retirer la basmala absente de l'audio.
        if key[1] == 1 and key[0] != 1 and letters.startswith(BASMALA_NORM):
            letters = letters[len(BASMALA_NORM):]
        out[key] = len(letters)
        if _is_muqattaat(letters):
            muqattaat.add(key)
    return out, muqattaat


# ----------------------------- scan disque ---------------------------------

def parse_key(name: str) -> Optional[Key]:
    """Extrait (sourate, ayah) d'un nom de fichier concat_3_3 : 001001.mp3."""
    stem = Path(name).stem
    digits = "".join(ch for ch in stem if ch.isdigit())
    if len(digits) != 6:
        return None
    s, a = int(digits[:3]), int(digits[3:])
    return (s, a) if 1 <= s <= 114 and a >= 1 else None


def scan_reciter(reciter_dir: Path) -> Tuple[Dict[Key, Path], List[Path], List[Tuple[Key, Path]]]:
    """Parcourt un dossier récitateur.

    Renvoie (mapped, unparsed, duplicates) :
      - mapped     : { (s,a) : chemin }  (premier fichier gagné)
      - unparsed   : fichiers audio dont le nom ne donne pas de clé
      - duplicates : (clé, chemin) supplémentaires pointant une clé déjà vue
    """
    mapped: Dict[Key, Path] = {}
    unparsed: List[Path] = []
    duplicates: List[Tuple[Key, Path]] = []
    for dirpath, dirnames, filenames in os.walk(reciter_dir):
        dirnames.sort()
        for fn in sorted(filenames):
            if Path(fn).suffix.lower() not in AUDIO_EXTS:
                continue
            full = Path(dirpath) / fn
            key = parse_key(fn)
            if key is None:
                unparsed.append(full)
            elif key in mapped:
                duplicates.append((key, full))
            else:
                mapped[key] = full
    return mapped, unparsed, duplicates


def list_reciter_dirs(audio_root: Path) -> List[str]:
    return sorted(
        p.name for p in audio_root.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )


# ------------------------ couche 1 : inventaire ----------------------------

def inventory_reciter(reciter: str, mapped: Dict[Key, Path], unparsed: List[Path],
                      duplicates: List[Tuple[Key, Path]],
                      canonical: Set[Key], cap: int = 50) -> dict:
    present = set(mapped)
    missing = sorted(canonical - present)
    extra = sorted(present - canonical)  # numéros hors corpus (mauvais nommage)
    return {
        "present": len(present),
        "missing_count": len(missing),
        "extra_count": len(extra),
        "duplicate_count": len(duplicates),
        "unparsed_count": len(unparsed),
        "missing": [f"{s}:{a}" for s, a in missing[:cap]],
        "extra": [f"{s}:{a}" for s, a in extra[:cap]],
        "duplicates": [f"{s}:{a} <- {p.name}" for (s, a), p in duplicates[:cap]],
        "unparsed": [p.name for p in unparsed[:cap]],
    }


# ------------------------ couche 2 : intégrité -----------------------------

def probe_file(path: Path, min_bytes: int) -> dict:
    """En-tête MP3 seulement : statut + durée + bitrate. Ne décode pas le flux."""
    try:
        size = path.stat().st_size
    except OSError as e:
        return {"status": "missing", "error": repr(e), "size": 0, "duration": None}
    if size == 0:
        return {"status": "empty", "size": 0, "duration": None}
    if size < min_bytes:
        return {"status": "tiny", "size": size, "duration": None}
    try:
        from mutagen import File as MutagenFile
        mf = MutagenFile(str(path))
        if mf is None or mf.info is None:
            return {"status": "unreadable", "size": size, "duration": None}
        dur = float(getattr(mf.info, "length", 0.0) or 0.0)
        bitrate = int(getattr(mf.info, "bitrate", 0) or 0)
    except Exception as e:  # noqa: BLE001 — tout échec de parsing = corrompu
        return {"status": "corrupt", "size": size, "duration": None, "error": repr(e)}
    if dur <= 0.0:
        return {"status": "zero_duration", "size": size, "duration": dur}
    return {"status": "ok", "size": size, "duration": dur, "bitrate": bitrate}


def integrity_reciter(items: List[Tuple[Key, Path]], min_bytes: int,
                      workers: int, cap: int = 50) -> Tuple[dict, Dict[Key, float]]:
    """Sonde chaque (clé, chemin). Renvoie (résumé, {clé: durée_ok})."""
    counts: Dict[str, int] = {}
    bad: List[dict] = []
    durations: Dict[Key, float] = {}

    def work(item: Tuple[Key, Path]) -> Tuple[Key, dict]:
        key, path = item
        return key, probe_file(path, min_bytes)

    runner: Iterable[Tuple[Key, dict]]
    if workers > 1:
        ex = ThreadPoolExecutor(max_workers=workers)
        runner = ex.map(work, items)
    else:
        ex = None
        runner = (work(it) for it in items)

    try:
        for key, res in runner:
            st = res["status"]
            counts[st] = counts.get(st, 0) + 1
            if st == "ok":
                durations[key] = res["duration"]
            elif len(bad) < cap:
                bad.append({"key": f"{key[0]}:{key[1]}", **res})
    finally:
        if ex is not None:
            ex.shutdown(wait=True)

    summary = {
        "checked": sum(counts.values()),
        "ok": counts.get("ok", 0),
        "by_status": counts,
        "bad": bad,
    }
    return summary, durations


# ----------------------- couche 3 : plausibilité ---------------------------

def theil_sen(xs: List[float], ys: List[float], rng: random.Random,
              max_pairs: int = 20000) -> Optional[Tuple[float, float]]:
    """Régression robuste durée = a + b·lettres par l'estimateur de Theil–Sen.

    b = médiane des pentes par paires ; a = médiane des (y - b·x). Insensible
    aux aberrants (point de rupture ~29 %). Au-delà de max_pairs combinaisons,
    on échantillonne les paires (déterministe via rng) pour rester en O(max_pairs).
    """
    n = len(xs)
    if n < 8:
        return None
    if n * (n - 1) // 2 <= max_pairs:
        idx = [(i, j) for i in range(n) for j in range(i + 1, n)]
    else:
        seen: Set[Tuple[int, int]] = set()
        while len(seen) < max_pairs:
            i, j = rng.randrange(n), rng.randrange(n)
            if i != j:
                seen.add((min(i, j), max(i, j)))
        idx = list(seen)
    slopes = [(ys[j] - ys[i]) / (xs[j] - xs[i])
              for i, j in idx if xs[j] != xs[i]]
    if not slopes:
        return None
    b = statistics.median(slopes)
    a = statistics.median([y - b * x for x, y in zip(xs, ys)])
    return a, b


def plausibility_reciter(durations: Dict[Key, float], canonical: Dict[Key, int],
                         mad_k: float, min_abs: float, rng: random.Random,
                         ratio_low: float = 0.5, ratio_high: float = 2.0,
                         cap: int = 50, skip_keys: frozenset = frozenset()) -> dict:
    """Signale les durées GROSSIÈREMENT aberrantes via durée = a + b·lettres.

    Le terme constant `a` absorbe l'overhead fixe par ayah (pause d'ouverture/
    fermeture, allongement/madd final) : sans lui, les ayahs COURTES paraissent
    « trop longues » par lettre. On ajuste la droite de façon robuste (Theil–Sen).

    Sans ASR, la durée seule ne distingue pas une variation de style légitime
    (madd, waqf, mélodie : ±60 %) d'une vraie anomalie. On ne retient donc que
    le GROSSIER, via DEUX conditions conjointes :
      - résidu statistiquement fort  (|résidu| > mad_k × MAD), ET
      - ratio durée/attendu hors bande [ratio_low, ratio_high] (déf. 0,5–2,0×),
    ou bien une durée absolue sous min_abs (clip tronqué/quasi vide).
    Cible : troncatures (ratio « trop court ») et fichiers échangés/redoublés
    (ratio « trop long »). La liste devient une file de revue fiable, pas du bruit.
    """
    per_key: List[Tuple[Key, float, int]] = []  # (clé, durée, lettres)
    xs: List[float] = []
    ys: List[float] = []
    for key, dur in durations.items():
        letters = canonical.get(key, 0)
        if letters <= 0 or dur <= 0 or key in skip_keys:
            continue
        per_key.append((key, dur, letters))
        xs.append(float(letters))
        ys.append(dur)

    fit = theil_sen(xs, ys, rng)
    if fit is None:
        return {"checked": len(per_key), "skipped": True,
                "reason": "trop peu de fichiers OK pour ajuster", "outliers": []}
    a, b = fit
    resid = [dur - (a + b * letters) for _, dur, letters in per_key]
    med_r = statistics.median(resid)
    mad_r = statistics.median([abs(r - med_r) for r in resid]) or 1e-9

    outliers: List[dict] = []
    for (key, dur, letters), r in zip(per_key, resid):
        z = abs(r - med_r) / mad_r
        expected = a + b * letters
        ratio = dur / expected if expected > 0 else 0.0
        gross = ratio < ratio_low or ratio > ratio_high
        if dur < min_abs or (z > mad_k and gross):
            outliers.append({
                "key": f"{key[0]}:{key[1]}",
                "duration": round(dur, 2),
                "letters": letters,
                "expected": round(expected, 2),
                "ratio": round(ratio, 2),
                "resid_z": round(z, 1),
                "reason": "too_short_abs" if dur < min_abs else
                          ("too_short" if dur < expected else "too_long"),
            })
    outliers.sort(key=lambda d: abs(d["ratio"] - 1.0), reverse=True)
    return {
        "checked": len(per_key),
        "fit_intercept_s": round(a, 3),
        "fit_slope_s_per_letter": round(b, 4),
        "resid_mad_s": round(mad_r, 3),
        "ratio_band": [ratio_low, ratio_high],
        "outlier_count": len(outliers),
        "outliers": outliers[:cap],
    }


# ------------------------------ orchestration ------------------------------

def verify(audio_root: Path, canonical: Dict[Key, int], reciters: List[str],
           layers: Set[str], surah: Optional[int], sample: Optional[int],
           min_bytes: int, workers: int, mad_k: float, min_abs: float,
           ratio_low: float = 0.5, ratio_high: float = 2.0,
           cap: int = 50, muqattaat: Optional[Set[Key]] = None,
           seed: int = 1234) -> dict:
    skip = frozenset(muqattaat or ())
    canon_keys = set(canonical)
    if surah is not None:
        canon_keys = {(s, a) for (s, a) in canon_keys if s == surah}
    rng = random.Random(seed)

    report_reciters: Dict[str, dict] = {}
    for reciter in reciters:
        rdir = audio_root / reciter
        if not rdir.is_dir():
            report_reciters[reciter] = {"error": "dossier introuvable"}
            continue
        mapped, unparsed, duplicates = scan_reciter(rdir)
        if surah is not None:
            mapped = {k: v for k, v in mapped.items() if k[0] == surah}
        entry: dict = {}

        if "inventory" in layers:
            entry["inventory"] = inventory_reciter(
                reciter, mapped, unparsed, duplicates, canon_keys, cap)

        durations: Dict[Key, float] = {}
        if "integrity" in layers:
            items = [(k, mapped[k]) for k in sorted(mapped)]
            if sample is not None and len(items) > sample:
                items = rng.sample(items, sample)
            entry["integrity"], durations = integrity_reciter(
                items, min_bytes, workers, cap)

        if "plausibility" in layers and durations:
            entry["plausibility"] = plausibility_reciter(
                durations, canonical, mad_k, min_abs, rng,
                ratio_low, ratio_high, cap, skip)

        report_reciters[reciter] = entry

    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0)
        .isoformat().replace("+00:00", "Z"),
        "audio_root": str(audio_root).replace(os.sep, "/"),
        "params": {
            "layers": sorted(layers), "surah": surah, "sample": sample,
            "min_bytes": min_bytes, "workers": workers,
            "mad_k": mad_k, "min_abs_s": min_abs,
        },
        "canonical_ayahs": len(canon_keys),
        "reciters": report_reciters,
    }


def emit_worklist(report: dict) -> List[str]:
    """Clés à re-télécharger : manquantes + intègres-KO + plausibilité-aberrantes."""
    work: List[str] = []
    for reciter, entry in report["reciters"].items():
        inv = entry.get("inventory", {})
        for k in inv.get("missing", []):
            work.append(f"{reciter}\t{k}\tmissing")
        for b in entry.get("integrity", {}).get("bad", []):
            work.append(f"{reciter}\t{b['key']}\t{b['status']}")
        for o in entry.get("plausibility", {}).get("outliers", []):
            work.append(f"{reciter}\t{o['key']}\t{o['reason']}")
    return work


# ------------------------------- rapport -----------------------------------

def print_summary(report: dict, known_reciters: Optional[Set[str]] = None) -> None:
    print(f"\n=== Vérification audio ({report['generated_at']}) ===")
    print(f"Racine : {report['audio_root']}   |   ayahs canoniques : "
          f"{report['canonical_ayahs']}")
    print(f"Couches : {', '.join(report['params']['layers'])}\n")
    tot_missing = tot_bad = tot_outliers = 0
    for reciter, e in report["reciters"].items():
        if "error" in e:
            print(f"  • {reciter:30} [ERREUR] {e['error']}")
            continue
        inv = e.get("inventory", {})
        integ = e.get("integrity", {})
        plaus = e.get("plausibility", {})
        miss = inv.get("missing_count", 0)
        bad = integ.get("checked", 0) - integ.get("ok", 0) if integ else 0
        outl = plaus.get("outlier_count", 0)
        tot_missing += miss
        tot_bad += bad
        tot_outliers += outl
        present = inv.get("present", 0)
        if inv and present == 0:
            print(f"  • {reciter:30} dossier vide  ⚠")
            continue
        bits = [f"présents {present}"]
        if miss:
            bits.append(f"MANQUANTS {miss}")
        if inv.get("extra_count"):
            bits.append(f"hors-corpus {inv['extra_count']}")
        if inv.get("duplicate_count"):
            bits.append(f"doublons {inv['duplicate_count']}")
        if integ:
            bits.append(f"intègres {integ.get('ok', 0)}/{integ.get('checked', 0)}")
        if plaus and not plaus.get("skipped"):
            bits.append(f"aberrants {outl}")
        flag = "  ✅" if (miss == 0 and bad == 0 and outl == 0) else "  ⚠"
        print(f"  • {reciter:30} {', '.join(bits)}{flag}")

    if known_reciters is not None:
        stray = sorted(set(report["reciters"]) - known_reciters)
        unmapped = sorted(known_reciters - set(report["reciters"]))
        if stray:
            print(f"\n[INFO] récitateurs sur disque mais absents de l'audio_map : "
                  f"{', '.join(stray)}")
        if unmapped:
            print(f"[INFO] récitateurs de l'audio_map non scannés : "
                  f"{', '.join(unmapped)}")
    print(f"\nTotaux — manquants : {tot_missing}   intègres-KO : {tot_bad}   "
          f"aberrants : {tot_outliers}")


# --------------------------------- CLI -------------------------------------

def _load_known_reciters(audio_map_path: Path) -> Optional[Set[str]]:
    if not audio_map_path.exists():
        return None
    try:
        doc = json.loads(audio_map_path.read_text(encoding="utf-8"))
        return set(doc.get("reciters", []))
    except (OSError, json.JSONDecodeError):
        return None


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Vérifie et signale les anomalies du corpus audio (streaming).")
    p.add_argument("--audio-root", type=Path, default=Path("Data/audio/ayahs"))
    p.add_argument("--text", type=Path, default=Path("Data/raw/quran-uthmani.txt"),
                   help="quran-uthmani.txt : corpus canonique (clés + longueurs).")
    p.add_argument("--audio-map", type=Path,
                   default=Path("Data/processed/audio_map.json"),
                   help="Pour signaler les récitateurs disque vs map.")
    p.add_argument("--reciter", action="append", default=None,
                   help="Limiter à ce(s) récitateur(s) (répétable). Défaut : tous.")
    p.add_argument("--surah", type=int, default=None, help="Limiter à une sourate.")
    p.add_argument("--layers", default="inventory",
                   help="Couches : inventory,integrity,plausibility (séparées par ,).")
    p.add_argument("--deep", action="store_true",
                   help="Raccourci : active les trois couches.")
    p.add_argument("--sample", type=int, default=None,
                   help="Échantillon aléatoire de N fichiers/récitateur (intégrité).")
    p.add_argument("--workers", type=int, default=8, help="Threads pour l'intégrité.")
    p.add_argument("--min-bytes", type=int, default=1024,
                   help="Taille plancher : en dessous = tronqué/vide.")
    p.add_argument("--mad-k", type=float, default=6.0,
                   help="Seuil d'aberration (multiples de MAD).")
    p.add_argument("--min-abs", type=float, default=0.4,
                   help="Durée (s) en dessous de laquelle un clip est suspect.")
    p.add_argument("--ratio-low", type=float, default=0.5,
                   help="Ratio durée/attendu mini avant de signaler (trop court).")
    p.add_argument("--ratio-high", type=float, default=2.0,
                   help="Ratio durée/attendu maxi avant de signaler (trop long).")
    p.add_argument("--cap", type=int, default=50,
                   help="Nb max d'exemples listés/catégorie/récitateur dans le rapport. "
                        "Mettre très haut (ex. 100000) pour un rapport EXHAUSTIF "
                        "destiné à la correction.")
    p.add_argument("--out", type=Path,
                   default=Path("Data/processed/audio_verify_report.json"))
    p.add_argument("--emit-worklist", action="store_true",
                   help="Écrit aussi une worklist .tsv des clés à réparer.")
    p.add_argument("--quiet", action="store_true", help="Pas de résumé console.")
    args = p.parse_args(argv)

    if not args.audio_root.exists():
        raise SystemExit(f"Dossier audio introuvable : {args.audio_root}")

    layers = ({"inventory", "integrity", "plausibility"} if args.deep
              else {x.strip() for x in args.layers.split(",") if x.strip()})
    unknown = layers - {"inventory", "integrity", "plausibility"}
    if unknown:
        raise SystemExit(f"Couche(s) inconnue(s) : {', '.join(sorted(unknown))}")
    # la plausibilité a besoin des durées de l'intégrité
    if "plausibility" in layers:
        layers.add("integrity")

    canonical, muqattaat = load_corpus(args.text)
    reciters = args.reciter or list_reciter_dirs(args.audio_root)

    report = verify(
        args.audio_root, canonical, reciters, layers, args.surah, args.sample,
        args.min_bytes, args.workers, args.mad_k, args.min_abs,
        args.ratio_low, args.ratio_high, args.cap, muqattaat)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"✅ Rapport écrit : {args.out}")

    if args.emit_worklist:
        work = emit_worklist(report)
        wl = args.out.with_name("audio_repair_worklist.tsv")
        wl.write_text("reciter\tkey\treason\n" + "\n".join(work) + "\n",
                      encoding="utf-8")
        print(f"✅ Worklist écrite : {wl}  ({len(work)} entrées)")

    if not args.quiet:
        print_summary(report, _load_known_reciters(args.audio_map))
    return 0


if __name__ == "__main__":
    sys.exit(main())
