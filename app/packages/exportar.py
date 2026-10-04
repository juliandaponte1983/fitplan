"""Construye el paquete semanal (app → LLM) a partir del análisis del motor."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from app.engine import analisis as motor
from app.engine import catalogo
from app.ingesta import perfil_medico_vigente

RAIZ = Path(__file__).resolve().parents[2]
ESQ_PAQUETE = json.loads((RAIZ / "schemas" / "paquete_semanal.schema.json").read_text(encoding="utf-8"))
ESQ_PLAN = (RAIZ / "schemas" / "plan_semanal.schema.json").read_text(encoding="utf-8")
PLANTILLA = (RAIZ / "prompts" / "03_plan_semanal.md").read_text(encoding="utf-8")


def cargar_perfil_yaml(conn: sqlite3.Connection, pid: int, ruta: Path | str) -> dict:
    try:
        datos = yaml.safe_load(Path(ruta).read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        m = getattr(e, "problem_mark", None)
        donde = f" (línea {m.line + 1}, columna {m.column + 1})" if m else ""
        raise ValueError(f"{Path(ruta).name} no es YAML válido{donde}: {getattr(e, 'problem', e)}") from None
    for campo in ("objetivo", "disponibilidad", "material", "preferencias_alimentarias", "horario_comidas"):
        if campo not in (datos or {}):
            raise ValueError(f"{Path(ruta).name}: falta el campo '{campo}'")
    return motor.guardar_ajustes(conn, pid, objetivo=datos["objetivo"]["principal"], nivel=datos.get("nivel"),
                                 perfil_plan=datos)


def _objetivos_entreno(perfil_plan: dict, fase: str, acwr: float | None) -> dict:
    ses = perfil_plan.get("sesiones_semana", {"fuerza": 3, "cardio": 2})
    dias_disp = len({d["dia"] for d in perfil_plan.get("disponibilidad", [])}) or 5
    z2 = {"reintroduccion": 90, "descarga": 60}.get(fase, 150 if perfil_plan["objetivo"]["principal"] == "perder_grasa" else 120)
    z2 = min(z2, ses["cardio"] * 45 + ses["fuerza"] * 10)   # realista: ~45 min por sesión de cardio + 10 min de final Z2 en fuerza
    alta = 0 if fase in ("reintroduccion", "descarga") or (acwr or 0) > 1.5 else 20
    return {"sesiones_fuerza": ses["fuerza"], "sesiones_cardio": ses["cardio"], "min_z2_semana": z2,
            "min_alta_intensidad_max": alta, "dias_descanso_min": max(1, 7 - min(dias_disp, ses["fuerza"] + ses["cardio"])),
            "incremento_carga_max_pct": 0 if (acwr or 0) > 1.5 else 5}


def _restricciones(conn, pid, perfil_plan: dict) -> dict:
    pm = perfil_medico_vigente(conn, pid) or {}
    decl = perfil_plan.get("restricciones_declaradas", {})
    ej = [{k: r.get(k) for k in ("id", "nivel", "ambito", "descripcion", "limite")} for r in pm.get("restricciones_ejercicio", [])]
    for i, amb in enumerate(decl.get("ejercicio_evitar", []), start=1):
        ej.append({"id": f"REU{i}", "nivel": "prohibido", "ambito": [amb], "descripcion": f"declarado por el usuario: evitar {amb}", "limite": None})
    di = [{k: r.get(k) for k in ("id", "nivel", "alimento_o_grupo", "limite")} for r in pm.get("restricciones_dieta", [])]
    for a in pm.get("alergias_intolerancias", []):
        di.append({"id": f"RDA-{a['sustancia']}", "nivel": "prohibido" if a["tipo"] == "alergia" else "limitar",
                   "alimento_o_grupo": a["sustancia"].lower(), "limite": None})
    for i, x in enumerate(decl.get("alimentos_prohibidos", []), start=1):
        di.append({"id": f"RDU{i}", "nivel": "prohibido", "alimento_o_grupo": x.lower(), "limite": None})
    for i, x in enumerate(decl.get("alimentos_limitar", []), start=1):
        di.append({"id": f"RDL{i}", "nivel": "limitar", "alimento_o_grupo": x.lower(), "limite": None})
    return {"ejercicio": ej, "dieta": di, "limites": pm.get("limites", {}),
            "senales_alarma": pm.get("senales_alarma", ["Dolor u opresión en el pecho", "Mareo o desmayo durante el ejercicio"]),
            "requiere_valoracion_medica": bool(pm.get("requiere_valoracion_medica", {}).get("valor", False))}


def construir(conn: sqlite3.Connection, pid: int, semana_inicio: date, instrucciones: str = "") -> tuple[dict, list[str]]:
    """Devuelve (paquete, avisos). Lanza ValueError si falta información imprescindible."""
    a = motor.analizar(conn, pid, semana_inicio)
    aj = a["perfil"]
    pp = aj.get("perfil_plan")
    if not pp:
        raise ValueError("falta el perfil de plan: ejecuta 'perfil-cargar' con tu perfil.yaml")
    if not a["nutricion"] or not a["estado"]["composicion_actual"]:
        raise ValueError("faltan datos de composición corporal o de perfil (fecha de nacimiento, altura)")
    avisos = list(a["alertas"])
    restr = _restricciones(conn, pid, pp)
    if not perfil_medico_vigente(conn, pid):
        avisos.append("sin perfil médico: el plan solo respeta las restricciones que declaraste en perfil.yaml")
    prohibidos = {amb for r in restr["ejercicio"] if r["nivel"] == "prohibido" for amb in r["ambito"]}
    nombres = [r[0] for r in conn.execute("SELECT DISTINCT ejercicio FROM hevy_serie WHERE perfil_id=?", (pid,))]
    permitidos, excluidos = catalogo.construir(nombres, prohibidos)
    for e in excluidos:
        avisos.append(f"excluido del catálogo: {e['nombre']} ({', '.join(e['motivo'])})")
    ids_ok = {e["nombre"] for e in permitidos}

    fase = a["semana"]["fase_sugerida"]
    acwr = a["semana_anterior"]["carga"]["acwr"]
    obj_ent = _objetivos_entreno(pp, fase, acwr)
    obj_ent["progresiones"] = [
        {"exercise_template_id": f"hevy:{p['ejercicio']}", "nombre": p["ejercicio"], "series": p["series"],
         "reps_min": p["reps_min"], "reps_max": p["reps_max"], "peso_kg": p["peso_kg"], "rpe_objetivo": p["rpe_objetivo"],
         "motivo": p["motivo"], "historial": p["historial"]}
        for p in a["fuerza"]["prescripciones"] if p["ejercicio"] in ids_ok]
    n = a["nutricion"]
    obj_nut = {k: n[k] for k in ("kcal_entreno", "kcal_descanso", "proteina_g", "grasa_g_min", "carbohidratos_g_entreno",
                                 "carbohidratos_g_descanso", "fibra_g_min", "agua_ml", "tolerancia_kcal_pct", "base_calculo")}
    c = a["estado"]["composicion_actual"]
    prev = conn.execute("SELECT json FROM plan WHERE perfil_id=? AND estado='aceptado' AND semana_inicio=?",
                        (pid, (semana_inicio - timedelta(days=7)).isoformat())).fetchone()
    planificadas = sum(len(d["sesiones"]) for d in json.loads(prev[0])["entrenamiento"]["dias"]) if prev else 0
    sa = a["semana_anterior"]

    paquete = {
        "schema": "paquete_semanal/v1",
        "paquete_id": str(uuid.uuid4()),
        "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "semana": {"inicio": a["semana"]["inicio"], "fin": a["semana"]["fin"], "bloque": 1, "semana_en_bloque": 1, "fase": fase},
        "perfil": {"sexo": aj["sexo"], "edad": aj["edad"], "altura_cm": aj["altura_cm"],
                   "objetivo": {"principal": pp["objetivo"]["principal"], "secundarios": pp["objetivo"].get("secundarios", []),
                                "notas": pp["objetivo"].get("notas", "")},
                   "nivel": pp.get("nivel", "intermedio"), "disponibilidad": pp["disponibilidad"], "material": pp["material"],
                   "preferencias_alimentarias": pp["preferencias_alimentarias"], "horario_comidas": pp["horario_comidas"]},
        "restricciones": restr,
        "estado": {"composicion_actual": {"fecha": c["fecha_hora"][:10], "peso_kg": c["peso_kg"], "grasa_pct": c["grasa_pct"],
                                          "musculo_esqueletico_kg": c["musculo_esqueletico_kg"], "masa_magra_kg": c["masa_magra_kg"],
                                          "tmb_kcal": c["tmb_kcal"]},
                   "tendencia_4s": a["estado"]["tendencia_4s"], "recuperacion": None,
                   "cardio_referencia": {**a["estado"]["cardio_referencia"], "ritmo_z2_cinta_min_km": None, "ritmo_z2_exterior_min_km": None}},
        "semana_anterior": {"sesiones_planificadas": planificadas, "sesiones_realizadas": sa["sesiones_realizadas"],
                            "adherencia_nutricion_pct": None,
                            "carga": {k: sa["carga"][k] for k in ("trimp_semana", "acwr", "volumen_fuerza_kg", "minutos_cardio", "minutos_por_zona")},
                            "sesiones": [{k: s[k] for k in ("fecha", "tipo", "duracion_min", "fc_media", "distancia_km", "rpe")} for s in sa["sesiones"]],
                            "comentarios_usuario": pp.get("restricciones_declaradas", {}).get("molestias_actuales", "")},
        "objetivos": {"entreno": obj_ent, "nutricion": obj_nut},
        "catalogo_ejercicios": permitidos,
        "rutinas_hevy_actuales": [],
        "instrucciones_extra": instrucciones,
    }
    errores = [f"/{'/'.join(map(str, e.path))}: {e.message}" for e in Draft202012Validator(ESQ_PAQUETE).iter_errors(paquete)]
    if errores:
        raise ValueError("el paquete generado no cumple el esquema: " + "; ".join(errores[:5]))
    return paquete, avisos


def guardar(conn: sqlite3.Connection, pid: int, paquete: dict, carpeta: Path | str) -> Path:
    """Guarda el paquete en la BD y escribe el .md listo para llevar a Claude."""
    with conn:
        conn.execute("INSERT INTO paquete (id, perfil_id, semana_inicio, json) VALUES (?,?,?,?)",
                     (paquete["paquete_id"], pid, paquete["semana"]["inicio"], json.dumps(paquete, ensure_ascii=False)))
    inicio = PLANTILLA.index("## INICIO DEL PROMPT")
    fin = PLANTILLA.index("## FIN DEL PROMPT")
    cuerpo = PLANTILLA[inicio:fin].replace("## INICIO DEL PROMPT\n", "")
    md = (cuerpo.replace("{{PAQUETE_JSON}}", json.dumps(paquete, ensure_ascii=False, indent=2))
                .replace("{{PLAN_SCHEMA}}", ESQ_PLAN.strip()))
    destino = Path(carpeta) / "paquetes" / f"paquete_{paquete['semana']['inicio']}.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(md, encoding="utf-8")
    return destino
