# -*- coding: utf-8 -*-
"""Moteur de correction Tajweed (offline/batch) — v1 : Madd + Ghunnah.

Cœur déterministe (types, ground_truth, rules, evaluate) importable sans torch.
Le back-end wav2vec2 (aligner.Wav2Vec2Aligner) charge torch paresseusement.
"""

from .types import Alignment, SegmentResult, Report
from .ground_truth import GroundTruth, GTSegment, LocalGroundTruth, SupabaseGroundTruth
from .rules import measure_all, measure_segment, estimate_haraka_unit
from .evaluate import evaluate
from .calibrate import summarize_samples, collect as collect_calibration

__all__ = [
    "Alignment", "SegmentResult", "Report",
    "GroundTruth", "GTSegment", "LocalGroundTruth", "SupabaseGroundTruth",
    "measure_all", "measure_segment", "estimate_haraka_unit", "evaluate",
    "summarize_samples", "collect_calibration",
]
