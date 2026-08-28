# -*- coding: utf-8 -*-
"""
src/tajweed/config.py — Configuration & secrets du pipeline.

Charge le fichier .env (à la racine du repo) si python-dotenv est présent, puis
expose les identifiants Supabase. Centralise la lecture des secrets pour qu'AUCUN
identifiant ne soit codé en dur dans le code (cf. le token HF historiquement en
clair dans Data/download_data.py — à proscrire).

Usage :
    from .config import supabase_credentials
    url, key = supabase_credentials()
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple

# Racine du repo : src/tajweed/config.py -> parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"

_loaded = False


def load_env() -> None:
    """Charge .env une seule fois (idempotent). No-op si python-dotenv absent.

    Les variables déjà définies dans l'environnement ne sont PAS écrasées
    (override=False) : l'environnement réel prime sur le fichier .env.
    """
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        from dotenv import load_dotenv
    except ImportError:
        return  # pas de dotenv : on se rabat sur les variables d'environnement
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH, override=False)
    else:
        load_dotenv(override=False)  # cherche un .env dans le cwd, le cas échéant


def get(name: str, default: str | None = None) -> str | None:
    load_env()
    return os.environ.get(name, default)


def require(name: str) -> str:
    val = get(name)
    if not val:
        raise SystemExit(
            f"Variable d'environnement manquante : {name}. "
            f"Définis-la dans {ENV_PATH} (voir .env.example.txt) ou dans ton shell."
        )
    return val


def supabase_credentials() -> Tuple[str, str]:
    """(SUPABASE_URL, SUPABASE_KEY). Lève une erreur claire si absent."""
    return require("SUPABASE_URL"), require("SUPABASE_KEY")
