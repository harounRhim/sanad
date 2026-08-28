# Tajweed-Audio-Supabase Pipeline

ETL en streaming qui normalise le texte coranique (uthmani), ses annotations
**Tajweed** et ~36 Go d'audio multi-récitateurs vers une base **Supabase /
PostgreSQL** prête pour une application web/mobile.

Conçu pour traiter de gros volumes **sans saturer la RAM** : tout est en
streaming (générateurs + `ijson`), les insertions sont par lots, idempotentes
(`upsert ... on_conflict`), et résilientes (file *dead-letter* rejouable).

---

## Architecture

```
quran-uthmani.txt ─┐
tajweed…json ──────┼─► iter_segments (ijson) ─► enrich_with_audio ─► SupabaseLoader ─► Supabase
audio_map.json ────┘        (extractor)            (extractor)       (batch + dead-letter)
                                                        ▲
data/audio/** ─► audio_mapper.py ─► audio_map.json ─────┘
```

| Module | Rôle |
|---|---|
| `src/tajweed/audio_mapper.py` | Scanne `data/audio/**` (streaming, ne lit aucun octet) → `audio_map.json` (`{récitateur: {"sourate:ayah": chemin}}`). |
| `src/tajweed/quran_text.py` | `load_verses` : `quran-uthmani.txt` → `{(sourate, ayah): texte}`. |
| `src/tajweed/metadata.py` | `load_surahs` (noms + ayah_count + makki/madani), `load_juz` (30 bornes de juz), `load_pages` (604 pages du mushaf), `verse_rows` (texte uthmani → lignes `verses`). |
| `src/tajweed/extractor.py` | `iter_segments` (découpe les segments via offsets), `enrich_with_audio` (ajoute les chemins audio), `RULE_LABELS`, `canonical_rule`. |
| `src/tajweed/supabase_loader.py` | Upserts par lots, déduplication audio, retries, dead-letter. |
| `src/tajweed/ingest.py` | Orchestrateur : seed audio → streaming des segments → loader. |
| `src/tajweed/replay_dead_letter.py` | Rejoue les lignes en échec jusqu'à convergence. |
| `src/tajweed/config.py` | Charge `.env`, expose les identifiants Supabase (aucun secret en dur). |

### Schéma (`schema.sql`)
- **`surahs`** — 1 ligne par sourate (114) ; clé `surah`. Noms ar/en/translittéré, `ayah_count`, `revelation_place` (makki/madani).
- **`juz`** — 1 ligne par juz (30) ; clé `juz`. Bornes `start_surah/start_ayah` → `end_surah/end_ayah`.
- **`pages`** — 1 ligne par page du mushaf (604, layout Madani/Tanzil) ; clé `page`. Mêmes bornes début/fin.
- **`verses`** — 1 ligne par `(surah, ayah)` (6236) ; texte uthmani. **C'est ce texte que les offsets `start_idx/end_idx` indexent** → l'app colore `text[start_idx:end_idx]`.
- **`tajweed_segments`** — 1 ligne par segment ; unique `(surah, ayah, rule, start_idx, end_idx)`.
- **`ayah_audio`** — 1 ligne par `(surah, ayah, reciter)` ; clé primaire composite.

---

## Données

```
Data/
├── raw/
│   ├── quran-uthmani.txt                       # sourate|ayah|texte  (6236 versets)
│   └── tajweed.hafs.uthmani-pause-sajdah.json  # [{surah,ayah,annotations:[{start,end,rule}]}]  (18 règles)
├── processed/
│   ├── audio_map.json                          # généré par audio_mapper.py
│   └── dead_letter.jsonl                        # généré à l'ingestion en cas d'échec
└── audio/ayahs/<récitateur>/SSSAAA.mp3          # ~36 Go (30 récitateurs)
```

Les **chemins audio sont stockés en relatif** (`audio_root` + chemin du fichier) ;
c'est à l'application d'y préfixer une URL de base (Storage / CDN) à l'exécution.

---

## Prérequis

```bash
pip install -r requirements.txt
```

> **Windows** : exécute Python avec `PYTHONIOENCODING=utf-8`, sinon l'affichage
> de l'arabe plante (console cp1252).

---

## Mise en route

### 1. Secrets
Copie `.env.example.txt` en `.env` (racine du repo) et renseigne :
```
SUPABASE_URL=https://<projet>.supabase.co
SUPABASE_KEY=<clé service_role>     # côté serveur uniquement, contourne la RLS
```
Le `.env` est ignoré par git (`.gitignore`).

### 2. Schéma
Exécute `schema.sql` dans Supabase → SQL Editor (ou `psql "<conn>" -f schema.sql`).

### 3. Construire la carte audio (une fois)
```bash
cd src
python -m tajweed.audio_mapper \
  --audio-root ../Data/audio/ayahs \
  --text ../Data/raw/quran-uthmani.txt \
  --out ../Data/processed/audio_map.json
# --dry-run pour un rapport sans écrire ; --flat pour forcer un seul niveau
```

### 4. Ingestion
```bash
cd src
# Test d'abord sur une sourate :
PYTHONIOENCODING=utf-8 python -m tajweed.ingest --all-rules --seed-meta --seed-audio --surah 1 \
  --text ../Data/raw/quran-uthmani.txt \
  --json ../Data/raw/tajweed.hafs.uthmani-pause-sajdah.json \
  --audio-map ../Data/processed/audio_map.json

# Puis le corpus complet :
PYTHONIOENCODING=utf-8 python -m tajweed.ingest --all-rules --seed-meta --seed-audio --batch-size 1000 \
  --text ../Data/raw/quran-uthmani.txt \
  --json ../Data/raw/tajweed.hafs.uthmani-pause-sajdah.json \
  --audio-map ../Data/processed/audio_map.json
```

Options utiles : `--rule ghunnah` (une règle), `--reciter alafasy` (un seul
récitateur ; sinon tous), `--surah` / `--ayah` (filtre), `--seed-audio` (peuple
`ayah_audio` pour TOUS les versets : ~187 080 lignes = 6236 × 30), `--seed-meta`
(peuple `surahs` = 114, `juz` = 30, `pages` = 604 et `verses` = 6236 depuis
`Data/audio/data/quran_.json` + le texte uthmani). `--seed-meta`/`--seed-audio`
sont idempotents (upsert).

### 5. Rejeu des échecs
En cas d'échecs, les lignes partent dans `Data/processed/dead_letter.jsonl` —
le flux ne s'arrête jamais. Pour les rejouer :
```bash
cd src
python -m tajweed.replay_dead_letter            # --dry-run pour compter seulement
```
Les lignes encore en échec vont dans un fichier *résiduel distinct*
(`dead_letter.replay.jsonl`) — rejouable plusieurs fois jusqu'à convergence.

### 6. Vérification audio (`audio_verify.py`)

Contrôle les ~187 000 fichiers (30 récitateurs × 6236) en *streaming* — ne lit
que `stat` + les en-têtes MP3 (via `mutagen`, pas de ffmpeg). Trois couches :

```bash
# inventaire rapide : couverture vs corpus, orphelins, dossiers vides (secondes)
PYTHONIOENCODING=utf-8 python -m tajweed.audio_verify --layers inventory

# intégrité + plausibilité, échantillon par récitateur, worklist de réparation
PYTHONIOENCODING=utf-8 python -m tajweed.audio_verify --deep --sample 400 \
    --workers 8 --emit-worklist

# audit complet d'un récitateur
PYTHONIOENCODING=utf-8 python -m tajweed.audio_verify --deep --reciter alafasy
```

- **inventory** — manquants/hors-corpus/doublons par récitateur vs les 6236 ayahs.
- **integrity** — taille ≥ `--min-bytes`, en-tête lisible, durée/bitrate > 0.
- **plausibility** — modèle robuste `durée = a + b·lettres` (Theil–Sen) ; ne
  signale que le *grossier* (ratio hors `[--ratio-low, --ratio-high]`, déf. 0,5–2×,
  ou durée < `--min-abs`) → file de revue fiable, pas du bruit de style.

Sortie : `Data/processed/audio_verify_report.json` (+ `audio_repair_worklist.tsv`
avec `--emit-worklist`). Pour une correction EXHAUSTIVE, relancer avec un `--cap`
élevé (ex. `--cap 100000`) afin que les listes ne soient pas tronquées.

### 7. Correction (`audio_correct.py`)

Consomme le rapport et applique deux corrections RÉVERSIBLES (jamais de DELETE) :

```bash
# aperçu (dry-run) : ce qui serait corrigé — intégrité seule
PYTHONIOENCODING=utf-8 python -m tajweed.audio_correct \
    --report Data/processed/audio_verify_report_full.json

# appliquer : réécrit audio_map.json (+ sauvegarde .bak) et signale en base
PYTHONIOENCODING=utf-8 python -m tajweed.audio_correct \
    --report ..._full.json --include-plausibility --apply

# tout ré-autoriser (verified=true partout)
PYTHONIOENCODING=utf-8 python -m tajweed.audio_correct --reset-flags --apply
```

- **audio_map.json** — retire les entrées mauvaises, recompte, sauvegarde l'original.
- **ayah_audio** — `verified=false` + `flag_reason` (l'app filtre `verified=true`).
- Intégrité (cassée) corrigée par défaut ; plausibilité (revue) via `--include-plausibility`.
- `--apply` requis pour écrire ; `--no-map`/`--no-db` pour cibler une seule action.

Prérequis base : la colonne `verified` doit exister — relancer `schema.sql`
(les `ALTER … add column if not exists` sont idempotents) avant la première correction.

---

## Correction Tajweed (Phase 4, offline) — `tajweed.correction`

Moteur v1 : évalue un enregistrement contre la vérité terrain (texte + segments
Tajweed) et mesure **Madd** (durée vs ḥarakāt) et **Ghunnah** (durée + nasalité).

```bash
# démo de bout en bout SANS modèle (aligneur synthétique = plombage)
PYTHONIOENCODING=utf-8 python -m tajweed.correction.evaluate \
    --audio rec.wav --surah 112 --ayah 1 --aligner synthetic --source local

# évaluation réelle (wav2vec2 CPU). Installer d'abord les deps optionnelles :
pip install torch torchaudio transformers soundfile
PYTHONIOENCODING=utf-8 python -m tajweed.correction.evaluate \
    --audio rec.wav --surah 112 --ayah 1 --aligner wav2vec2 --source supabase \
    --out report.json
```

Architecture : `aligner` (audio↔texte, CTC forcé — seule brique ML, imports
paresseux) → `Alignment` (timing par caractère) → `rules` (mesure déterministe)
→ `Report` (JSON + résumé). Le cœur s'importe sans torch ; testé via un aligneur
synthétique.

**Calibration des normes** (`tajweed.correction.calibrate`) — apprend les bornes
attendues par règle sur des récitateurs de référence (absorbe le biais de mesure) :

```bash
# large : plage de sourates courtes
python -m tajweed.correction.calibrate --reciters alafasy husary --surah-min 100 --surah-max 114

# ciblé : règles rares (muttasil/munfasil/shafawi), ayahs les plus courtes/règle
python -m tajweed.correction.calibrate --reciters alafasy husary abdul_basit_murattal \
    --focus-rules madd_muttasil madd_munfasil ikhfa_shafawi --per-rule 60
```

Produit `Data/processed/tajweed_calibration.json` ; appliqué via
`evaluate … --calibration <fichier>`. NB : `madd_2` définit l'unité ḥaraka → il
mesure toujours ≈2 (auto-référence, non diagnostiquable).

---

## Tests

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/ -q
# ou sans pytest :
PYTHONIOENCODING=utf-8 python tests/test_alignment.py
```
Les tests valident l'alignement des offsets sur tout le corpus, le vocabulaire
des règles, le pipeline complet via un client Supabase factice (hors-ligne), et
le vérificateur audio (inventaire, intégrité, plausibilité) sur fixtures synthétiques.

---

## Téléchargement des données (optionnel)

`Data/download_data.py` récupère l'archive 36 Go depuis Hugging Face. Le token se
lit dans l'environnement :
```bash
export HF_TOKEN=hf_xxx        # PowerShell : $env:HF_TOKEN = "hf_xxx"
python Data/download_data.py
```

> ⚠️ **Sécurité** : un token Hugging Face avait été committé en clair dans ce
> script — il a été retiré, mais **doit être révoqué/rotaté** sur huggingface.co.
> Ne committe jamais de secret ; utilise `.env` / les variables d'environnement.
