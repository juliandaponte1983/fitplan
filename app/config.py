"""Rutas y ajustes. Los datos viven FUERA del repo y fuera de OneDrive."""
from __future__ import annotations

import os
from pathlib import Path

HOME_APP = Path(os.environ.get("FITPLAN_HOME", Path.home() / "Library" / "Application Support" / "FitPlan"))
DB_PATH = Path(os.environ.get("FITPLAN_DB", HOME_APP / "fitplan.db"))
ZONA_HORARIA = os.environ.get("FITPLAN_TZ", "Europe/Madrid")
DATOS_DIR = Path(os.environ.get("FITPLAN_DATOS", Path(__file__).resolve().parents[2] / "datos"))  # fitplan/../datos


def carpeta_perfil(alias: str) -> Path:
    return DATOS_DIR / alias
