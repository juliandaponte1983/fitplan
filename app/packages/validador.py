"""Validador del plan semanal (reglas V1–V15 del README).

No se fía del 'autochequeo' del LLM: recalcula todo a partir del paquete.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from jsonschema import Draft202012Validator

from app.engine.alimentos import Diccionario, norm

RAIZ = Path(__file__).resolve().parents[2]
_V_PLAN = Draft202012Validator(json.loads((RAIZ / "schemas" / "plan_semanal.schema.json").read_text(encoding="utf-8")))
CARDIO = {"cinta", "carrera_exterior", "bici_indoor", "remo", "eliptica", "hiit", "caminar"}
DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]


@dataclass
class Hallazgo:
    regla: str
    severidad: str   # bloqueo | aviso
    mensaje: str


def _min(h: str) -> int:
    hh, mm = h.split(":")
    return int(hh) * 60 + int(mm)


def _macros_items(comida: dict, recetas: dict) -> dict:
    tot = {"kcal": 0.0, "proteina_g": 0.0, "carbohidratos_g": 0.0, "grasa_g": 0.0, "fibra_g": 0.0}
    for it in comida["items"]:
        if it.get("receta_id") in recetas and "macros" not in it:
            m = {k: v * it["raciones"] for k, v in recetas[it["receta_id"]]["macros_racion"].items()}
        else:
            m = it.get("macros", {})
        for k in tot:
            tot[k] += m.get(k, 0) or 0
    return tot


def validar(plan: dict, paquete: dict, dic: Diccionario | None = None) -> list[Hallazgo]:
    H: list[Hallazgo] = []
    B = lambda r, m: H.append(Hallazgo(r, "bloqueo", m))
    A = lambda r, m: H.append(Hallazgo(r, "aviso", m))

    # V1 esquema
    for e in _V_PLAN.iter_errors(plan):
        B("V1", f"/{'/'.join(map(str, e.path))}: {e.message}")
    if H:
        return H

    # V2 identidad
    if plan["paquete_id"] != paquete["paquete_id"]:
        B("V2", "paquete_id no coincide con el paquete exportado")
    if plan["semana_inicio"] != paquete["semana"]["inicio"]:
        B("V2", f"semana_inicio {plan['semana_inicio']} ≠ {paquete['semana']['inicio']}")

    cat = {e["exercise_template_id"]: e for e in paquete["catalogo_ejercicios"]}
    restr = paquete["restricciones"]
    prohibidos_ej = {a for r in restr["ejercicio"] if r["nivel"] == "prohibido" for a in r["ambito"]}
    rutinas = {r["id"]: r for r in plan["entrenamiento"]["rutinas"]}

    # V3 / V4 ejercicios
    for r in rutinas.values():
        for ej in r["ejercicios"]:
            tid = ej["exercise_template_id"]
            if tid not in cat:
                B("V3", f"{r['titulo']}: '{ej['nombre']}' ({tid}) no está en el catálogo permitido")
            elif prohibidos_ej & set(cat[tid]["patrones"]):
                B("V4", f"{ej['nombre']}: patrón prohibido {sorted(prohibidos_ej & set(cat[tid]['patrones']))}")

    # V5 / V6 alimentos
    dic = dic or Diccionario()
    proh_dieta = [r["alimento_o_grupo"] for r in restr["dieta"] if r["nivel"] == "prohibido"]
    recetas = {r["id"]: r for r in plan["nutricion"]["recetas"]}
    alimentos = [(f"receta {r['id']} ({r['nombre']})", i["alimento"]) for r in recetas.values() for i in r["ingredientes"]]
    alimentos += [(f"{d['fecha']} {c['comida']}", it["alimento"]) for d in plan["nutricion"]["dias"]
                  for c in d["comidas"] for it in c["items"] if it.get("alimento")]
    for donde, al in alimentos:
        for h in dic.comprobar([al], proh_dieta):
            B("V5", f"{donde}: '{al}' contiene '{h['termino']}' (restricción prohibida: {h['restriccion']})")
    for r in recetas.values():
        for alergeno in r["alergenos"]:
            for rp in proh_dieta:
                if alergeno in dic.resolver(rp):
                    B("V5", f"receta {r['id']} declara alérgeno '{alergeno}' prohibido ({rp})")
    evitar = {norm(x["alimento_o_grupo"]) for x in plan["nutricion"]["alimentos_evitar"]}
    for rp in proh_dieta:
        if norm(rp) not in evitar:
            B("V6", f"'{rp}' (prohibido) no aparece en alimentos_evitar")
    for d in plan["nutricion"]["dias"]:
        for c in d["comidas"]:
            for it in c["items"]:
                if it.get("receta_id") and it["receta_id"] not in recetas:
                    B("V9", f"{d['fecha']} {c['comida']}: receta {it['receta_id']} no definida")

    # V7 / V8 / V9 / V10 nutrición diaria
    on = paquete["objetivos"]["nutricion"]
    tol = on.get("tolerancia_kcal_pct", 5) / 100
    dias_entreno = {d["fecha"] for d in plan["entrenamiento"]["dias"] if d["sesiones"]}
    for d in plan["nutricion"]["dias"]:
        esperado = "entreno" if d["fecha"] in dias_entreno else "descanso"
        if d["tipo_dia"] != esperado:
            A("V7", f"{d['fecha']}: tipo_dia '{d['tipo_dia']}' pero el entreno dice '{esperado}'")
        obj = on["kcal_entreno"] if d["tipo_dia"] == "entreno" else on["kcal_descanso"]
        suma = {"kcal": 0.0, "proteina_g": 0.0, "carbohidratos_g": 0.0, "grasa_g": 0.0, "fibra_g": 0.0}
        for c in d["comidas"]:
            for k, v in _macros_items(c, recetas).items():
                suma[k] += v
        t = d["totales"]
        if abs(suma["kcal"] - t["kcal"]) > max(t["kcal"] * 0.02, 10):
            B("V9", f"{d['fecha']}: totales {t['kcal']:.0f} kcal ≠ suma de comidas {suma['kcal']:.0f}")
        kcal = suma["kcal"]
        if abs(kcal - obj) > obj * tol:
            B("V7", f"{d['fecha']}: {kcal:.0f} kcal fuera de {obj} ±{tol:.0%}")
        if suma["proteina_g"] < on["proteina_g"] * 0.95:
            B("V8", f"{d['fecha']}: proteína {suma['proteina_g']:.0f} g < {on['proteina_g']} g")
        if suma["grasa_g"] < on["grasa_g_min"]:
            B("V8", f"{d['fecha']}: grasa {suma['grasa_g']:.0f} g < mínimo {on['grasa_g_min']} g")
        if suma["fibra_g"] and suma["fibra_g"] < on["fibra_g_min"]:
            B("V8", f"{d['fecha']}: fibra {suma['fibra_g']:.0f} g < mínimo {on['fibra_g_min']} g")
        elif not suma["fibra_g"]:
            A("V8", f"{d['fecha']}: sin datos de fibra")
        atw = 4 * suma["proteina_g"] + 4 * suma["carbohidratos_g"] + 9 * suma["grasa_g"]
        if kcal and abs(atw - kcal) > kcal * 0.08:
            A("V10", f"{d['fecha']}: 4P+4C+9G = {atw:.0f} ≠ {kcal:.0f} kcal")
    for r in recetas.values():
        m = r["macros_racion"]
        atw = 4 * m["proteina_g"] + 4 * m["carbohidratos_g"] + 9 * m["grasa_g"]
        if m["kcal"] and abs(atw - m["kcal"]) > m["kcal"] * 0.08:
            A("V10", f"receta {r['id']}: 4P+4C+9G = {atw:.0f} ≠ {m['kcal']:.0f} kcal")
    A("V9", "comprobación receta ↔ ingredientes pendiente de la base nutricional (BEDCA)")

    # V11 progresiones prescritas
    prog = {p["exercise_template_id"]: p for p in paquete["objetivos"]["entreno"]["progresiones"]}
    for r in rutinas.values():
        for ej in r["ejercicios"]:
            p = prog.get(ej["exercise_template_id"])
            if not p:
                continue
            normales = [s for s in ej["series"] if s["tipo"] == "normal"]
            if len(normales) != p["series"]:
                B("V11", f"{ej['nombre']}: {len(normales)} series de trabajo, prescritas {p['series']}")
            for s in normales:
                if p["peso_kg"] is not None and s.get("peso_kg") is not None and abs(s["peso_kg"] - p["peso_kg"]) > 0.01:
                    B("V11", f"{ej['nombre']}: {s['peso_kg']} kg, prescrito {p['peso_kg']} kg")
                rr = s.get("reps_rango") or ([s["reps"], s["reps"]] if s.get("reps") else None)
                if rr and (rr[0] < p["reps_min"] or rr[1] > p["reps_max"]):
                    B("V11", f"{ej['nombre']}: rango {rr} fuera de {p['reps_min']}-{p['reps_max']}")

    # V12 volumen semanal
    oe = paquete["objetivos"]["entreno"]
    ses = [(d, s) for d in plan["entrenamiento"]["dias"] for s in d["sesiones"]]
    n_f = sum(s["tipo"] == "fuerza" for _, s in ses)
    n_c = sum(s["tipo"] in CARDIO for _, s in ses)
    if n_f != oe["sesiones_fuerza"]:
        B("V12", f"{n_f} sesiones de fuerza, objetivo {oe['sesiones_fuerza']}")
    if n_c != oe["sesiones_cardio"]:
        B("V12", f"{n_c} sesiones de cardio, objetivo {oe['sesiones_cardio']}")
    usar_rpe = bool(restr.get("limites", {}).get("usar_rpe_en_lugar_de_fc"))
    z2 = alta = 0.0
    for _, s in ses:
        for b in s.get("bloques_cardio", []):
            mins = b["duracion_min"] * b.get("repeticiones", 1)
            it = b["intensidad"]
            if it.get("zona") == "Z2" or (usar_rpe and it.get("rpe") in (3, 4)):
                z2 += mins
            if it.get("zona") in ("Z4", "Z5") or (it.get("rpe") or 0) >= 8:
                alta += mins
        if s["tipo"] == "fuerza" and s.get("rutina_ref") not in rutinas:
            B("V12", f"sesión de fuerza sin rutina válida (rutina_ref={s.get('rutina_ref')})")
        if s["tipo"] in CARDIO and not s.get("bloques_cardio"):
            B("V12", f"sesión de {s['tipo']} sin bloques de cardio")
    if z2 < oe["min_z2_semana"] * 0.9:
        B("V12", f"{z2:.0f} min en Z2, objetivo {oe['min_z2_semana']}")
    if oe.get("min_alta_intensidad_max") is not None and alta > oe["min_alta_intensidad_max"]:
        B("V12", f"{alta:.0f} min de alta intensidad, máximo {oe['min_alta_intensidad_max']}")
    descanso = sum(not d["sesiones"] for d in plan["entrenamiento"]["dias"])
    if descanso < oe["dias_descanso_min"]:
        B("V12", f"{descanso} días de descanso, mínimo {oe['dias_descanso_min']}")

    # V13 horarios
    disp = paquete["perfil"]["disponibilidad"]
    for d, s in ses:
        ok = any(x["dia"] == d["dia"] and _min(x["desde"]) <= _min(s["hora"]) and _min(s["hora"]) + s["duracion_min"] <= _min(x["hasta"]) + 15
                 for x in disp)
        if not ok:
            A("V13", f"{d['dia']} {s['hora']} {s['tipo']} ({s['duracion_min']} min) fuera de tu disponibilidad")
    horario = {h["comida"]: _min(h["hora"]) for h in paquete["perfil"]["horario_comidas"]}
    for d in plan["nutricion"]["dias"]:
        for c in d["comidas"]:
            if c["comida"] in horario and abs(_min(c["hora"]) - horario[c["comida"]]) > 60:
                A("V13", f"{d['fecha']} {c['comida']} a las {c['hora']} (habitual {divmod(horario[c['comida']], 60)[0]:02d}:{horario[c['comida']] % 60:02d})")

    # V14 FC / RPE
    lim = restr.get("limites", {})
    for d, s in ses:
        for b in s.get("bloques_cardio", []):
            if usar_rpe and b["intensidad"].get("zona"):
                B("V14", f"{d['fecha']} {s['tipo']}: usa zonas de FC pero debe prescribirse por RPE")
            if lim.get("rpe_max") and (b["intensidad"].get("rpe") or 0) > lim["rpe_max"]:
                B("V14", f"{d['fecha']} {s['tipo']}: RPE {b['intensidad']['rpe']} > máximo {lim['rpe_max']}")
    if lim.get("rpe_max"):
        for r in rutinas.values():
            for ej in r["ejercicios"]:
                for s in ej["series"]:
                    if (s.get("rpe_objetivo") or 0) > lim["rpe_max"]:
                        B("V14", f"{ej['nombre']}: RPE {s['rpe_objetivo']} > máximo {lim['rpe_max']}")

    # V15 lista de la compra
    lista = {norm(x["alimento"]) for x in plan["nutricion"]["lista_compra"]}
    faltan = sorted({i["alimento"] for r in recetas.values() for i in r["ingredientes"] if norm(i["alimento"]) not in lista})
    if faltan:
        A("V15", f"no están en la lista de la compra: {', '.join(faltan[:10])}{'…' if len(faltan) > 10 else ''}")
    return H


def resumen(h: list[Hallazgo]) -> dict:
    return {"bloqueos": sum(x.severidad == "bloqueo" for x in h), "avisos": sum(x.severidad == "aviso" for x in h),
            "hallazgos": [asdict(x) for x in h]}
