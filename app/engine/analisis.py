"""Orquestador del motor: lee la BD de un perfil y calcula el estado para una semana."""
from __future__ import annotations

import json
import sqlite3
from collections import Counter
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.engine import carga, composicion, fuerza, nutricion

AJUSTES_DEFECTO = {"objetivo": "recomposicion", "nivel": "intermedio", "fc_reposo": 60,
                   "fc_max": None, "factor_neat": 1.35}


def ajustes(conn: sqlite3.Connection, pid: int) -> dict:
    fila = conn.execute("SELECT ajustes_json FROM perfil WHERE id=?", (pid,)).fetchone()
    return {**AJUSTES_DEFECTO, **json.loads(fila[0] or "{}")}


def guardar_ajustes(conn: sqlite3.Connection, pid: int, **cambios) -> dict:
    a = {**json.loads(conn.execute("SELECT ajustes_json FROM perfil WHERE id=?", (pid,)).fetchone()[0] or "{}"),
         **{k: v for k, v in cambios.items() if v is not None}}
    with conn:
        conn.execute("UPDATE perfil SET ajustes_json=? WHERE id=?", (json.dumps(a), pid))
    return {**AJUSTES_DEFECTO, **a}


def _edad(nac: str | None, hoy: date) -> int | None:
    if not nac:
        return None
    n = date.fromisoformat(nac)
    return hoy.year - n.year - ((hoy.month, hoy.day) < (n.month, n.day))


def lunes(d: date) -> date:
    return d - timedelta(days=d.weekday())


def analizar(conn: sqlite3.Connection, pid: int, semana_inicio: date | None = None) -> dict:
    p = conn.execute("SELECT * FROM perfil WHERE id=?", (pid,)).fetchone()
    tz = ZoneInfo(p["zona_horaria"])
    aj = ajustes(conn, pid)
    if aj.get("fc_reposo_garmin") and not json.loads(conn.execute("SELECT ajustes_json FROM perfil WHERE id=?", (pid,)).fetchone()[0] or "{}").get("fc_reposo"):
        aj["fc_reposo"] = aj["fc_reposo_garmin"]
    semana_inicio = semana_inicio or lunes(datetime.now(tz).date() + timedelta(days=7 if datetime.now(tz).weekday() >= 5 else 0))
    hoy = semana_inicio - timedelta(days=1)                 # se analiza hasta el domingo previo
    ini_prev = semana_inicio - timedelta(days=7)
    edad = _edad(p["fecha_nacimiento"], semana_inicio)
    local = lambda iso: datetime.fromisoformat(iso).astimezone(tz)

    # ---------------- actividades Garmin: TRIMP y zonas
    acts = conn.execute("SELECT * FROM actividad WHERE perfil_id=? AND inicio_utc < ? ORDER BY inicio_utc",
                        (pid, datetime.combine(semana_inicio, datetime.min.time(), tz).astimezone(timezone.utc).isoformat())).fetchall()
    fc_max = aj["fc_max"] or next((a["fc_max_config"] for a in reversed(acts) if a["fc_max_config"]), None) or (220 - (edad or 40))
    cargas, sesiones_prev, zonas_prev = [], [], Counter()
    for a in acts:
        d = local(a["inicio_utc"]).date()
        fc = json.loads(a["fc_json"] or "[]")
        t = carga.trimp_banister(fc, aj["fc_reposo"], fc_max, p["sexo"] or "H") if fc else carga.trimp_desde_zonas(json.loads(a["zonas_json"] or "{}"))
        cargas.append((d, t))
        if ini_prev <= d <= hoy:
            sesiones_prev.append({"fecha": d.isoformat(), "tipo": a["tipo"], "duracion_min": round(a["duracion_s"] / 60),
                                  "fc_media": a["fc_media"], "distancia_km": a["distancia_km"], "rpe": None, "trimp": t})
            for z, s in json.loads(a["zonas_json"] or "{}").items():
                zonas_prev[z.upper()] += s / 60
    diaria = carga.carga_diaria(cargas)
    estado_carga = carga.acwr(diaria, hoy)

    # ---------------- Hevy: fuerza
    filas = conn.execute(
        """SELECT e.inicio_utc, s.ejercicio, s.tipo, s.peso_kg, s.reps, s.rpe FROM hevy_serie s
           JOIN hevy_entreno e ON e.id = s.entreno_id WHERE s.perfil_id=? AND e.inicio_utc < ?
           ORDER BY e.inicio_utc, s.ejercicio_orden, s.set_index""",
        (pid, datetime.combine(semana_inicio, datetime.min.time(), tz).astimezone(timezone.utc).isoformat())).fetchall()
    hist = fuerza.historiales(filas)
    entrenos = conn.execute("SELECT inicio_utc, fin_utc, titulo FROM hevy_entreno WHERE perfil_id=? ORDER BY inicio_utc",
                            (pid,)).fetchall()
    fechas_entreno = sorted({local(e["inicio_utc"]).date() for e in entrenos} | {d for d, _ in cargas})
    fechas_entreno = [f for f in fechas_entreno if f <= hoy]
    ultimo = fechas_entreno[-1] if fechas_entreno else None
    dias_sin = (hoy - ultimo).days if ultimo else None
    huecos = [(b - a).days for a, b in zip(fechas_entreno, fechas_entreno[1:])]
    parada_reciente = any(h >= 14 for h in huecos[-6:]) if huecos else False
    fase = "reintroduccion" if (dias_sin is not None and dias_sin >= 14) or parada_reciente else "acumulacion"

    # ejercicios activos: los hechos en las últimas 8 semanas, por frecuencia
    corte = datetime.combine(hoy - timedelta(weeks=8), datetime.min.time(), timezone.utc)
    activos = [h for h in hist.values() if h.sesiones and h.sesiones[-1].fecha >= corte]
    activos.sort(key=lambda h: -len([s for s in h.sesiones if s.fecha >= corte]))
    estado_ok = estado_carga["acwr"] is None or estado_carga["acwr"] <= 1.5
    prescripciones = [fuerza.prescribir(h, fase, permitir_subir_peso=estado_ok) for h in activos]
    alertas = []
    if not estado_ok:
        alertas.append(f"ACWR {estado_carga['acwr']}: la carga de la última semana es alta respecto a tu base de 4 semanas; "
                       "esta semana no se sube peso, solo repeticiones")
    if parada_reciente or (dias_sin or 0) >= 14:
        alertas.append("parón de 14 días o más: el bloque empieza en reintroducción")
    progresion = []
    for h in activos:
        e = [s.mejor_e1rm for s in h.sesiones if s.mejor_e1rm]
        progresion.append({"ejercicio": h.ejercicio, "sesiones": len(h.sesiones), "e1rm_primero": e[0] if e else None,
                           "e1rm_ultimo": e[-1] if e else None, "e1rm_max": max(e) if e else None,
                           "estancado": h.estancado()})
    vol_prev = sum((pk or 0) * (r or 0) for ini, _, tp, pk, r, _ in filas
                   if tp != "warmup" and ini_prev <= local(ini).date() <= hoy)
    ses_fuerza_prev = len({local(e["inicio_utc"]).date() for e in entrenos if ini_prev <= local(e["inicio_utc"]).date() <= hoy})

    # ---------------- composición
    comps = conn.execute("SELECT fecha_hora, peso_kg, grasa_pct, musculo_esqueletico_kg, masa_magra_kg, tmb_kcal FROM composicion "
                         "WHERE perfil_id=? ORDER BY fecha_hora", (pid,)).fetchall()
    actual = dict(comps[-1]) if comps else None
    pts = lambda campo: [(datetime.fromisoformat(c["fecha_hora"]), c[campo]) for c in comps]
    tendencia = {"peso_kg_sem": composicion.pendiente_semanal(pts("peso_kg")),
                 "grasa_pct_sem": composicion.pendiente_semanal(pts("grasa_pct")),
                 "musculo_esqueletico_kg_sem": composicion.pendiente_semanal(pts("musculo_esqueletico_kg")),
                 "n_mediciones": len(comps)}

    # ---------------- nutrición
    obj_nut = None
    if actual and edad and p["altura_cm"]:
        base, _ = nutricion.tmb(actual["peso_kg"], p["altura_cm"], edad, p["sexo"] or "H", actual["masa_magra_kg"])
        activas = sum(max((a["kcal"] or 0) - (a["duracion_s"] / 60) * base / 1440, 0) for a in acts
                      if hoy - timedelta(days=27) <= local(a["inicio_utc"]).date() <= hoy)
        obj_nut = nutricion.objetivos(actual["peso_kg"], p["altura_cm"], edad, p["sexo"] or "H", aj["objetivo"],
                                      actual["masa_magra_kg"], activas / 28, aj["factor_neat"],
                                      tendencia["peso_kg_sem"], aj.get("limites"))

    # zonas FC (Garmin: % FCmáx)
    zonas_fc = {f"Z{i}": [round(fc_max * lo), round(fc_max * hi)] for i, (lo, hi) in
                enumerate([(0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.0)], start=1)}

    return {
        "semana": {"inicio": semana_inicio.isoformat(), "fin": (semana_inicio + timedelta(days=6)).isoformat(),
                   "fase_sugerida": fase, "dias_sin_entrenar": dias_sin, "parada_reciente_14d": parada_reciente},
        "perfil": {"alias": p["alias"], "sexo": p["sexo"], "edad": edad, "altura_cm": p["altura_cm"], **aj},
        "estado": {"composicion_actual": actual, "tendencia_4s": tendencia,
                   "cardio_referencia": {"fc_max_estimada": fc_max, "zonas_fc": zonas_fc}},
        "semana_anterior": {"sesiones_realizadas": len(sesiones_prev) + max(ses_fuerza_prev - sum(s["tipo"] == "fuerza" for s in sesiones_prev), 0),
                            "sesiones_fuerza": ses_fuerza_prev, "sesiones": sesiones_prev,
                            "carga": {"trimp_semana": round(sum(s["trimp"] for s in sesiones_prev), 1), **estado_carga,
                                      "volumen_fuerza_kg": vol_prev,
                                      "minutos_cardio": sum(s["duracion_min"] for s in sesiones_prev if s["tipo"] != "fuerza"),
                                      "minutos_por_zona": {k: round(v) for k, v in sorted(zonas_prev.items())}}},
        "alertas": alertas,
        "fuerza": {"prescripciones": [asdict(x) for x in prescripciones], "progresion": progresion},
        "nutricion": asdict(obj_nut) if obj_nut else None,
    }
