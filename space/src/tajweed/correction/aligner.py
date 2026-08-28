# -*- coding: utf-8 -*-
"""
src/tajweed/correction/aligner.py — Alignement forcé audio ↔ texte.

Produit une `Alignment` : pour chaque caractère du texte uthmani, sa fenêtre
temporelle dans l'audio (ou None pour les harakat/espaces sans support propre).
C'est la SEULE brique « ML » ; le reste du moteur est déterministe.

Deux back-ends :
  - SyntheticAligner : répartit la durée uniformément (tests/démo, sans modèle).
  - Wav2Vec2Aligner  : CTC (transformers) + alignement forcé (torchaudio), CPU.
    Imports paresseux : importer ce module ne requiert pas torch.

Mapping texte→jetons : on n'aligne que les LETTRES de base (les harakat et
l'espace n'ont pas de jeton acoustique distinct), en gardant l'index uthmani
d'origine de chaque jeton pour reprojeter les temps sur le texte complet.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Tuple

from .types import Alignment

try:  # normalisation des lettres (أإآٱ→ا, etc.)
    from ..metadata import normalize_arabic
except ImportError:  # pragma: no cover
    from tajweed.metadata import normalize_arabic  # type: ignore

# Modèle CTC arabe par défaut (CPU-compatible). Surchargable.
DEFAULT_MODEL = "jonatasgrosman/wav2vec2-large-xlsr-53-arabic"


def text_to_tokens(text: str) -> Tuple[List[str], List[int]]:
    """(jetons_lettres_normalisées, index_uthmani_de_chaque_jeton).

    Ignore espaces, tatweel et marques combinantes (harakat, signes coraniques).
    """
    toks: List[str] = []
    idx: List[int] = []
    for i, ch in enumerate(text):
        if ch.isspace() or ch == "ـ":
            continue
        if unicodedata.category(ch).startswith("M"):  # marque combinante
            continue
        norm = normalize_arabic(ch)
        if not norm:
            continue
        toks.append(norm)
        idx.append(i)
    return toks, idx


def _spans_to_alignment(text: str, token_idx: List[int],
                        token_spans: List[Optional[Tuple[float, float]]],
                        duration: float,
                        decoded_text: Optional[str] = None) -> Alignment:
    """Reprojette les spans des jetons sur les caractères du texte complet."""
    char_spans: List[Optional[Tuple[float, float]]] = [None] * len(text)
    for uidx, span in zip(token_idx, token_spans):
        char_spans[uidx] = span
    return Alignment(text=text, char_spans=char_spans, duration=duration,
                     decoded_text=decoded_text)


# ------------------------------ synthétique --------------------------------

class SyntheticAligner:
    """Répartit `duration` uniformément sur les lettres. Aucune dépendance ML.

    Utile pour les tests/la démo de bout en bout (le plombage), PAS pour une
    évaluation réelle (toutes les lettres durent pareil → pas de vrai madd).
    """

    name = "synthetic"

    def __init__(self, duration: Optional[float] = None):
        self._forced_duration = duration

    def _duration(self, audio_path: Path) -> float:
        if self._forced_duration is not None:
            return self._forced_duration
        from mutagen import File as MutagenFile
        mf = MutagenFile(str(audio_path))
        return float(getattr(mf.info, "length", 0.0) or 0.0)

    def align(self, audio_path: Path, text: str) -> Alignment:
        toks, idx = text_to_tokens(text)
        dur = self._duration(Path(audio_path))
        n = len(toks)
        if n == 0:
            return Alignment(text, [None] * len(text), dur)
        step = dur / n
        spans: List[Optional[Tuple[float, float]]] = [
            (k * step, (k + 1) * step) for k in range(n)]
        return _spans_to_alignment(text, idx, spans, dur)


# ------------------------------ wav2vec2 -----------------------------------

@dataclass
class DecodeResult:
    """Résultat du décodage CTC seul — UNE passe modèle, réutilisable pour un
    forced_align ultérieur contre N'IMPORTE QUEL texte sans repasser le modèle
    (Roadmap V2 — notation "sourate = un seul paragraphe", voir
    evaluate.evaluate_clip). `emission` est un tenseur torch (T, V) ; typé
    `Any` pour que ce module reste important sans torch au chargement."""
    decoded_text: str
    emission: Any
    duration: float
    frame_s: float


class Wav2Vec2Aligner:
    """Alignement forcé CTC sur CPU (transformers + torchaudio).

    Imports paresseux dans align() : le module reste importable sans torch.
    """

    def __init__(self, model_id: str = DEFAULT_MODEL, device: str = "cpu"):
        self.model_id = model_id
        self.device = device
        self.name = f"wav2vec2:{model_id}"
        self._model = None
        self._processor = None

    def _load(self):
        if self._model is not None:
            return
        from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor
        self._processor = Wav2Vec2Processor.from_pretrained(self.model_id)
        self._model = Wav2Vec2ForCTC.from_pretrained(self.model_id).to(self.device)
        self._model.eval()

    def _load_audio(self, audio_path: Path):
        import torch
        import torchaudio
        try:
            wav, sr = torchaudio.load(str(audio_path))   # (canaux, T)
        except Exception:                                 # backend mp3 indispo → soundfile
            import soundfile as sf
            data, sr = sf.read(str(audio_path), dtype="float32", always_2d=True)
            wav = torch.from_numpy(data.T)                # (canaux, T)
        if wav.shape[0] > 1:                              # stéréo → mono
            wav = wav.mean(dim=0, keepdim=True)
        if sr != 16000:
            wav = torchaudio.functional.resample(wav, sr, 16000)
            sr = 16000
        return wav.squeeze(0), sr

    def decode(self, audio_path: Path) -> DecodeResult:
        """UNE passe modèle : logits + décodage CTC glouton. Ne dépend d'AUCUN
        texte attendu — `align_from_decode()` peut ensuite forcer-aligner ce
        MÊME résultat contre n'importe quel texte, y compris plusieurs fois de
        suite contre des textes différents, sans repasser le modèle."""
        import torch
        self._load()
        wav, sr = self._load_audio(Path(audio_path))
        duration = wav.numel() / sr

        with torch.inference_mode():
            inputs = self._processor(wav.numpy(), sampling_rate=sr,
                                     return_tensors="pt").input_values.to(self.device)
            logits = self._model(inputs).logits[0]            # (T, V)
            emission = torch.log_softmax(logits, dim=-1)

        # Décodage CTC glouton (Roadmap V2 Phase 0 — vérif. de contenu) : mêmes
        # logits que forced_align, AUCUN coût supplémentaire (pas de 2e passe
        # modèle). tok.decode() fait le collapse CTC standard (fusionne les
        # répétitions, retire blank/pad) -> une transcription brute de CE QUI a
        # été dit, indépendante du texte attendu (contrairement à forced_align).
        tok = self._processor.tokenizer
        pred_ids = torch.argmax(logits, dim=-1).tolist()
        decoded_text = tok.decode(pred_ids)
        n_frames = emission.shape[0]
        frame_s = duration / n_frames
        return DecodeResult(decoded_text=decoded_text, emission=emission,
                            duration=duration, frame_s=frame_s)

    def align_from_decode(self, decoded: DecodeResult, text: str) -> Alignment:
        """Force-aligne un `DecodeResult` DÉJÀ CALCULÉ contre `text` — pas de
        nouvelle passe modèle. C'est ce qui rend `evaluate_clip` efficace :
        décoder UNE fois, puis forcer-aligner seulement contre le petit texte
        de l'ayah/la plage identifiée, jamais contre toute une longue sourate."""
        import torch
        from torchaudio.functional import forced_align
        tok = self._processor.tokenizer
        blank = tok.pad_token_id if tok.pad_token_id is not None else 0
        toks, idx = text_to_tokens(text)
        tok2id = tok.get_vocab()
        unk = tok2id.get(tok.unk_token, blank)
        # `targets` doit vivre sur le MÊME device que l'émission : le noyau CUDA
        # de forced_align refuse un mélange CPU/GPU ("targets must be a CUDA
        # tensor"). Sans ce .to(), le moteur ne tourne que sur CPU.
        targets = torch.tensor([[tok2id.get(t, unk) for t in toks]],
                               dtype=torch.int32, device=decoded.emission.device)

        aligned, _scores = forced_align(decoded.emission.unsqueeze(0), targets, blank=blank)
        aligned = aligned[0].tolist()
        n_frames = decoded.emission.shape[0]
        frame_s = decoded.frame_s

        # CTC émet chaque jeton comme un PIC bref ; la durée TENUE (madd) vit dans
        # les frames blank qui suivent. On mesure donc chaque jeton de son onset à
        # l'onset du SUIVANT (intervalle inter-onset) → la voyelle tenue est bien
        # attribuée à la lettre tenue. (Les répétitions sont séparées par un blank
        # obligatoire dans un chemin CTC valide, donc l'onset est bien détecté.)
        onsets: List[int] = []
        prev = blank
        for f, lab in enumerate(aligned):
            if lab != blank and lab != prev:
                onsets.append(f)
            prev = lab

        spans: List[Optional[Tuple[float, float]]] = [None] * len(toks)
        for i in range(min(len(onsets), len(toks))):
            start = onsets[i]
            end = onsets[i + 1] if i + 1 < len(onsets) else n_frames
            spans[i] = (start * frame_s, end * frame_s)
        return _spans_to_alignment(text, idx, spans, decoded.duration,
                                   decoded_text=decoded.decoded_text)

    def align(self, audio_path: Path, text: str) -> Alignment:
        """Compat : decode() + align_from_decode() en un appel (une seule
        passe modèle, comme avant) — utilisé par evaluate()/evaluate_window()."""
        return self.align_from_decode(self.decode(Path(audio_path)), text)
