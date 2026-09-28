"""Tests del lector FIT.

Los tests de integración usan tus FIT reales de ../datos/<perfil>/garmin_fit si existen
(o la ruta de la variable FITPLAN_FIT_DIR). Los FIT no se suben al repo porque pueden
contener tu ubicación GPS.
"""
import os
from pathlib import Path

import pytest

from app.parsers import garmin_fit as g

DIR = Path(os.environ.get("FITPLAN_FIT_DIR", Path(__file__).parents[2] / "datos" / "julian" / "garmin_fit"))
FITS = sorted(DIR.glob("*.zip")) + sorted(DIR.glob("*.fit")) if DIR.exists() else []
requiere_fits = pytest.mark.skipif(not FITS, reason=f"sin FIT reales en {DIR}")


@pytest.mark.parametrize("sport,sub,esperado", [
    ("running", "treadmill", "cinta"),
    ("running", "generic", "carrera_exterior"),
    ("training", "strength_training", "fuerza"),
    ("rowing", "indoor_rowing", "remo"),
    ("cycling", "indoor_cycling", "bici_indoor"),
    ("training", "cardio_training", "cardio"),
    ("walking", "casual_walking", "caminar"),
    ("sailing", None, "otro"),
])
def test_tipo_actividad(sport, sub, esperado):
    assert g.tipo_actividad(sport, sub) == esperado


def test_zip_invalido():
    with pytest.raises(Exception):
        g.leer(b"PK\x03\x04no-es-un-zip")


@requiere_fits
def test_todos_los_fit_se_leen_con_claves_unicas():
    acts = [g.leer(p) for p in FITS]
    assert len({a.clave for a in acts}) == len(acts)
    for a in acts:
        assert a.duracion_s > 0 and a.inicio is not None
        assert a.tipo != "otro", f"{a.garmin_id}: {a.sport}/{a.sub_sport} sin mapear"
        if a.zonas_s:
            assert abs(sum(a.zonas_s.values()) - a.duracion_s) < a.duracion_s * 0.1


@requiere_fits
def test_fuerza_tiene_series_y_carrera_tiene_ritmo():
    acts = [g.leer(p) for p in FITS]
    fuerza = [a for a in acts if a.tipo == "fuerza"]
    carrera = [a for a in acts if a.tipo in ("cinta", "carrera_exterior")]
    assert fuerza and all(a.series for a in fuerza)
    assert carrera and all(a.ritmo_min_km for a in carrera)
