"""API y web local de FitPlan.  Arranque:  python -m app.servidor  →  http://127.0.0.1:8720

Seguridad (uso local):
- Escucha solo en 127.0.0.1.
- Rechaza peticiones cuyo Host no sea localhost (protección frente a DNS rebinding).
- Toda petición que modifica datos exige la cabecera X-FitPlan (bloquea formularios cross-site / CSRF).
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

from app import config, ingesta, sincronizar, vista
from app.conectores import garmin, secretos
from app.conectores.hevy_api import ClienteHevy, ErrorHevy
from app.db.conexion import conectar
from app.engine import analisis as motor
from app.packages import exportar, importar as importar_plan

app = FastAPI(title="FitPlan", version="0.5.0")
RAIZ = Path(__file__).resolve().parents[1]
ESTATICO = Path(__file__).with_name("static")
HOSTS = {"127.0.0.1", "localhost", "testserver"}


@app.middleware("http")
async def seguridad(request: Request, call_next):
    host = (request.headers.get("host") or "").split(":")[0]
    if host not in HOSTS:
        return JSONResponse({"detail": "host no permitido"}, status_code=403)
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-fitplan") != "1":
        return JSONResponse({"detail": "falta la cabecera X-FitPlan"}, status_code=403)
    resp = await call_next(request)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@app.exception_handler(ValueError)
@app.exception_handler(LookupError)
@app.exception_handler(ErrorHevy)
@app.exception_handler(garmin.ErrorGarmin)
async def errores(_, exc):
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.exception_handler(Exception)
async def error_inesperado(request: Request, exc: Exception):
    """Cualquier fallo no previsto llega a la web como mensaje legible (y queda en la Terminal)."""
    import logging
    import traceback
    logging.getLogger("fitplan").error("Error en %s %s\n%s", request.method, request.url.path, traceback.format_exc())
    return JSONResponse({"detail": f"error interno ({type(exc).__name__}): {exc}"}, status_code=500)


def db():
    conn = conectar()
    try:
        yield conn
    finally:
        conn.close()


def _pid(conn: sqlite3.Connection, alias: str) -> int:
    return ingesta.perfil_id(conn, alias)


def _lunes(semana: str | None) -> date:
    if semana:
        return date.fromisoformat(semana)
    hoy = date.today()
    return motor.lunes(hoy + timedelta(days=7 if hoy.weekday() >= 5 else 0))


# ------------------------------------------------------------------ básicos
@app.get("/salud")
def salud() -> dict:
    return {"estado": "ok", "version": app.version}


@app.get("/", response_class=HTMLResponse)
def inicio():
    return FileResponse(ESTATICO / "index.html")


class NuevoPerfil(BaseModel):
    alias: str
    sexo: str | None = None
    nacimiento: str | None = None
    altura: float | None = None


@app.get("/api/perfiles")
def perfiles(conn=Depends(db)):
    return [dict(r) for r in conn.execute("SELECT alias, sexo, fecha_nacimiento, altura_cm FROM perfil ORDER BY id")]


@app.post("/api/perfiles")
def crear_perfil(p: NuevoPerfil, conn=Depends(db)):
    if not re.fullmatch(r"[a-z0-9_-]{2,30}", p.alias):
        raise ValueError("alias: 2–30 caracteres, minúsculas, números, '-' o '_'")
    pid = ingesta.crear_perfil(conn, p.alias, p.sexo, p.nacimiento, p.altura)
    for sub in ("hevy", "garmin_fit", "fitdays", "medico"):
        (config.carpeta_perfil(p.alias) / sub).mkdir(parents=True, exist_ok=True)
    return {"id": pid}


@app.get("/api/p/{alias}/estado")
def estado(alias: str, conn=Depends(db)):
    pid = _pid(conn, alias)
    q = lambda sql: conn.execute(sql, (pid,)).fetchone()
    comp = conn.execute("SELECT fecha_hora, peso_kg, grasa_pct FROM composicion WHERE perfil_id=? ORDER BY fecha_hora DESC LIMIT 2", (pid,)).fetchall()
    aj = motor.ajustes(conn, pid)
    planes = [dict(r) for r in conn.execute(
        "SELECT semana_inicio, estado, importado FROM plan WHERE perfil_id=? AND estado='aceptado' ORDER BY semana_inicio", (pid,))]
    return {
        "alias": alias,
        "hevy": {"entrenos": q("SELECT COUNT(*) FROM hevy_entreno WHERE perfil_id=?")[0],
                 "ultimo": (q("SELECT MAX(inicio_utc) FROM hevy_entreno WHERE perfil_id=?")[0] or "")[:10],
                 "conectado": bool(sincronizar.clave_hevy(alias)), "sync": sincronizar.ultima(conn, pid, "hevy_api"),
                 "plantillas": q("SELECT COUNT(*) FROM hevy_plantilla WHERE perfil_id=?")[0]},
        "garmin": {"actividades": q("SELECT COUNT(*) FROM actividad WHERE perfil_id=?")[0],
                   "ultima": (q("SELECT MAX(inicio_utc) FROM actividad WHERE perfil_id=?")[0] or "")[:10],
                   "conectado": garmin.conectado(alias), "sync": sincronizar.ultima(conn, pid, "garmin")},
        "composicion": [dict(r) for r in comp],
        "medico": bool(ingesta.perfil_medico_vigente(conn, pid)),
        "perfil_plan": bool(aj.get("perfil_plan")),
        "objetivo": aj.get("objetivo"),
        "planes": planes,
        "semana_siguiente": _lunes(None).isoformat(),
    }


# ------------------------------------------------------------------ datos
@app.post("/api/p/{alias}/sincronizar")
def sincronizar_todo(alias: str, conn=Depends(db)):
    pid = _pid(conn, alias)
    res = {}
    for fuente, f in (("hevy", lambda: [sincronizar.sincronizar_hevy(conn, pid, alias)]),
                      ("garmin", lambda: sincronizar.sincronizar_garmin(conn, pid, alias, config.carpeta_perfil(alias)))):
        try:
            res[fuente] = {"ok": True, "informes": [vars(i) for i in f()]}
        except (ErrorHevy, garmin.ErrorGarmin) as e:
            res[fuente] = {"ok": False, "error": str(e)}
        except Exception as e:  # la librería de Garmin puede romperse: no tumbar la app
            res[fuente] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return res


DESTINOS = {".csv": ("hevy", ingesta.importar_hevy), ".zip": ("garmin_fit", ingesta.importar_fit),
            ".fit": ("garmin_fit", ingesta.importar_fit), ".json": ("fitdays", ingesta.importar_composicion),
            ".md": ("medico", ingesta.importar_perfil_medico)}


@app.post("/api/p/{alias}/subir")
async def subir(alias: str, ficheros: list[UploadFile] = File(...), conn=Depends(db)):
    pid = _pid(conn, alias)
    salida = []
    for f in ficheros:
        ext = Path(f.filename or "").suffix.lower()
        if ext not in DESTINOS:
            salida.append({"fichero": f.filename, "errores": [f"tipo no admitido ({ext})"]})
            continue
        sub, fn = DESTINOS[ext]
        nombre = Path(f.filename).name
        destino = config.carpeta_perfil(alias) / sub / nombre
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(await f.read())
        salida.append(vars(fn(conn, pid, destino)))
    return salida


class Texto(BaseModel):
    texto: str


@app.post("/api/p/{alias}/composicion")
def composicion(alias: str, t: Texto, conn=Depends(db)):
    pid = _pid(conn, alias)
    datos = importar_plan.extraer_json(t.texto)
    destino = config.carpeta_perfil(alias) / "fitdays" / f"composicion_{datos.get('fecha_hora', 'sin_fecha')[:10]}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    return vars(ingesta.importar_composicion(conn, pid, destino))


@app.get("/api/p/{alias}/analisis")
def analisis(alias: str, semana: str | None = None, conn=Depends(db)):
    return motor.analizar(conn, _pid(conn, alias), _lunes(semana))


# ------------------------------------------------------------------ ciclo semanal
class PedidoPaquete(BaseModel):
    semana: str | None = None
    nota: str = ""


@app.post("/api/p/{alias}/paquete")
def paquete(alias: str, p: PedidoPaquete, conn=Depends(db)):
    pid = _pid(conn, alias)
    paq, avisos = exportar.construir(conn, pid, _lunes(p.semana), p.nota)
    ruta = exportar.guardar(conn, pid, paq, config.carpeta_perfil(alias))
    return {"paquete_id": paq["paquete_id"], "semana": paq["semana"], "avisos": avisos, "nombre": ruta.name,
            "md": ruta.read_text(encoding="utf-8"), "objetivos": paq["objetivos"]["nutricion"] | {
                k: paq["objetivos"]["entreno"][k] for k in ("sesiones_fuerza", "sesiones_cardio", "min_z2_semana")}}


@app.post("/api/p/{alias}/plan")
def plan(alias: str, t: Texto, conn=Depends(db)):
    pid = _pid(conn, alias)
    datos = importar_plan.extraer_json(t.texto)
    carpeta = config.carpeta_perfil(alias)
    resp = carpeta / "paquetes" / f"respuesta_{datos.get('semana_inicio', 'sin_semana')}.json"
    resp.parent.mkdir(parents=True, exist_ok=True)
    resp.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    r = importar_plan.importar(conn, pid, resp, carpeta)
    if r.get("correccion"):
        r["correccion_md"] = Path(r["correccion"]).read_text(encoding="utf-8")
    return r


@app.get("/p/{alias}/vista/{semana}", response_class=HTMLResponse)
def ver_plan(alias: str, semana: str, conn=Depends(db)):
    pid = _pid(conn, alias)
    f = conn.execute("SELECT p.json, k.json FROM plan p JOIN paquete k ON k.id=p.paquete_id WHERE p.perfil_id=? AND "
                     "p.semana_inicio=? AND p.estado='aceptado' ORDER BY p.id DESC LIMIT 1", (pid, semana)).fetchone()
    if not f:
        raise HTTPException(404, "no hay plan aceptado para esa semana")
    return HTMLResponse(vista.generar(json.loads(f[0]), json.loads(f[1]), config.carpeta_perfil(alias)).read_text(encoding="utf-8"))


@app.post("/api/p/{alias}/hevy/rutinas/{semana}")
def rutinas_a_hevy(alias: str, semana: str, conn=Depends(db)):
    pid = _pid(conn, alias)
    f = conn.execute("SELECT json FROM plan WHERE perfil_id=? AND semana_inicio=? AND estado='aceptado' ORDER BY id DESC LIMIT 1",
                     (pid, semana)).fetchone()
    if not f:
        raise LookupError("no hay plan aceptado para esa semana")
    return {"resultado": sincronizar.subir_rutinas(conn, pid, alias, json.loads(f[0]))}


# ------------------------------------------------------------------ ajustes y conectores
@app.get("/api/p/{alias}/perfil-yaml")
def leer_perfil_yaml(alias: str):
    ruta = config.carpeta_perfil(alias) / "perfil.yaml"
    plantilla = RAIZ / "examples" / "perfil_plantilla.yaml"
    return {"texto": (ruta if ruta.exists() else plantilla).read_text(encoding="utf-8"), "existe": ruta.exists()}


@app.put("/api/p/{alias}/perfil-yaml")
def guardar_perfil_yaml(alias: str, t: Texto, conn=Depends(db)):
    pid = _pid(conn, alias)
    ruta = config.carpeta_perfil(alias) / "perfil.yaml"
    tmp = ruta.with_suffix(".yaml.tmp")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(t.texto, encoding="utf-8")
    try:
        exportar.cargar_perfil_yaml(conn, pid, tmp)   # valida antes de sustituir
    except ValueError:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(ruta)
    return {"ok": True}


@app.get("/api/prompts/{nombre}")
def prompt(nombre: str):
    fichero = {"medico": "01_perfil_medico.md", "fitdays": "02_fitdays.md"}.get(nombre)
    if not fichero:
        raise HTTPException(404)
    t = (RAIZ / "prompts" / fichero).read_text(encoding="utf-8")
    ini = t.find("## INICIO DEL PROMPT")
    fin = t.find("## FIN DEL PROMPT")
    return {"texto": t[ini + len("## INICIO DEL PROMPT"):fin].strip() if ini >= 0 and fin > ini else t}


class ClaveHevy(BaseModel):
    clave: str


@app.put("/api/p/{alias}/hevy/clave")
def hevy_clave(alias: str, c: ClaveHevy, conn=Depends(db)):
    _pid(conn, alias)
    info = ClienteHevy(c.clave.strip()).probar()          # valida la clave antes de guardarla
    secretos.guardar(f"hevy:{alias}", c.clave.strip())
    return {"ok": True, **info}


@app.delete("/api/p/{alias}/hevy/clave")
def hevy_borrar(alias: str):
    secretos.borrar(f"hevy:{alias}")
    return {"ok": True}


class LoginGarmin(BaseModel):
    email: str | None = None
    password: str | None = None
    mfa: str | None = None


@app.post("/api/p/{alias}/garmin/login")
def garmin_login(alias: str, l: LoginGarmin, conn=Depends(db)):
    _pid(conn, alias)
    if l.mfa:
        return {"estado": garmin.completar_mfa(alias, l.mfa)}
    if not (l.email and l.password):
        raise ValueError("email y contraseña obligatorios")
    return {"estado": garmin.iniciar_sesion(alias, l.email, l.password)}


@app.delete("/api/p/{alias}/garmin/login")
def garmin_salir(alias: str):
    garmin.desconectar(alias)
    return {"ok": True}
