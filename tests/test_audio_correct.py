# -*- coding: utf-8 -*-
"""
tests/test_audio_correct.py — Validation de la correction (sans Supabase).

Couvre la sélection des anomalies (intégrité vs plausibilité, précédence) et la
réécriture de l'audio_map (retrait + recompte + dry-run sans écriture).

Exécution :
    pytest -q
    python tests/test_audio_correct.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tajweed import audio_correct as ac  # noqa: E402


def _report():
    return {"reciters": {
        "alafasy": {
            "integrity": {"checked": 100, "ok": 98,
                          "bad": [{"key": "2:5", "status": "empty"},
                                  {"key": "3:7", "status": "corrupt"}]},
            "plausibility": {"outliers": [
                {"key": "18:2", "reason": "too_long", "ratio": 6.0},   # gros → retenu
                {"key": "9:9", "reason": "too_long", "ratio": 2.1}]},  # style → ignoré
        },
        "husary": {"error": "dossier introuvable"},
    }}


def test_collect_bad_integrity_only():
    bad = ac.collect_bad(_report(), include_plausibility=False)
    assert set(bad) == {"alafasy"}
    assert bad["alafasy"] == {(2, 5): "integrity:empty", (3, 7): "integrity:corrupt"}


def test_collect_bad_with_plausibility_only_gross():
    bad = ac.collect_bad(_report(), include_plausibility=True)
    # le gros (ratio 6.0) est retenu ; le style (ratio 2.1) est ignoré.
    assert bad["alafasy"][(18, 2)] == "review:too_long(6.0x)"
    assert (9, 9) not in bad["alafasy"]
    assert len(bad["alafasy"]) == 3   # 2 intégrité + 1 plausibilité grossière


def test_collect_bad_integrity_takes_precedence():
    rep = {"reciters": {"r": {
        "integrity": {"bad": [{"key": "1:1", "status": "corrupt"}]},
        "plausibility": {"outliers": [{"key": "1:1", "reason": "too_long", "ratio": 9.0}]},
    }}}
    bad = ac.collect_bad(rep, include_plausibility=True)
    assert bad["r"][(1, 1)] == "integrity:corrupt"  # l'intégrité prime sur la revue


def test_rewrite_map_dry_run_does_not_write(tmp_path):
    mp = tmp_path / "audio_map.json"
    original = {"map": {"alafasy": {"1:1": "alafasy/001001.mp3",
                                    "2:5": "alafasy/002005.mp3",
                                    "3:7": "alafasy/003007.mp3"}},
                "count": {"alafasy": 3}, "missing_count": {"alafasy": 6233}}
    mp.write_text(json.dumps(original), encoding="utf-8")
    bad = {"alafasy": {(2, 5): "integrity:empty", (3, 7): "integrity:corrupt"}}

    removed, doc = ac.rewrite_map(mp, bad, apply=False)
    assert removed == 2
    # dry-run : le fichier sur disque est INCHANGÉ
    assert json.loads(mp.read_text(encoding="utf-8")) == original
    # le doc renvoyé reflète bien le retrait + recompte
    assert "2:5" not in doc["map"]["alafasy"]
    assert doc["count"]["alafasy"] == 1
    assert doc["missing_count"]["alafasy"] == 6235


def test_rewrite_map_apply_writes_and_backs_up(tmp_path):
    mp = tmp_path / "audio_map.json"
    mp.write_text(json.dumps({"map": {"r": {"1:1": "r/001001.mp3",
                                            "2:5": "r/002005.mp3"}},
                              "count": {"r": 2}, "missing_count": {"r": 0}}),
                  encoding="utf-8")
    bad = {"r": {(2, 5): "integrity:empty"}}
    removed, _ = ac.rewrite_map(mp, bad, apply=True)
    assert removed == 1
    on_disk = json.loads(mp.read_text(encoding="utf-8"))
    assert "2:5" not in on_disk["map"]["r"]
    assert on_disk["count"]["r"] == 1
    # une sauvegarde .bak.* a été créée
    backups = list(tmp_path.glob("audio_map.json.bak.*"))
    assert len(backups) == 1


def _run_without_pytest() -> int:
    import inspect
    tmp_root = Path(__file__).resolve().parent / "_tmp_ac"
    tmp_root.mkdir(exist_ok=True)
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
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
