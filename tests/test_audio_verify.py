# -*- coding: utf-8 -*-
"""
tests/test_audio_verify.py — Validation du vérificateur audio (sans vrais MP3).

Couvre les trois couches sur des fixtures synthétiques minuscules :
  - parse_key / inventory : couverture, manquants, hors-corpus, doublons ;
  - probe_file : classement par taille (vide / tiny / corrompu) ;
  - theil_sen : récupère pente+ordonnée d'une droite bruitée + aberrants ;
  - plausibility : ne signale QUE le grossier (ratio hors bande), pas la
    variation de style naturelle.

Exécution :
    pytest -q
    python tests/test_audio_verify.py
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from tajweed import audio_verify as av  # noqa: E402


# ------------------------------ parse_key ----------------------------------

def test_parse_key_valid_and_invalid():
    assert av.parse_key("001001.mp3") == (1, 1)
    assert av.parse_key("114006.mp3") == (114, 6)
    assert av.parse_key("002255.ogg") == (2, 255)
    # mauvais nombre de chiffres / sourate hors plage / non audio-clé
    assert av.parse_key("12345.mp3") is None        # 5 chiffres
    assert av.parse_key("999001.mp3") is None        # sourate > 114
    assert av.parse_key("bismillah.mp3") is None     # aucun chiffre


# ------------------------------ inventaire ---------------------------------

def test_inventory_counts(tmp_path):
    canonical = {(1, 1), (1, 2), (1, 3), (2, 1)}
    # présents : 1:1, 1:2 (manque 1:3 et 2:1), plus un hors-corpus 5:7,
    # plus un doublon de 1:1, plus un fichier non parsable.
    mapped = {(1, 1): Path("a/001001.mp3"),
              (1, 2): Path("a/001002.mp3"),
              (5, 7): Path("a/005007.mp3")}
    unparsed = [Path("a/intro.mp3")]
    duplicates = [((1, 1), Path("a/001001 (copy).mp3"))]
    inv = av.inventory_reciter("a", mapped, unparsed, duplicates, canonical)
    assert inv["present"] == 3
    assert inv["missing_count"] == 2          # 1:3 et 2:1
    assert set(inv["missing"]) == {"1:3", "2:1"}
    assert inv["extra_count"] == 1            # 5:7
    assert inv["duplicate_count"] == 1
    assert inv["unparsed_count"] == 1


# ----------------------------- probe_file ----------------------------------

def test_probe_file_size_classes(tmp_path):
    empty = tmp_path / "empty.mp3"
    empty.write_bytes(b"")
    assert av.probe_file(empty, min_bytes=1024)["status"] == "empty"

    tiny = tmp_path / "tiny.mp3"
    tiny.write_bytes(b"\x00" * 100)
    assert av.probe_file(tiny, min_bytes=1024)["status"] == "tiny"

    # >= plancher mais pas un MP3 valide : mutagen ne le décode pas.
    junk = tmp_path / "junk.mp3"
    junk.write_bytes(b"\x00" * 4096)
    assert av.probe_file(junk, min_bytes=1024)["status"] in {"corrupt", "unreadable"}

    missing = tmp_path / "nope.mp3"
    assert av.probe_file(missing, min_bytes=1024)["status"] == "missing"


# ------------------------------ theil_sen ----------------------------------

def test_theil_sen_recovers_line():
    rng = random.Random(0)
    # y = 1.0 + 0.4 x, plus un peu de bruit + 2 aberrants grossiers.
    xs = [float(i) for i in range(5, 60)]
    ys = [1.0 + 0.4 * x + rng.uniform(-0.2, 0.2) for x in xs]
    ys[10] += 30          # aberrant
    ys[20] -= 25          # aberrant
    a, b = av.theil_sen(xs, ys, rng)
    assert abs(b - 0.4) < 0.05
    assert abs(a - 1.0) < 1.0


# ----------------------------- plausibilité --------------------------------

def _line_durations(rng, slope=0.4, intercept=1.0, n=200, jitter=0.25):
    """Durées synthétiques suivant durée = intercept + slope*lettres + bruit %."""
    durations = {}
    canonical = {}
    for i in range(n):
        s, a = 1 + i // 6, 1 + i % 6
        letters = rng.randint(8, 220)
        base = intercept + slope * letters
        dur = base * (1.0 + rng.uniform(-jitter, jitter))
        durations[(s, a)] = round(dur, 2)
        canonical[(s, a)] = letters
    return durations, canonical


def test_plausibility_flags_only_gross():
    rng = random.Random(42)
    durations, canonical = _line_durations(rng)
    keys = list(durations)
    # Injecte 3 anomalies GROSSIÈRES.
    trunc = keys[3]
    durations[trunc] = 0.1                                  # quasi vide
    swap_long = keys[7]
    durations[swap_long] = (1.0 + 0.4 * canonical[swap_long]) * 3.0   # 3x trop long
    swap_short = keys[11]
    durations[swap_short] = (1.0 + 0.4 * canonical[swap_short]) * 0.3  # 0.3x trop court

    res = av.plausibility_reciter(durations, canonical, mad_k=6.0,
                                  min_abs=0.4, rng=rng)
    flagged = {o["key"] for o in res["outliers"]}
    want = {f"{k[0]}:{k[1]}" for k in (trunc, swap_long, swap_short)}
    assert want <= flagged, f"anomalies manquées : {want - flagged}"
    # Le bruit naturel (±25 %) ne doit pas exploser la liste.
    assert res["outlier_count"] <= len(want) + 3, res["outlier_count"]


def test_is_muqattaat():
    assert av._is_muqattaat("الم")   # 2:1 (basmala retirée)
    assert av._is_muqattaat("عسق")   # 42:2
    assert av._is_muqattaat("يس")    # 36:1
    assert not av._is_muqattaat("فاخذتهم")          # mot normal
    assert not av._is_muqattaat("")                  # vide
    assert not av._is_muqattaat("الفجراليوم")        # > 6 lettres


def test_plausibility_skips_muqattaat_keys():
    rng = random.Random(7)
    durations, canonical = _line_durations(rng)
    keys = list(durations)
    muq = keys[5]
    # Donne au muqattaʿāt une durée grossièrement longue : sans skip il serait
    # signalé ; avec skip_keys il doit être ignoré.
    durations[muq] = (1.0 + 0.4 * canonical[muq]) * 4.0
    flagged_no_skip = {o["key"] for o in av.plausibility_reciter(
        durations, canonical, 6.0, 0.4, rng).get("outliers", [])}
    flagged_skip = {o["key"] for o in av.plausibility_reciter(
        durations, canonical, 6.0, 0.4, rng,
        skip_keys=frozenset({muq})).get("outliers", [])}
    label = f"{muq[0]}:{muq[1]}"
    assert label in flagged_no_skip
    assert label not in flagged_skip


def test_plausibility_skips_when_too_few():
    rng = random.Random(1)
    durations = {(1, 1): 3.0, (1, 2): 4.0, (1, 3): 5.0}
    canonical = {(1, 1): 10, (1, 2): 12, (1, 3): 14}
    res = av.plausibility_reciter(durations, canonical, 6.0, 0.4, rng)
    assert res.get("skipped") is True
    assert res["outliers"] == []


# ----------------------------- worklist ------------------------------------

def test_emit_worklist_collects_all_problem_classes():
    report = {"reciters": {"r1": {
        "inventory": {"missing": ["1:3", "2:1"]},
        "integrity": {"bad": [{"key": "1:5", "status": "empty"}]},
        "plausibility": {"outliers": [{"key": "9:1", "reason": "too_long"}]},
    }}}
    work = av.emit_worklist(report)
    assert "r1\t1:3\tmissing" in work
    assert "r1\t1:5\tempty" in work
    assert "r1\t9:1\ttoo_long" in work
    assert len(work) == 4


# ------------------------------- runner ------------------------------------

def _run_without_pytest() -> int:
    import inspect
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    tmp_root = Path(__file__).resolve().parent / "_tmp_av"
    tmp_root.mkdir(exist_ok=True)
    for t in tests:
        try:
            if "tmp_path" in inspect.signature(t).parameters:
                d = tmp_root / t.__name__
                d.mkdir(exist_ok=True)
                t(d)
            else:
                t()
            print(f"  PASS  {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  FAIL  {t.__name__}: {e!r}")
    print(f"\n{len(tests) - failed}/{len(tests)} tests passés.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_without_pytest())
