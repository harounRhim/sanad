# -*- coding: utf-8 -*-
"""
server/app.py — API HTTP du moteur de correction Tajweed ("correction as a service").

Enveloppe la fonction `evaluate()` (déjà validée hors-ligne) dans un serveur
FastAPI. Le modèle wav2vec2 (~1.2 Go) et la vérité terrain sont chargés UNE
SEULE FOIS au démarrage puis réutilisés à chaque requête (le CPU met quelques
secondes par ayah — inacceptable de recharger à chaque appel).

Lancer :
    D:/Quran_App_Project/.venv/Scripts/python.exe -m uvicorn server.app:app \
        --host 0.0.0.0 --port 8000
(ou le script server/run.ps1)

Endpoints :
    GET  /health           → { ok, model_loaded, aligner }
    POST /grade  (multipart) surah=<int> ayah=<int> file=<audio wav 16k mono>
                           → rapport JSON (cf. Report.to_dict())
    POST /grade_window (multipart) surah=<int> start_ayah=<int> file=<...>
                           → note contre une FENÊTRE de plusieurs ayahs au
                             lieu d'UNE ayah supposée (cf. WindowReport.to_dict(),
                             evaluate.evaluate_window). SUPERSEDED par
                             /grade_clip (2026-07-08) mais gardé fonctionnel.
    POST /grade_clip   (multipart) surah=<int> file=<audio wav 16k mono>
                           → note contre la SOURATE ENTIÈRE (cf.
                             ClipReport.to_dict(), evaluate.evaluate_clip) —
                             PAS d'ayah/curseur à fournir, le clip est localisé
                             dans la sourate via son contenu. C'est l'endpoint
                             utilisé par Practice.tsx pour la récitation
                             continue "sourate = un paragraphe" (Roadmap V2).

Le navigateur encode l'audio en WAV (16 kHz mono) côté client : soundfile /
torchaudio le lisent nativement, donc AUCUN ffmpeg requis côté serveur.
"""

from __future__ import annotations

import os
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

# --- Environnement AVANT tout import transformers/torch -----------------------
# Les poids complets vivent dans .hf_cache ; on force le mode hors-ligne pour ne
# jamais dépendre du réseau (cf. mémoire projet). Surchargable par l'env réel.
_ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("HF_HOME", str(_ROOT / ".hf_cache"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

sys.path.insert(0, str(_ROOT / "src"))

import json  # noqa: E402
from fastapi import FastAPI, File, Form, HTTPException, UploadFile  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from tajweed.correction.evaluate import evaluate, evaluate_window, evaluate_clip, _make_aligner  # noqa: E402
from tajweed.correction.ground_truth import LocalGroundTruth  # noqa: E402

WINDOW_AYAH_COUNT = int(os.environ.get("CORRECTION_WINDOW_AYAHS", 6))

# --- Configuration ------------------------------------------------------------
TEXT_PATH = _ROOT / "Data" / "raw" / "quran-uthmani.txt"
JSON_PATH = _ROOT / "Data" / "raw" / "tajweed.hafs.uthmani-pause-sajdah.json"
CALIB_PATH = _ROOT / "Data" / "processed" / "tajweed_calibration.json"
MODEL_ID = os.environ.get("CORRECTION_MODEL",
                          "jonatasgrosman/wav2vec2-large-xlsr-53-arabic")
MAX_UPLOAD_BYTES = int(os.environ.get("CORRECTION_MAX_BYTES", 15 * 1024 * 1024))  # 15 Mo
# Origines autorisées (frontend). Virgule-séparées ; "*" pour tout ouvrir (dev).
_ORIGINS = os.environ.get(
    "CORRECTION_ALLOW_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173",
).split(",")
# Vite se rabat sur 5174, 5175… si le port est pris ; on autorise donc tout
# localhost/127.0.0.1 quel que soit le port pour éviter les blocages CORS en dev.
_ORIGIN_REGEX = os.environ.get(
    "CORRECTION_ALLOW_ORIGIN_REGEX",
    r"^http://(localhost|127\.0\.0\.1):\d+$",
)

# État partagé, peuplé au démarrage (lifespan).
STATE: dict = {"aligner": None, "gt": None, "calibration": None, "ready": False}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Vérité terrain + normes calibrées : peu coûteux.
    STATE["gt"] = LocalGroundTruth(TEXT_PATH, JSON_PATH)
    STATE["calibration"] = (
        json.loads(CALIB_PATH.read_text(encoding="utf-8")) if CALIB_PATH.exists() else None
    )
    # Aligneur : charge le modèle wav2vec2 (~1.2 Go) et le garde chaud.
    aligner = _make_aligner("wav2vec2", MODEL_ID)
    aligner._load()  # préchauffe explicitement (sinon 1er /grade très lent)
    STATE["aligner"] = aligner
    STATE["ready"] = True
    yield
    STATE.clear()


app = FastAPI(title="Sanad — Correction Tajweed API", version="1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _ORIGINS if o.strip()],
    allow_origin_regex=_ORIGIN_REGEX,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {
        "ok": True,
        "model_loaded": bool(STATE.get("ready")),
        "aligner": getattr(STATE.get("aligner"), "name", None),
        "calibrated": STATE.get("calibration") is not None,
    }


@app.post("/grade")
async def grade(
    surah: int = Form(...),
    ayah: int = Form(...),
    file: UploadFile = File(...),
):
    if not STATE.get("ready"):
        raise HTTPException(503, "Modèle pas encore chargé, réessayez dans un instant.")
    if not (1 <= surah <= 114):
        raise HTTPException(422, f"Sourate hors bornes : {surah} (attendu 1–114).")
    if ayah < 1:
        raise HTTPException(422, f"Ayah invalide : {ayah}.")

    # Vérité terrain : valide (sourate, ayah) et fournit texte + segments.
    try:
        STATE["gt"].get(surah, ayah)
    except Exception:
        raise HTTPException(404, f"Ayah introuvable : {surah}:{ayah}.")

    raw = await file.read()
    if not raw:
        raise HTTPException(422, "Fichier audio vide.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413, f"Audio trop volumineux ({len(raw)} o > {MAX_UPLOAD_BYTES} o).")

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    try:
        tmp.write(raw)
        tmp.close()
        rep = evaluate(
            Path(tmp.name), surah, ayah,
            STATE["aligner"], STATE["gt"],
            with_nasality=True, calibration=STATE["calibration"],
        )
    except Exception as e:  # alignement/mesure échoue → 422 lisible côté client
        raise HTTPException(422, f"Échec de l'analyse audio : {e}")
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    payload = rep.to_dict()
    payload["audio_path"] = None  # ne pas divulguer le chemin temp serveur
    return payload


@app.post("/grade_window")
async def grade_window(
    surah: int = Form(...),
    start_ayah: int = Form(...),
    file: UploadFile = File(...),
):
    """Note un clip contre une FENÊTRE de plusieurs ayahs (Roadmap V2 —
    correction mot-par-mot en continu) au lieu de supposer que le clip EST
    exactement `start_ayah` — voir evaluate.evaluate_window. Corrige le bug du
    2026-07-07 : une récitation fluide sans pause entre ayahs finissait notée
    comme si tout n'était que la première ayah."""
    if not STATE.get("ready"):
        raise HTTPException(503, "Modèle pas encore chargé, réessayez dans un instant.")
    if not (1 <= surah <= 114):
        raise HTTPException(422, f"Sourate hors bornes : {surah} (attendu 1–114).")
    if start_ayah < 1:
        raise HTTPException(422, f"Ayah invalide : {start_ayah}.")

    try:
        STATE["gt"].get_range(surah, start_ayah, WINDOW_AYAH_COUNT)
    except Exception:
        raise HTTPException(404, f"Ayah introuvable : {surah}:{start_ayah}.")

    raw = await file.read()
    if not raw:
        raise HTTPException(422, "Fichier audio vide.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413, f"Audio trop volumineux ({len(raw)} o > {MAX_UPLOAD_BYTES} o).")

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    try:
        tmp.write(raw)
        tmp.close()
        rep = evaluate_window(
            Path(tmp.name), surah, start_ayah,
            STATE["aligner"], STATE["gt"], count=WINDOW_AYAH_COUNT,
            with_nasality=True, calibration=STATE["calibration"],
        )
    except Exception as e:
        raise HTTPException(422, f"Échec de l'analyse audio : {e}")
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    payload = rep.to_dict()
    payload["audio_path"] = None
    return payload


@app.post("/grade_clip")
async def grade_clip(
    surah: int = Form(...),
    file: UploadFile = File(...),
    near_ayah: int | None = Form(None),
):
    """Note un clip contre une SOURATE ENTIÈRE traitée comme un seul
    paragraphe (Roadmap V2, 2026-07-08) — voir evaluate.evaluate_clip. PAS
    d'ayah/curseur à fournir : le clip est localisé DANS la sourate via son
    contenu, pas supposé être une ayah précise. Remplace /grade_window pour
    la récitation continue — élimine la classe de bug "curseur bloqué" au
    lieu de la contourner, puisqu'il n'y a plus de curseur du tout ici.
    `near_ayah` (optionnel) : indice de proximité (départage seulement, cf.
    content_check.locate_best_span) pour les phrases qui se répètent
    mot-pour-mot ailleurs dans la même sourate (ex. Al-Fātiḥa "الرحمن
    الرحيم", à la fois fin d'ayah 1 et ayah 3 entière)."""
    if not STATE.get("ready"):
        raise HTTPException(503, "Modèle pas encore chargé, réessayez dans un instant.")
    if not (1 <= surah <= 114):
        raise HTTPException(422, f"Sourate hors bornes : {surah} (attendu 1–114).")

    raw = await file.read()
    if not raw:
        raise HTTPException(422, "Fichier audio vide.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413, f"Audio trop volumineux ({len(raw)} o > {MAX_UPLOAD_BYTES} o).")

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    try:
        tmp.write(raw)
        tmp.close()
        rep = evaluate_clip(
            Path(tmp.name), surah,
            STATE["aligner"], STATE["gt"],
            with_nasality=True, calibration=STATE["calibration"],
            near_ayah=near_ayah,
        )
    except Exception as e:
        raise HTTPException(422, f"Échec de l'analyse audio : {e}")
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    payload = rep.to_dict()
    payload["audio_path"] = None
    return payload
