# -*- coding: utf-8 -*-
"""
src/tajweed/supabase_loader.py — Ingestion par lots vers Supabase.

Consomme le flux enrichi (sortie de enrich_with_audio) et le répartit, en
streaming, dans deux tables :
  - tajweed_segments : 1 ligne / segment (indépendant du récitateur)
  - ayah_audio       : 1 ligne / (verset, récitateur), DÉDUPLIQUÉE à la volée

Principes "production" :
  * Insertion par lots (upsert idempotent via on_conflict).
  * Déduplication des lignes audio (un même verset revient sur chaque segment).
  * Résilience : un lot qui échoue est ré-essayé, puis isolé ligne par ligne ;
    les lignes définitivement en échec partent dans un "dead-letter" JSONL et
    le flux NE S'ARRÊTE JAMAIS.
  * Client injectable : testable hors-ligne (mock) ; en prod, créé depuis
    les variables d'environnement SUPABASE_URL / SUPABASE_KEY.

DDL attendu (à exécuter dans Supabase avant l'ingestion) :

    create table if not exists tajweed_segments (
      id         bigint generated always as identity primary key,
      surah      smallint not null,
      ayah       smallint not null,
      rule       text     not null,
      start_idx  int      not null,
      end_idx    int      not null,
      segment    text     not null,
      word       text     not null,
      created_at timestamptz default now(),
      unique (surah, ayah, rule, start_idx, end_idx)
    );

    create table if not exists ayah_audio (
      surah      smallint not null,
      ayah       smallint not null,
      reciter    text     not null,
      audio_path text     not null,
      created_at timestamptz default now(),
      primary key (surah, ayah, reciter)
    );
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

SURAH_CONFLICT = "surah"
JUZ_CONFLICT = "juz"
PAGE_CONFLICT = "page"
VERSE_CONFLICT = "surah,ayah"
SEG_CONFLICT = "surah,ayah,rule,start_idx,end_idx"
AUDIO_CONFLICT = "surah,ayah,reciter"


class SupabaseLoader:
    def __init__(
        self,
        client=None,
        *,
        batch_size: int = 500,
        max_retries: int = 3,
        retry_backoff: float = 1.0,
        dead_letter_path: Optional[Path] = Path("data/processed/dead_letter.jsonl"),
        segments_table: str = "tajweed_segments",
        audio_table: str = "ayah_audio",
        surahs_table: str = "surahs",
        juz_table: str = "juz",
        pages_table: str = "pages",
        verses_table: str = "verses",
        verbose: bool = True,
    ):
        self.client = client if client is not None else self._client_from_env()
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.dead_letter_path = Path(dead_letter_path) if dead_letter_path else None
        self.segments_table = segments_table
        self.audio_table = audio_table
        self.surahs_table = surahs_table
        self.juz_table = juz_table
        self.pages_table = pages_table
        self.verses_table = verses_table
        self.verbose = verbose

        self._seg_buf: List[dict] = []
        self._audio_buf: List[dict] = []
        self._audio_seen: set = set()  # (surah, ayah, reciter) déjà mises en file

        self.stats: Dict[str, int] = {
            "segments_seen": 0, "segments_inserted": 0, "segments_failed": 0,
            "segments_skipped": 0, "audio_inserted": 0, "audio_failed": 0,
            "surahs_inserted": 0, "surahs_failed": 0,
            "juz_inserted": 0, "juz_failed": 0,
            "pages_inserted": 0, "pages_failed": 0,
            "verses_inserted": 0, "verses_failed": 0,
            "batch_failures": 0,
        }
        self._dl_fh = None

    # ---------------- création du client en prod ----------------
    @staticmethod
    def _client_from_env():
        try:
            from supabase import create_client
        except ImportError:
            raise SystemExit("pip install supabase  (puis définis SUPABASE_URL / SUPABASE_KEY)")
        # Secrets centralisés dans config (charge .env si présent) — jamais en dur.
        try:
            from .config import supabase_credentials
        except ImportError:  # exécution hors package
            from config import supabase_credentials
        url, key = supabase_credentials()
        return create_client(url, key)

    # ---------------- mapping segment -> lignes ----------------
    @staticmethod
    def _seg_row(seg: dict) -> dict:
        return {
            "surah": seg["surah"], "ayah": seg["ayah"], "rule": seg["rule"],
            "start_idx": seg["start"], "end_idx": seg["end"],
            "segment": seg["segment"], "word": seg["word"],
        }

    @staticmethod
    def _audio_pairs(seg: dict) -> Iterator[Tuple[int, int, str, str]]:
        """Génère (surah, ayah, reciter, audio_path) selon la forme de l'enrichissement."""
        if seg.get("audio_paths"):                       # multi-récitateurs
            for reciter, path in seg["audio_paths"].items():
                if path:
                    yield seg["surah"], seg["ayah"], reciter, path
        elif seg.get("audio_path"):                      # récitateur unique
            yield seg["surah"], seg["ayah"], seg.get("reciter", "default"), seg["audio_path"]

    # ---------------- boucle principale (streaming) ----------------
    def load(self, segments: Iterator[dict]) -> Dict[str, int]:
        for seg in segments:
            try:
                self._seg_buf.append(self._seg_row(seg))
                self.stats["segments_seen"] += 1
                if len(self._seg_buf) >= self.batch_size:
                    self._flush_segments()

                for s, a, reciter, path in self._audio_pairs(seg):
                    key = (s, a, reciter)
                    if key in self._audio_seen:
                        continue
                    self._audio_seen.add(key)
                    self._audio_buf.append(
                        {"surah": s, "ayah": a, "reciter": reciter, "audio_path": path}
                    )
                    if len(self._audio_buf) >= self.batch_size:
                        self._flush_audio()
            except Exception as e:  # segment malformé -> on logue et on continue
                self.stats["segments_skipped"] += 1
                self._dead_letter("_input", {"error": repr(e), "seg": self._safe(seg)})
        self.flush_all()
        return self.stats

    def flush_all(self) -> None:
        self._flush_segments()
        self._flush_audio()

    # ---------------- amorçage audio complet (indépendant des segments) -------
    def seed_audio_from_map(self, audio_map: dict) -> Dict[str, int]:
        """Peuple ayah_audio pour TOUS les versets présents dans audio_map.json,
        indépendamment des règles Tajweed. Réutilise le même batching, la même
        déduplication (_audio_seen) et le même dead-letter que load().

        Appelée AVANT load(), elle évite aussi de re-pousser les mêmes lignes
        audio pendant l'ingestion des segments (jeu de dédup partagé).
        """
        root = audio_map.get("audio_root", "")
        amap = audio_map["map"]
        multi = audio_map.get("multi_reciter")
        if multi is None:  # rétro-compat : déduire de la forme
            multi = bool(amap) and isinstance(next(iter(amap.values())), dict)

        def emit(reciter: str, key: str, rel: str) -> None:
            if not rel:
                return
            s, a = (int(x) for x in key.split(":"))
            dedup_key = (s, a, reciter)
            if dedup_key in self._audio_seen:
                return
            self._audio_seen.add(dedup_key)
            full = f"{root.rstrip('/')}/{rel}" if root else rel
            self._audio_buf.append(
                {"surah": s, "ayah": a, "reciter": reciter, "audio_path": full}
            )
            if len(self._audio_buf) >= self.batch_size:
                self._flush_audio()

        if multi:
            for reciter, verses in amap.items():
                for key, rel in verses.items():
                    emit(reciter, key, rel)
        else:
            for key, rel in amap.items():
                emit("default", key, rel)

        self._flush_audio()
        return self.stats

    # ---------------- amorçage métadonnées (sourates + texte des versets) -----
    def seed_surahs(self, rows: Iterator[dict]) -> Dict[str, int]:
        """Peuple la table `surahs` (cf. metadata.load_surahs)."""
        self._seed_generic(self.surahs_table, rows, SURAH_CONFLICT,
                           "surahs_inserted", "surahs_failed")
        return self.stats

    def seed_juz(self, rows: Iterator[dict]) -> Dict[str, int]:
        """Peuple la table `juz` (cf. metadata.load_juz)."""
        self._seed_generic(self.juz_table, rows, JUZ_CONFLICT,
                           "juz_inserted", "juz_failed")
        return self.stats

    def seed_pages(self, rows: Iterator[dict]) -> Dict[str, int]:
        """Peuple la table `pages` (cf. metadata.load_pages)."""
        self._seed_generic(self.pages_table, rows, PAGE_CONFLICT,
                           "pages_inserted", "pages_failed")
        return self.stats

    def seed_verses(self, rows: Iterator[dict]) -> Dict[str, int]:
        """Peuple la table `verses` avec le texte uthmani (cf. metadata.verse_rows)."""
        self._seed_generic(self.verses_table, rows, VERSE_CONFLICT,
                           "verses_inserted", "verses_failed")
        return self.stats

    def _seed_generic(self, table: str, rows: Iterator[dict], conflict: str,
                      ok_stat: str, fail_stat: str) -> None:
        """Upsert en streaming d'un flux de lignes déjà formées (mêmes batching,
        résilience et dead-letter que load())."""
        buf: List[dict] = []
        for row in rows:
            buf.append(row)
            if len(buf) >= self.batch_size:
                self._flush(table, buf, conflict, ok_stat, fail_stat)
        self._flush(table, buf, conflict, ok_stat, fail_stat)

    # ---------------- upsert direct de lignes déjà formées (replay) ----------
    def conflict_for(self, table: str) -> Optional[str]:
        return {self.segments_table: SEG_CONFLICT,
                self.audio_table: AUDIO_CONFLICT,
                self.surahs_table: SURAH_CONFLICT,
                self.juz_table: JUZ_CONFLICT,
                self.pages_table: PAGE_CONFLICT,
                self.verses_table: VERSE_CONFLICT}.get(table)

    def upsert_rows(self, table: str, rows: List[dict]) -> Tuple[int, int]:
        """Upsert par lots d'un ensemble de lignes déjà formées (pas de segments).
        Renvoie (insérées_ok, échouées). Les échecs définitifs vont au dead-letter.
        Utilisé par replay_dead_letter.py.
        """
        conflict = self.conflict_for(table)
        if conflict is None:
            raise ValueError(f"Table inconnue : '{table}' (replay impossible).")
        ok = fail = 0
        for i in range(0, len(rows), self.batch_size):
            chunk = rows[i:i + self.batch_size]
            if self._upsert_with_retry(table, chunk, conflict):
                ok += len(chunk)
            else:
                self.stats["batch_failures"] += 1
                for row in chunk:
                    if self._upsert_with_retry(table, [row], conflict):
                        ok += 1
                    else:
                        fail += 1
                        self._dead_letter(table, row)
        return ok, fail

    # ---------------- flush + résilience ----------------
    def _flush_segments(self) -> None:
        self._flush(self.segments_table, self._seg_buf, SEG_CONFLICT,
                    "segments_inserted", "segments_failed")

    def _flush_audio(self) -> None:
        self._flush(self.audio_table, self._audio_buf, AUDIO_CONFLICT,
                    "audio_inserted", "audio_failed")

    def _flush(self, table: str, buf: List[dict], conflict: str,
               ok_stat: str, fail_stat: str) -> None:
        if not buf:
            return
        rows = list(buf)
        buf.clear()
        if self._upsert_with_retry(table, rows, conflict):
            self.stats[ok_stat] += len(rows)
            return
        # Le lot a échoué malgré les retries -> on isole ligne par ligne.
        self.stats["batch_failures"] += 1
        self._log(f"[{table}] lot de {len(rows)} en échec -> isolation ligne par ligne")
        for row in rows:
            if self._upsert_with_retry(table, [row], conflict):
                self.stats[ok_stat] += 1
            else:
                self.stats[fail_stat] += 1
                self._dead_letter(table, row)

    def _upsert_with_retry(self, table: str, rows: List[dict], conflict: str) -> bool:
        for attempt in range(1, self.max_retries + 1):
            try:
                self.client.table(table).upsert(rows, on_conflict=conflict).execute()
                return True
            except Exception as e:
                if attempt < self.max_retries:
                    self._log(f"[{table}] tentative {attempt}/{self.max_retries} : {e}")
                    time.sleep(self.retry_backoff * attempt)
                else:
                    self._log(f"[{table}] échec définitif : {e}")
        return False

    # ---------------- dead-letter ----------------
    def _dead_letter(self, table: str, row: dict) -> None:
        if not self.dead_letter_path:
            return
        if self._dl_fh is None:
            self.dead_letter_path.parent.mkdir(parents=True, exist_ok=True)
            self._dl_fh = self.dead_letter_path.open("a", encoding="utf-8")
        self._dl_fh.write(json.dumps(
            {"ts": datetime.now(timezone.utc).isoformat(), "table": table, "row": row},
            ensure_ascii=False) + "\n")
        self._dl_fh.flush()

    @staticmethod
    def _safe(seg) -> dict:
        try:
            return {k: seg[k] for k in ("surah", "ayah", "rule", "start", "end")}
        except Exception:
            return {"repr": repr(seg)[:200]}

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg)

    # ---------------- context manager ----------------
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.flush_all()
        if self._dl_fh:
            self._dl_fh.close()
            self._dl_fh = None