"""Exportación del paquete, validación del plan (V1–V15) e importación."""
import copy
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

EJ = Path(__file__).parents[1] / "examples"
FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    monkeypatch.setenv("FITPLAN_CLAVE", Fernet.generate_key().decode())
    from app.db import cripto
    cripto._fernet.cache_clear()
    from app.db.conexion import conectar
    from app import ingesta
    from app.packages import exportar
    conn = conectar(tmp_path / "t.db")
    pid = ingesta.crear_perfil(conn, "prueba", "H", "1986-01-01", 175)
    ingesta.importar_hevy(conn, pid, FIX / "hevy_mini.csv")
    ingesta.importar_composicion(conn, pid, EJ / "composicion_2026-09-22.json")
    ingesta.importar_perfil_medico(conn, pid, EJ / "perfil_medico_ejemplo.md")
    yaml_p = tmp_path / "perfil.yaml"
    yaml_p.write_text((EJ / "perfil_plantilla.yaml").read_text(encoding="utf-8").replace(
        "alimentos_prohibidos: []", "alimentos_prohibidos: [marisco]"), encoding="utf-8")
    exportar.cargar_perfil_yaml(conn, pid, yaml_p)
    yield conn, pid, tmp_path
    conn.close()
    cripto._fernet.cache_clear()


def plan_valido(paq: dict) -> dict:
    """Plan mínimo que cumple todas las reglas de bloqueo del paquete."""
    on, oe = paq["objetivos"]["nutricion"], paq["objetivos"]["entreno"]
    ini = date.fromisoformat(paq["semana"]["inicio"])
    dias_nombre = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
    prog = {p["exercise_template_id"]: p for p in oe["progresiones"]}
    ejercicios = []
    for p in list(prog.values())[:2]:
        ejercicios.append({"exercise_template_id": p["exercise_template_id"], "nombre": p["nombre"], "superset_id": None, "descanso_s": 120,
                           "series": [{"tipo": "normal", "peso_kg": p["peso_kg"], "reps_rango": [p["reps_min"], p["reps_max"]]}] * p["series"]})
    fuerza_dias, cardio_dias = [0, 2, 4][:oe["sesiones_fuerza"]], [1, 5][:oe["sesiones_cardio"]]
    z2_por_sesion = oe["min_z2_semana"] / max(len(cardio_dias), 1)
    dias = []
    for i in range(7):
        ses = []
        if i in fuerza_dias:
            ses.append({"tipo": "fuerza", "hora": "07:00", "duracion_min": 60, "objetivo": "fuerza", "rutina_ref": "RT1"})
        if i in cardio_dias:
            ses.append({"tipo": "cinta", "hora": "07:00" if i < 5 else "10:00", "duracion_min": int(z2_por_sesion) + 5, "objetivo": "Z2",
                        "bloques_cardio": [{"nombre": "Z2", "duracion_min": z2_por_sesion, "intensidad": {"zona": "Z2"}}]})
        dias.append({"fecha": (ini + timedelta(days=i)).isoformat(), "dia": dias_nombre[i], "sesiones": ses})

    def dia_nut(i):
        tipo = "entreno" if dias[i]["sesiones"] else "descanso"
        kcal = on["kcal_entreno"] if tipo == "entreno" else on["kcal_descanso"]
        p, g = on["proteina_g"], on["grasa_g_min"] + 3
        c = (kcal - 4 * p - 9 * g) / 4
        m = {"kcal": kcal, "proteina_g": p, "carbohidratos_g": c, "grasa_g": g, "fibra_g": on["fibra_g_min"] + 2}
        return {"fecha": dias[i]["fecha"], "tipo_dia": tipo, "totales": m,
                "comidas": [{"comida": "almuerzo", "hora": "14:00", "items": [{"alimento": "pechuga de pollo con arroz", "gramos": 500, "raciones": 1, "macros": dict(m)}]}]}

    return {"schema": "plan_semanal/v1", "paquete_id": paq["paquete_id"], "semana_inicio": paq["semana"]["inicio"],
            "resumen": {"enfoque": "prueba", "cambios_vs_anterior": []},
            "entrenamiento": {"dias": dias, "rutinas": [{"id": "RT1", "hevy_routine_id": None, "titulo": "B1S1 · Prueba", "ejercicios": ejercicios}]},
            "nutricion": {"objetivos_dia": {"entreno": {"kcal": on["kcal_entreno"], "proteina_g": on["proteina_g"], "carbohidratos_g": 200, "grasa_g": 70},
                                            "descanso": {"kcal": on["kcal_descanso"], "proteina_g": on["proteina_g"], "carbohidratos_g": 150, "grasa_g": 70}},
                          "dias": [dia_nut(i) for i in range(7)],
                          "recetas": [],
                          "lista_compra": [{"alimento": "pechuga de pollo", "cantidad": 1, "unidad": "kg", "seccion": "carne"}],
                          "alimentos_evitar": [{"alimento_o_grupo": "marisco", "nivel": "prohibido", "motivo": "declarado", "restriccion_id": "RDU1"}]},
            "autochequeo": {"restricciones_respetadas": True, "objetivos_cumplidos": True, "desviaciones": []}}


def _paquete(entorno):
    from app.packages import exportar
    conn, pid, tmp = entorno
    paq, avisos = exportar.construir(conn, pid, date(2026, 9, 28))
    return paq, avisos


def test_paquete_cumple_esquema_y_lleva_restricciones(entorno):
    paq, avisos = _paquete(entorno)
    assert paq["semana"]["inicio"] == "2026-09-28"
    assert any(r["alimento_o_grupo"] == "marisco" and r["nivel"] == "prohibido" for r in paq["restricciones"]["dieta"])
    assert any(r["alimento_o_grupo"] == "grasas saturadas" for r in paq["restricciones"]["dieta"])  # del perfil médico
    assert paq["objetivos"]["entreno"]["progresiones"]
    assert all(e["exercise_template_id"].startswith("hevy:") for e in paq["catalogo_ejercicios"])


def test_markdown_del_paquete(entorno):
    from app.packages import exportar
    conn, pid, tmp = entorno
    paq, _ = _paquete(entorno)
    ruta = exportar.guardar(conn, pid, paq, tmp)
    md = ruta.read_text(encoding="utf-8")
    assert paq["paquete_id"] in md and "{{" not in md and "plan_semanal/v1" in md


def test_plan_valido_sin_bloqueos(entorno):
    from app.packages import validador
    paq, _ = _paquete(entorno)
    h = validador.validar(plan_valido(paq), paq)
    assert [x for x in h if x.severidad == "bloqueo"] == []


@pytest.mark.parametrize("mutacion,regla", [
    (lambda p: p.update(paquete_id="otro"), "V2"),
    (lambda p: p["entrenamiento"]["rutinas"][0]["ejercicios"][0].update(exercise_template_id="hevy:Inventado"), "V3"),
    (lambda p: p["nutricion"]["dias"][0]["comidas"][0]["items"][0].update(alimento="gambas al ajillo"), "V5"),
    (lambda p: p["nutricion"].update(alimentos_evitar=[]), "V6"),
    (lambda p: p["nutricion"]["dias"][0]["totales"].update(kcal=900) or p["nutricion"]["dias"][0]["comidas"][0]["items"][0]["macros"].update(kcal=900), "V7"),
    (lambda p: p["nutricion"]["dias"][1]["comidas"][0]["items"][0]["macros"].update(proteina_g=40) or p["nutricion"]["dias"][1]["totales"].update(proteina_g=40), "V8"),
    (lambda p: p["nutricion"]["dias"][2]["totales"].update(kcal=5000), "V9"),
    (lambda p: p["entrenamiento"]["rutinas"][0]["ejercicios"][0]["series"].__setitem__(0, {"tipo": "normal", "peso_kg": 999, "reps_rango": [8, 12]}), "V11"),
    (lambda p: p["entrenamiento"]["dias"][0].update(sesiones=[]), "V12"),
    (lambda p: p.pop("autochequeo"), "V1"),
])
def test_reglas_de_bloqueo(entorno, mutacion, regla):
    from app.packages import validador
    paq, _ = _paquete(entorno)
    plan = copy.deepcopy(plan_valido(paq))
    mutacion(plan)
    h = validador.validar(plan, paq)
    assert any(x.regla == regla and x.severidad == "bloqueo" for x in h), [(x.regla, x.mensaje) for x in h]


def test_importar_acepta_y_rechaza(entorno):
    from app.packages import exportar, importar
    conn, pid, tmp = entorno
    paq, _ = _paquete(entorno)
    exportar.guardar(conn, pid, paq, tmp)
    bueno = tmp / "resp.md"
    bueno.write_text("Aquí va:\n```json\n" + json.dumps(plan_valido(paq)) + "\n```", encoding="utf-8")
    r = importar.importar(conn, pid, bueno, tmp)
    assert r["estado"] == "aceptado" and Path(r["plan"]).exists()
    malo = copy.deepcopy(plan_valido(paq))
    malo["nutricion"]["alimentos_evitar"] = []
    (tmp / "malo.json").write_text(json.dumps(malo), encoding="utf-8")
    r2 = importar.importar(conn, pid, tmp / "malo.json", tmp)
    assert r2["estado"] == "rechazado" and "V6" in Path(r2["correccion"]).read_text(encoding="utf-8")


def test_v16_no_le_gusta_es_aviso(entorno):
    from app.packages import validador
    paq, _ = _paquete(entorno)
    paq["perfil"]["preferencias_alimentarias"]["no_le_gusta"] = ["legumbres"]
    plan = plan_valido(paq)
    plan["nutricion"]["dias"][0]["comidas"][0]["items"][0]["alimento"] = "lentejas estofadas"
    h = validador.validar(plan, paq)
    assert any(x.regla == "V16" and x.severidad == "aviso" for x in h)
    assert not any(x.severidad == "bloqueo" for x in h)


def test_importar_normaliza_titulos_y_genera_vista(entorno):
    from app.packages import exportar, importar
    conn, pid, tmp = entorno
    paq, _ = _paquete(entorno)
    exportar.guardar(conn, pid, paq, tmp)
    plan = plan_valido(paq)
    plan["entrenamiento"]["rutinas"][0]["titulo"] = "B1S2 - Pierna"
    (tmp / "r.json").write_text(json.dumps(plan), encoding="utf-8")
    r = importar.importar(conn, pid, tmp / "r.json", tmp)
    guardado = json.loads(Path(r["plan"]).read_text(encoding="utf-8"))
    assert guardado["entrenamiento"]["rutinas"][0]["titulo"] == "B1S1 · Pierna"
    html = Path(r["vista"]).read_text(encoding="utf-8")
    assert "B1S1 · Pierna" in html and "__DATOS__" not in html
