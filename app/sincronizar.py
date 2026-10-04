"""Sincronización con las fuentes: Hevy (API) y Garmin (garminconnect), más rutinas hacia Hevy."""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app import ingesta
from app.conectores import garmin, secretos
from app.conectores.hevy_api import ClienteHevy, ErrorHevy, rutina_a_hevy


def _registrar(conn, pid, fuente, resultado: str) -> None:
    with conn:
        conn.execute("INSERT INTO sincronizacion (perfil_id, fuente, ultima, resultado) VALUES (?,?,?,?) "
                     "ON CONFLICT(perfil_id, fuente) DO UPDATE SET ultima=excluded.ultima, resultado=excluded.resultado",
                     (pid, fuente, datetime.now(timezone.utc).isoformat(timespec="seconds"), resultado))


def ultima(conn, pid, fuente) -> dict | None:
    f = conn.execute("SELECT ultima, resultado FROM sincronizacion WHERE perfil_id=? AND fuente=?", (pid, fuente)).fetchone()
    return dict(f) if f else None


# ------------------------------------------------------------------ Hevy
def clave_hevy(alias: str) -> str | None:
    return secretos.leer(f"hevy:{alias}")


def cliente_hevy(alias: str, transporte=None) -> ClienteHevy:
    clave = clave_hevy(alias)
    if not clave:
        raise ErrorHevy("Hevy no está conectado para este perfil (falta la clave de API)")
    return ClienteHevy(clave, transporte)


def importar_entrenos_api(conn: sqlite3.Connection, pid: int, entrenos: list[dict]) -> ingesta.Informe:
    """Guarda entrenos de la API con la MISMA clave que el CSV (hora local al minuto | orden | serie)."""
    tz = ZoneInfo(conn.execute("SELECT zona_horaria FROM perfil WHERE id=?", (pid,)).fetchone()[0])
    inf = ingesta.Informe("hevy_api", f"{len(entrenos)} entrenos")
    with conn:
        for w in entrenos:
            ini = datetime.fromisoformat(w["start_time"].replace("Z", "+00:00")).astimezone(tz).replace(second=0, microsecond=0, tzinfo=None)
            fin = datetime.fromisoformat(w["end_time"].replace("Z", "+00:00")).astimezone(tz).replace(second=0, microsecond=0, tzinfo=None)
            ini_utc, fin_utc = ingesta._utc(ini, tz), ingesta._utc(fin, tz)
            conn.execute("INSERT OR IGNORE INTO hevy_entreno (perfil_id, inicio_utc, fin_utc, titulo) VALUES (?,?,?,?)",
                         (pid, ini_utc, fin_utc, w.get("title")))
            eid = conn.execute("SELECT id FROM hevy_entreno WHERE perfil_id=? AND inicio_utc=?", (pid, ini_utc)).fetchone()[0]
            for e in sorted(w.get("exercises", []), key=lambda x: x.get("index", 0)):
                orden = int(e.get("index", 0)) + 1
                for s in sorted(e.get("sets", []), key=lambda x: x.get("index", 0)):
                    clave = f"{ini.isoformat()}|{orden}|{s.get('index', 0)}"
                    dist = s.get("distance_meters")
                    cur = conn.execute(
                        """INSERT OR IGNORE INTO hevy_serie (perfil_id, entreno_id, clave, ejercicio, ejercicio_orden, set_index,
                           tipo, peso_kg, reps, distancia_km, duracion_s, rpe, superset_id, notas) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (pid, eid, clave, e.get("title", "").strip(), orden, s.get("index", 0), s.get("type") or "normal",
                         s.get("weight_kg"), s.get("reps"), dist / 1000 if dist else None, s.get("duration_seconds"),
                         s.get("rpe"), e.get("superset_id"), (e.get("notes") or "").strip()))
                    if cur.rowcount:
                        inf.nuevos += 1
                    else:
                        inf.duplicados += 1
    return inf


def sincronizar_hevy(conn: sqlite3.Connection, pid: int, alias: str, transporte=None) -> ingesta.Informe:
    cli = cliente_hevy(alias, transporte)
    previa = ultima(conn, pid, "hevy_api")
    if previa:
        eventos = cli.eventos_desde(datetime.fromisoformat(previa["ultima"]) - timedelta(days=2))
        entrenos = [ev["workout"] for ev in eventos if ev.get("type") == "updated" and ev.get("workout")]
    else:
        entrenos = cli.entrenos()
    inf = importar_entrenos_api(conn, pid, entrenos)
    plantillas = cli.plantillas()
    with conn:
        conn.executemany("INSERT OR REPLACE INTO hevy_plantilla (perfil_id, id, titulo, tipo, musculo, equipo) VALUES (?,?,?,?,?,?)",
                         [(pid, t["id"], t["title"], t.get("type"), t.get("primary_muscle_group"), t.get("equipment")) for t in plantillas])
    inf.avisos.append(f"{len(plantillas)} ejercicios en el catálogo de Hevy")
    _registrar(conn, pid, "hevy_api", str(inf))
    return inf


def subir_rutinas(conn: sqlite3.Connection, pid: int, alias: str, plan: dict, transporte=None) -> list[str]:
    """Crea o actualiza en Hevy (carpeta 'FitPlan') las rutinas del plan. Reutiliza los huecos RT1, RT2…"""
    cli = cliente_hevy(alias, transporte)
    no_reales = [e["nombre"] for r in plan["entrenamiento"]["rutinas"] for e in r["ejercicios"]
                 if e["exercise_template_id"].startswith("hevy:")]
    if no_reales:
        raise ErrorHevy("hay ejercicios sin id real de Hevy (sincroniza Hevy y genera el paquete de nuevo): " + ", ".join(no_reales[:5]))
    carpeta = next((c for c in cli.carpetas() if c.get("title") == "FitPlan"), None) or cli.crear_carpeta("FitPlan")
    existentes = {r["id"] for r in cli.rutinas()}
    salida = []
    for r in plan["entrenamiento"]["rutinas"]:
        cuerpo = rutina_a_hevy(r)
        fila = conn.execute("SELECT routine_id FROM hevy_rutina WHERE perfil_id=? AND hueco=?", (pid, r["id"])).fetchone()
        if fila and fila[0] in existentes:
            cli.actualizar_rutina(fila[0], cuerpo)
            salida.append(f"actualizada: {r['titulo']}")
        else:
            nueva = cli.crear_rutina(cuerpo, carpeta.get("id"))
            with conn:
                conn.execute("INSERT OR REPLACE INTO hevy_rutina (perfil_id, hueco, routine_id) VALUES (?,?,?)", (pid, r["id"], nueva["id"]))
            salida.append(f"creada: {r['titulo']}")
    _registrar(conn, pid, "hevy_rutinas", "; ".join(salida))
    return salida


# ------------------------------------------------------------------ Garmin
def sincronizar_garmin(conn: sqlite3.Connection, pid: int, alias: str, carpeta_datos: Path) -> list[ingesta.Informe]:
    previa = ultima(conn, pid, "garmin")
    desde = (datetime.fromisoformat(previa["ultima"]).date() - timedelta(days=3)) if previa else date.today() - timedelta(days=56)
    ya = {r[0] for r in conn.execute("SELECT garmin_id FROM actividad WHERE perfil_id=? AND garmin_id IS NOT NULL", (pid,))}
    nuevas = garmin.descargar_nuevas(alias, Path(carpeta_datos) / "garmin_fit", desde, ya)
    informes = [ingesta.importar_fit(conn, pid, f) for f in nuevas]
    fcr = None
    try:
        fcr = garmin.fc_reposo_media(alias)
    except Exception:
        pass
    if fcr:
        from app.engine import analisis
        analisis.guardar_ajustes(conn, pid, fc_reposo_garmin=fcr)
    _registrar(conn, pid, "garmin", f"{len(nuevas)} actividades nuevas" + (f", FC reposo 7 d {fcr}" if fcr else ""))
    return informes
