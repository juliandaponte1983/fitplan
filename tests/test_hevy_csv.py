from datetime import datetime
from pathlib import Path

import pytest

from app.parsers import hevy_csv

FIX = Path(__file__).parent / "fixtures" / "hevy_mini.csv"


@pytest.mark.parametrize("texto,esperado", [
    ("25 sept 2026, 7:04", datetime(2026, 9, 25, 7, 4)),
    ("1 abr 2026, 17:30", datetime(2026, 4, 1, 17, 30)),
    ("25 Sep 2026, 07:04", datetime(2026, 9, 25, 7, 4)),
    ("3 dic. 2025, 21:17", datetime(2025, 12, 3, 21, 17)),
])
def test_parse_fecha(texto, esperado):
    assert hevy_csv.parse_fecha(texto) == esperado


def test_leer_agrupa_y_reporta_errores():
    r = hevy_csv.leer(FIX)
    assert len(r.series) == 6
    assert len(r.entrenos) == 2
    assert len(r.errores) == 1 and "línea 8" in r.errores[0]
    pecho = r.entrenos[0]
    assert pecho.duracion_min == 55
    assert pecho.volumen_kg == 30 * 10 + 50 * 10 + 45 * 12
    assert r.series[1].rpe == 8 and r.series[0].tipo == "warmup"
    assert r.entrenos[1].series[0].peso_kg is None and r.entrenos[1].series[0].superset_id == 1


def test_mismo_ejercicio_dos_veces_tiene_claves_distintas():
    r = hevy_csv.leer(FIX)
    claves = [s.clave for s in r.series]
    assert len(claves) == len(set(claves))
    banca = [s for s in r.entrenos[0].series if s.ejercicio == "Bench Press (Barbell)"]
    assert [s.ejercicio_orden for s in banca] == [1, 1, 3]


def test_nuevas_devuelve_solo_la_diferencia():
    r = hevy_csv.leer(FIX)
    ya = {s.clave for s in r.series[:4]}
    assert [s.clave for s in hevy_csv.nuevas(r, ya)] == [s.clave for s in r.series[4:]]


def test_columnas_obligatorias():
    with pytest.raises(ValueError, match="sin columnas"):
        hevy_csv.leer(b"title,start_time\nx,y\n")
