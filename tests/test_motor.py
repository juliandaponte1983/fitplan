from datetime import date, datetime, timedelta

import pytest

from app.engine import carga, composicion, fuerza, nutricion


def test_trimp_banister_valores_razonables():
    fc = [(i, 150) for i in range(0, 1801, 5)]          # 30 min a 150 ppm
    t = carga.trimp_banister(fc, 60, 184, "H")
    assert 50 < t < 70
    assert carga.trimp_banister(fc, 60, 184, "M") != t
    assert carga.trimp_banister([(0, 150), (300, 150)], 60, 184) == 0  # hueco > 60 s no cuenta


def test_acwr():
    hoy = date(2026, 9, 27)
    diaria = {hoy - timedelta(days=d): 50.0 for d in range(0, 28, 2)}   # 14 sesiones en 28 días
    r = carga.acwr(diaria, hoy)
    assert r["aguda_7d"] == 200 and r["cronica_semanal_28d"] == 175 and r["acwr"] == 1.14
    assert carga.acwr({}, hoy)["acwr"] is None


def test_e1rm():
    assert fuerza.e1rm(100, 1) == pytest.approx(103.3, 0.01)
    assert fuerza.e1rm(50, 20) == fuerza.e1rm(50, 12)
    assert fuerza.e1rm(None, 10) is None


def _hist(ej, sesiones):
    base = datetime(2026, 7, 1)
    filas = [((base + timedelta(days=7 * i)).isoformat(), ej, "normal", p, r, None)
             for i, ses in enumerate(sesiones) for p, r in ses]
    return fuerza.historiales(filas)[ej]


def test_doble_progresion_sube_peso_al_llegar_al_tope():
    h = _hist("Bench Press (Barbell)", [[(50, 12)] * 3])
    p = fuerza.prescribir(h, "acumulacion")
    assert (p.motivo, p.peso_kg, p.reps_min, p.reps_max) == ("subir_peso", 52.5, 8, 12)


def test_doble_progresion_bloqueada_por_carga():
    h = _hist("Bench Press (Barbell)", [[(50, 12)] * 3])
    assert fuerza.prescribir(h, "acumulacion", permitir_subir_peso=False).peso_kg == 50


def test_subir_reps_y_bajar_si_falla_dos_veces():
    assert fuerza.prescribir(_hist("Bench Press (Barbell)", [[(50, 10)] * 3]), "acumulacion").motivo == "subir_reps"
    p = fuerza.prescribir(_hist("Bench Press (Barbell)", [[(60, 7)] * 3, [(60, 6)] * 3, [(60, 12)], [(60, 6)] * 3, [(60, 7)] * 3]), "acumulacion", rango=(8, 12))
    assert p.motivo == "mantener" and p.peso_kg == 57.5


def test_reintroduccion_baja_al_90():
    p = fuerza.prescribir(_hist("Squat (Barbell)", [[(50, 10)] * 3]), "reintroduccion")
    assert p.motivo == "descarga" and p.peso_kg == 45


def test_peso_trabajo_y_rango_habitual():
    h = _hist("Bent Over Row (Dumbbell)", [[(40, 8)] * 4])
    p = fuerza.prescribir(h, "acumulacion")
    assert (p.reps_min, p.reps_max) == (6, 10) and p.peso_kg == 40
    assert fuerza.peso_trabajo(_hist("Bicep Curl (Barbell)", [[(30, 10), (30, 10), (35, 10)]]).sesiones[-1]) == 30


def test_estancado():
    h = _hist("Chest Fly (Dumbbell)", [[(24, 12)]] * 10)
    assert h.estancado()
    assert not _hist("Chest Fly (Dumbbell)", [[(20 + i, 12)] for i in range(10)]).estancado()


def test_pendiente_semanal():
    d0 = datetime(2026, 9, 1)
    pts = [(d0 + timedelta(days=i), 84 - 0.1 * i) for i in range(0, 22, 7)]
    assert composicion.pendiente_semanal(pts) == -0.7
    assert composicion.pendiente_semanal(pts[:1]) is None


def test_nutricion_respeta_suelos_y_ajusta_por_tendencia():
    o = nutricion.objetivos(84.2, 169, 43, "H", "perder_grasa", 58.9, 60)
    assert o.kcal_descanso >= 1642 and o.proteina_g == 135 and o.grasa_g_min == 67
    lenta = nutricion.objetivos(84.2, 169, 43, "H", "perder_grasa", 58.9, 60, tendencia_kg_sem=0.0)
    assert lenta.kcal_entreno < o.kcal_entreno and "más lenta" in lenta.base_calculo
    lim = nutricion.objetivos(84.2, 169, 43, "H", "perder_grasa", 58.9, 60, limites={"proteina_max_g_kg": 1.2})
    assert lim.proteina_g <= 101
