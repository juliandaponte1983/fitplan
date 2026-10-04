"""API web local y conectores (Hevy simulado con httpx.MockTransport)."""
import json
from datetime import date
from pathlib import Path

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

EJ = Path(__file__).parents[1] / "examples"
FIX = Path(__file__).parent / "fixtures"
H = {"X-FitPlan": "1"}


@pytest.fixture
def cli(tmp_path, monkeypatch):
    monkeypatch.setenv("FITPLAN_CLAVE", Fernet.generate_key().decode())
    monkeypatch.setenv("FITPLAN_SECRETOS", "memoria")
    from app import config
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "w.db")
    monkeypatch.setattr(config, "DATOS_DIR", tmp_path / "datos")
    from app.db import cripto
    cripto._fernet.cache_clear()
    from app.main import app
    c = TestClient(app)
    assert c.post("/api/perfiles", json={"alias": "prueba", "sexo": "H", "nacimiento": "1986-01-01", "altura": 175}, headers=H).status_code == 200
    yield c
    cripto._fernet.cache_clear()


def test_seguridad_csrf_y_host(cli):
    assert cli.post("/api/perfiles", json={"alias": "x1"}).status_code == 403            # sin cabecera
    assert cli.get("/salud", headers={"host": "evil.example"}).status_code == 403          # DNS rebinding
    assert cli.get("/").status_code == 200


def test_ciclo_completo_por_web(cli, tmp_path):
    with open(FIX / "hevy_mini.csv", "rb") as f:
        r = cli.post("/api/p/prueba/subir", files=[("ficheros", ("hevy.csv", f, "text/csv"))], headers=H).json()
    assert r[0]["nuevos"] == 6
    comp = (EJ / "composicion_2026-09-22.json").read_text(encoding="utf-8")
    assert cli.post("/api/p/prueba/composicion", json={"texto": f"```json\n{comp}\n```"}, headers=H).json()["nuevos"] == 1
    y = (EJ / "perfil_plantilla.yaml").read_text(encoding="utf-8")
    assert cli.put("/api/p/prueba/perfil-yaml", json={"texto": "objetivo: [roto"}, headers=H).status_code == 400
    assert cli.put("/api/p/prueba/perfil-yaml", json={"texto": y}, headers=H).json()["ok"]
    paq = cli.post("/api/p/prueba/paquete", json={"semana": "2026-09-28"}, headers=H).json()
    assert paq["paquete_id"] in paq["md"]
    from tests.test_plan import plan_valido
    from app import config
    from app.db.conexion import conectar
    conn = conectar(config.DB_PATH)
    paquete = json.loads(conn.execute("SELECT json FROM paquete WHERE id=?", (paq["paquete_id"],)).fetchone()[0])
    r = cli.post("/api/p/prueba/plan", json={"texto": "```json\n" + json.dumps(plan_valido(paquete)) + "\n```"}, headers=H).json()
    assert r["estado"] == "aceptado", r
    est = cli.get("/api/p/prueba/estado").json()
    assert est["planes"][0]["semana_inicio"] == "2026-09-28"
    html = cli.get("/p/prueba/vista/2026-09-28")
    assert html.status_code == 200 and "Semana" in html.text
    assert cli.get("/api/p/prueba/analisis?semana=2026-09-28").json()["nutricion"]["proteina_g"] > 0


def _mock_hevy(entrenos, rutinas_creadas):
    def h(req: httpx.Request):
        p = req.url.path
        if p == "/v1/workouts":
            return httpx.Response(200, json={"page": 1, "page_count": 1, "workouts": entrenos})
        if p == "/v1/exercise_templates":
            return httpx.Response(200, json={"page": 1, "page_count": 1, "exercise_templates": [
                {"id": "79D0BB3A", "title": "Bench Press (Barbell)", "type": "weight_reps"}]})
        if p == "/v1/routine_folders" and req.method == "GET":
            return httpx.Response(200, json={"page": 1, "page_count": 1, "routine_folders": []})
        if p == "/v1/routine_folders":
            return httpx.Response(201, json={"routine_folder": {"id": 7, "title": "FitPlan"}})
        if p == "/v1/routines" and req.method == "GET":
            return httpx.Response(200, json={"page": 1, "page_count": 1, "routines": []})
        if p == "/v1/routines":
            body = json.loads(req.content)
            rutinas_creadas.append(body)
            return httpx.Response(201, json={"routine": [{"id": f"r{len(rutinas_creadas)}", **body["routine"]}]})
        return httpx.Response(404)
    return httpx.MockTransport(h)


def test_hevy_api_misma_clave_que_csv(tmp_path, monkeypatch):
    monkeypatch.setenv("FITPLAN_CLAVE", Fernet.generate_key().decode())
    monkeypatch.setenv("FITPLAN_SECRETOS", "memoria")
    from app.db import cripto
    cripto._fernet.cache_clear()
    from app import ingesta, sincronizar
    from app.conectores import secretos
    from app.db.conexion import conectar
    conn = conectar(tmp_path / "h.db")
    pid = ingesta.crear_perfil(conn, "prueba", "H", "1986-01-01", 175)
    ingesta.importar_hevy(conn, pid, FIX / "hevy_mini.csv")
    secretos.guardar("hevy:prueba", "clave-falsa")
    entreno = {"id": "w1", "title": "Pecho", "start_time": "2026-09-02T05:10:33+00:00", "end_time": "2026-09-02T06:05:10+00:00",
               "exercises": [{"index": 0, "title": "Bench Press (Barbell)", "exercise_template_id": "79D0BB3A", "superset_id": None,
                              "sets": [{"index": 0, "type": "warmup", "weight_kg": 30, "reps": 10},
                                       {"index": 1, "type": "normal", "weight_kg": 50, "reps": 10, "rpe": 8},
                                       {"index": 2, "type": "normal", "weight_kg": 52.5, "reps": 8}]}]}
    inf = sincronizar.sincronizar_hevy(conn, pid, "prueba", _mock_hevy([entreno], []))
    assert (inf.nuevos, inf.duplicados) == (1, 2)   # las dos primeras series ya venían del CSV
    assert conn.execute("SELECT id FROM hevy_plantilla WHERE titulo='Bench Press (Barbell)'").fetchone()[0] == "79D0BB3A"


def test_subir_rutinas_a_hevy(tmp_path, monkeypatch):
    monkeypatch.setenv("FITPLAN_CLAVE", Fernet.generate_key().decode())
    monkeypatch.setenv("FITPLAN_SECRETOS", "memoria")
    from app import ingesta, sincronizar
    from app.conectores import secretos
    from app.conectores.hevy_api import ErrorHevy
    from app.db.conexion import conectar
    conn = conectar(tmp_path / "r.db")
    pid = ingesta.crear_perfil(conn, "prueba", "H", "1986-01-01", 175)
    secretos.guardar("hevy:prueba", "clave-falsa")
    plan = {"entrenamiento": {"rutinas": [{"id": "RT1", "titulo": "B1S1 · Torso", "ejercicios": [
        {"exercise_template_id": "79D0BB3A", "nombre": "Bench Press (Barbell)", "descanso_s": 120, "superset_id": None,
         "series": [{"tipo": "warmup", "peso_kg": 30, "reps": 10}, {"tipo": "normal", "peso_kg": 50, "reps_rango": [8, 12]}]}]}]}}
    creadas = []
    r = sincronizar.subir_rutinas(conn, pid, "prueba", plan, _mock_hevy([], creadas))
    assert r == ["creada: B1S1 · Torso"]
    s = creadas[0]["routine"]["exercises"][0]["sets"][1]
    assert s["rep_range"] == {"start": 8, "end": 12} and s["weight_kg"] == 50 and creadas[0]["routine"]["folder_id"] == 7
    plan["entrenamiento"]["rutinas"][0]["ejercicios"][0]["exercise_template_id"] = "hevy:Bench Press (Barbell)"
    with pytest.raises(ErrorHevy, match="sin id real"):
        sincronizar.subir_rutinas(conn, pid, "prueba", plan, _mock_hevy([], []))
