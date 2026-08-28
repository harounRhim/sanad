# -*- coding: utf-8 -*-
"""
tests/test_alignment.py — Validation hors-ligne du pipeline (sans Supabase).

Vérifie le cœur de la correction : les offsets (start, end) des annotations
tranchent bien le texte uthmani, le mot englobant est cohérent, le vocabulaire
des règles correspond aux données, et le flux complet (extraction -> enrichissement
audio -> loader) tourne via un client Supabase factice.

Exécution :
    pytest -q                         # depuis la racine du repo
    python tests/test_alignment.py    # sans pytest (runner intégré)
"""

from __future__ import annotations

import io
import sys
from collections import Counter
from pathlib import Path

import ijson

# --- résolution des chemins : on rend le package importable et on situe Data/ ---
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
DATA = ROOT / "Data"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Console Windows : éviter les crashs cp1252 quand on imprime de l'arabe.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from tajweed.quran_text import load_verses                              # noqa: E402
from tajweed.extractor import (iter_segments, enrich_with_audio,        # noqa: E402
                               load_audio_map, RULE_LABELS, canonical_rule)
from tajweed.supabase_loader import SupabaseLoader                      # noqa: E402

TEXT = DATA / "raw" / "quran-uthmani.txt"
JSON = DATA / "raw" / "tajweed.hafs.uthmani-pause-sajdah.json"
AUDIO_MAP = DATA / "processed" / "audio_map.json"

# audio_map.json est un artefact GENERE par `python -m tajweed.audio_mapper`
# (8 Mo, non versionne). Les deux tests qui en dependent sont ignores quand il
# est absent -- typiquement en CI -- plutot que de faire echouer la suite.
try:
    import pytest as _pytest
    requires_audio_map = _pytest.mark.skipif(
        not AUDIO_MAP.exists(),
        reason="requires Data/processed/audio_map.json (generated locally, not committed)",
    )
except ImportError:  # runner integre, sans pytest
    def requires_audio_map(fn):
        return fn

# Chargé une fois (réutilisé par tous les tests).
VERSES = load_verses(TEXT)


# ------------------------------- mock loader -------------------------------

class _FakeTable:
    def __init__(self, name, sink):
        self.name, self.sink = name, sink

    def upsert(self, rows, on_conflict=None):
        self._rows, self._conflict = rows, on_conflict
        return self

    def execute(self):
        # On capture (table, nb_lignes, clé on_conflict) sans aucun réseau.
        self.sink.append((self.name, len(self._rows), self._conflict))
        return self


class FakeClient:
    """Client Supabase factice : enregistre les upserts au lieu de les envoyer."""
    def __init__(self):
        self.calls = []

    def table(self, name):
        return _FakeTable(name, self.calls)


# --------------------------------- tests -----------------------------------

def test_load_verses_count_and_content():
    assert len(VERSES) == 6236, f"attendu 6236 versets, obtenu {len(VERSES)}"
    assert (1, 1) in VERSES and (114, 6) in VERSES
    assert VERSES[(1, 1)].startswith("بِسْمِ")


def test_rule_vocabulary_matches_data():
    """Les 18 règles déclarées doivent être exactement celles du fichier."""
    found = set()
    with JSON.open("rb") as fh:
        for obj in ijson.items(fh, "item"):
            for ann in obj.get("annotations", []):
                found.add(ann["rule"])
    assert found == set(RULE_LABELS), (
        f"écart vocabulaire : manquantes={found - set(RULE_LABELS)} "
        f"en trop={set(RULE_LABELS) - found}"
    )


def test_canonical_rule_normalisation_and_rejection():
    assert canonical_rule("Madd 2") == "madd_2"
    assert canonical_rule("madd-2") == "madd_2"
    assert canonical_rule("  GHUNNAH ") == "ghunnah"
    try:
        canonical_rule("not_a_rule")
    except SystemExit:
        pass
    else:
        raise AssertionError("une règle inconnue doit lever SystemExit")


def test_madd_246_known_offset():
    """Repère connu : 1:1 madd_246 = (35, 36) -> un seul caractère, non vide."""
    segs = list(iter_segments(JSON, VERSES, "madd_246", surah=1, ayah=1))
    assert len(segs) == 1
    s = segs[0]
    assert (s["start"], s["end"]) == (35, 36)
    assert s["segment"] == VERSES[(1, 1)][35:36] != ""


def test_segment_and_word_alignment_full_corpus():
    """Sur TOUT le corpus : chaque segment = texte[start:end], non vide, dans
    les bornes ; le mot englobant contient le segment et n'a pas d'espace."""
    checked = 0
    with JSON.open("rb") as fh:
        for obj in ijson.items(fh, "item"):
            key = (int(obj["surah"]), int(obj["ayah"]))
            text = VERSES.get(key)
            assert text is not None, f"verset absent du texte : {key}"
            for ann in obj.get("annotations", []):
                start, end = int(ann["start"]), int(ann["end"])
                assert 0 <= start < end <= len(text), (
                    f"offsets hors bornes {key} {ann['rule']} "
                    f"[{start}:{end}] len={len(text)}"
                )
                checked += 1
    assert checked > 60000, f"trop peu d'annotations vérifiées ({checked})"


def test_iter_segments_word_contains_segment():
    """Le mot englobant contient le segment et n'est pas vide.

    NB : certaines règles (idghaam, ikhfa) s'appliquent à la jonction de deux
    mots, donc segment ET mot peuvent légitimement contenir une espace.
    """
    n = 0
    for rule in ("ghunnah", "qalqalah", "ikhfa", "madd_2"):
        for seg in iter_segments(JSON, VERSES, rule, surah=2):
            assert seg["segment"] in seg["word"]
            assert seg["word"] != ""
            n += 1
    assert n > 0


def test_filters_surah_ayah():
    """Le filtre (surah, ayah) ne renvoie que les segments de ce verset."""
    in_surah2 = list(iter_segments(JSON, VERSES, "madd_2", surah=2))
    assert in_surah2, "attendu des segments madd_2 en sourate 2"
    target_ayah = in_surah2[0]["ayah"]
    filtered = list(iter_segments(JSON, VERSES, "madd_2", surah=2, ayah=target_ayah))
    assert filtered
    assert all(s["surah"] == 2 and s["ayah"] == target_ayah for s in filtered)
    assert len(filtered) == sum(1 for s in in_surah2 if s["ayah"] == target_ayah)


def test_iter_segments_is_lazy_generator():
    import types
    gen = iter_segments(JSON, VERSES, "madd_2")
    assert isinstance(gen, types.GeneratorType)


def test_segment_counts_match_raw_per_rule_surah1():
    """Les comptes par règle en sourate 1 doivent égaler ceux du JSON brut."""
    raw = Counter()
    with JSON.open("rb") as fh:
        for obj in ijson.items(fh, "item"):
            if int(obj["surah"]) == 1:
                for ann in obj.get("annotations", []):
                    raw[ann["rule"]] += 1
    for rule in RULE_LABELS:
        got = sum(1 for _ in iter_segments(JSON, VERSES, rule, surah=1))
        assert got == raw.get(rule, 0), f"{rule}: extracteur={got} brut={raw.get(rule, 0)}"


@requires_audio_map
def test_full_pipeline_mock_loader_surah1_multi_reciter():
    """Bout-en-bout sans DB : extraction -> audio -> loader (client factice)."""
    amap = load_audio_map(AUDIO_MAP)
    n_reciters = len(amap["map"])
    client = FakeClient()
    loader = SupabaseLoader(client=client, batch_size=500,
                            dead_letter_path=None, verbose=False)
    with loader:
        segs = iter_segments(JSON, VERSES, "madd_2", surah=1)
        enriched = enrich_with_audio(segs, amap)  # multi-récitateur
        loader.load(enriched)

    s = loader.stats
    assert s["segments_seen"] == 6          # madd_2 présent en 1:1..1:4, 1:6, 1:7
    assert s["segments_inserted"] == 6
    assert s["segments_failed"] == 0 and s["audio_failed"] == 0
    # 6 versets distincts × N récitateurs, dédupliqués une seule fois.
    assert s["audio_inserted"] == 6 * n_reciters
    # Les upserts segments portent bien la bonne clé on_conflict.
    seg_calls = [c for c in client.calls if c[0] == "tajweed_segments"]
    assert seg_calls and all(c[2] == "surah,ayah,rule,start_idx,end_idx" for c in seg_calls)


@requires_audio_map
def test_seed_audio_dedup_shared_with_load():
    """seed_audio_from_map puis load ne doivent pas re-pousser les mêmes audios."""
    amap = load_audio_map(AUDIO_MAP)
    n_reciters = len(amap["map"])
    loader = SupabaseLoader(client=FakeClient(), batch_size=1000,
                            dead_letter_path=None, verbose=False)
    with loader:
        loader.seed_audio_from_map(amap)
        seeded = loader.stats["audio_inserted"]
        # Tout l'audio du corpus : 6236 versets × récitateurs.
        assert seeded == 6236 * n_reciters
        # Ensuite, l'ingestion d'une sourate ne doit ajouter AUCUNE ligne audio.
        loader.load(enrich_with_audio(iter_segments(JSON, VERSES, "madd_2", surah=1), amap))
        assert loader.stats["audio_inserted"] == seeded


# ------------------------------- runner CLI --------------------------------

def _run_without_pytest() -> int:
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"  FAIL  {t.__name__}: {e!r}")
    print(f"\n{len(tests) - failed}/{len(tests)} tests passés.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_without_pytest())
