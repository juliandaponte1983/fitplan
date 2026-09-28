"""Ingesta: lee ficheros con los parsers y guarda solo lo nuevo en la BD.

Cada función devuelve un Informe con nuevos, duplicados, errores y avisos.
Deduplicación en dos niveles: fichero idéntico (sha256) y registro (clave única).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.db.cripto import cifrar, descifrar
from app.parsers import fitdays, garmin_fit, hevy_csv, perfil_medico


@dataclass
class Informe:
    fuente: str
    fichero: str
    nuevos: int = 0
    duplicados: int = 0
    errores: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    ya_importado: bool = False

    def __str__(self) -> str:
        if self.ya_importado:
            return f"{self.fichero}: ya importado antes (sin cambios)"
        s = f"{self.fichero}: {self.nuevos} nuevos, {self.duplicados} duplicados"
        if self.errores:
            s += f", {len(self.errores)} errores"
        return s


# ---------------------------------------------------------------- perfiles
def crear_perfil(conn: sqlite3.Connection, alias: str, sexo: str | None = None,
                 fecha_nacimiento: str | None = None, altura_cm: float | None = None,
                 zona_horaria: str = "Europe/Madrid") -> int:
    with conn:
        cur = conn.execute(
            "INSERT INTO perfil (alias, sexo, fecha_nacimiento, altura_cm, zona_horaria) VALUES (?,?,?,?,?)",
            (alias, sexo, fecha_nacimiento, altura_cm, zona_horaria))
    return cur.lastrowid


def perfil_id(conn: sqlite3.Connection, alias: str) -> int:
    fila = conn.execute("SELECT id FROM perfil WHERE alias = ?", (alias,)).fetchone()
    if not fila:
        raise LookupError(f"no existe el perfil {alias!r}")
    return fila["id"]


def _tz(conn, pid) -> ZoneInfo:
    return ZoneInfo(conn.execute("SELECT zona_horaria FROM perfil WHERE id=?", (pid,)).fetchone()[0])


def _sha(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def _ya_importado(conn, pid, fuente, sha) -> bool:
    return conn.execute("SELECT 1 FROM importacion WHERE perfil_id=? AND fuente=? AND sha256=? LIMIT 1",
                        (pid, fuente, sha)).fetchone() is not None


def _registrar(conn, pid, inf: Informe, sha: str) -> None:
    conn.execute("INSERT INTO importacion (perfil_id, fuente, fichero, sha256, nuevos, duplicados) VALUES (?,?,?,?,?,?)",
                 (pid, inf.fuente, inf.fichero, sha, inf.nuevos, inf.duplicados))


def _utc(dt: datetime, tz: ZoneInfo) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- Hevy
def importar_hevy(conn: sqlite3.Connection, pid: int, ruta: Path | str) -> Informe:
    ruta = Path(ruta)
    datos = ruta.read_bytes()
    sha, inf = _sha(datos), Informe("hevy_csv", ruta.name)
    if _ya_importado(conn, pid, inf.fuente, sha):
        inf.ya_importado = True
        return inf
    res = hevy_csv.leer(datos)
    inf.errores = res.errores
    tz = _tz(conn, pid)
    with conn:
        for e in res.entrenos:
            conn.execute("INSERT OR IGNORE INTO hevy_entreno (perfil_id, inicio_utc, fin_utc, titulo) VALUES (?,?,?,?)",
                         (pid, _utc(e.inicio, tz), _utc(e.fin, tz), e.titulo))
            eid = conn.execute("SELECT id FROM hevy_entreno WHERE perfil_id=? AND inicio_utc=?",
                               (pid, _utc(e.inicio, tz))).fetchone()[0]
            for s in e.series:
                cur = conn.execute(
                    """INSERT OR IGNORE INTO hevy_serie (perfil_id, entreno_id, clave, ejercicio, ejercicio_orden,
                       set_index, tipo, peso_kg, reps, distancia_km, duracion_s, rpe, superset_id, notas)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (pid, eid, s.clave, s.ejercicio, s.ejercicio_orden, s.set_index, s.tipo, s.peso_kg, s.reps,
                     s.distancia_km, s.duracion_s, s.rpe, s.superset_id, s.notas))
                if cur.rowcount:
                    inf.nuevos += 1
                else:
                    inf.duplicados += 1
        _registrar(conn, pid, inf, sha)
    return inf


# ---------------------------------------------------------------- Garmin FIT
def importar_fit(conn: sqlite3.Connection, pid: int, ruta: Path | str) -> Informe:
    ruta = Path(ruta)
    datos = ruta.read_bytes()
    sha, inf = _sha(datos), Informe("garmin_fit", ruta.name)
    if _ya_importado(conn, pid, inf.fuente, sha):
        inf.ya_importado = True
        return inf
    try:
        a = garmin_fit.leer(datos, nombre=ruta.name)
    except Exception as e:  # FIT corrupto o no soportado
        inf.errores.append(str(e))
        return inf
    inf.avisos = a.avisos
    with conn:
        cur = conn.execute(
            """INSERT OR IGNORE INTO actividad (perfil_id, clave, garmin_id, tipo, sport, sub_sport, inicio_utc,
               duracion_s, distancia_km, kcal, fc_media, fc_max, ascenso_m, cadencia_media, te_aerobico,
               te_anaerobico, carga_garmin, fc_max_config, zonas_json, fc_json, con_gps, avisos_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (pid, a.clave, a.garmin_id, a.tipo, a.sport, a.sub_sport, _utc(a.inicio, timezone.utc), a.duracion_s,
             a.distancia_km, a.kcal, a.fc_media, a.fc_max, a.ascenso_m, a.cadencia_media, a.te_aerobico,
             a.te_anaerobico, a.carga_garmin, a.fc_max_config, json.dumps(a.zonas_s), json.dumps(a.fc),
             int(a.con_gps), json.dumps(a.avisos, ensure_ascii=False)))
        if cur.rowcount:
            inf.nuevos = 1
            conn.executemany(
                """INSERT INTO actividad_serie (actividad_id, orden, inicio_utc, duracion_s, reps, peso_kg,
                   descanso_s, categoria_garmin) VALUES (?,?,?,?,?,?,?,?)""",
                [(cur.lastrowid, i, _utc(s.inicio, timezone.utc) if s.inicio else None, s.duracion_s, s.reps,
                  s.peso_kg, s.descanso_s, s.categoria_garmin) for i, s in enumerate(a.series)])
        else:
            inf.duplicados = 1
        _registrar(conn, pid, inf, sha)
    return inf


# ---------------------------------------------------------------- Fitdays
def importar_composicion(conn: sqlite3.Connection, pid: int, ruta: Path | str) -> Informe:
    ruta = Path(ruta)
    texto = ruta.read_text(encoding="utf-8")
    sha, inf = _sha(texto.encode()), Informe("fitdays", ruta.name)
    if _ya_importado(conn, pid, inf.fuente, sha):
        inf.ya_importado = True
        return inf
    p = conn.execute("SELECT sexo, altura_cm, fecha_nacimiento FROM perfil WHERE id=?", (pid,)).fetchone()
    perfil = {"sexo": p["sexo"], "altura_cm": p["altura_cm"]}
    ant = conn.execute("SELECT datos_json FROM composicion WHERE perfil_id=? ORDER BY fecha_hora DESC LIMIT 1",
                       (pid,)).fetchone()
    r = fitdays.importar(texto, perfil=perfil, anterior=json.loads(ant[0]) if ant else None)
    inf.errores, inf.avisos = r.errores, r.avisos
    if not r.valido:
        return inf
    c = r.datos["composicion"]
    with conn:
        cur = conn.execute(
            """INSERT OR IGNORE INTO composicion (perfil_id, fecha_hora, peso_kg, grasa_pct, musculo_esqueletico_kg,
               masa_magra_kg, tmb_kcal, datos_json) VALUES (?,?,?,?,?,?,?,?)""",
            (pid, r.datos["fecha_hora"], c["peso_kg"], c.get("grasa_pct"), c.get("musculo_esqueletico_kg"),
             c.get("masa_magra_kg"), c.get("tmb_kcal"), json.dumps(r.datos, ensure_ascii=False)))
        inf.nuevos, inf.duplicados = (1, 0) if cur.rowcount else (0, 1)
        _registrar(conn, pid, inf, sha)
    return inf


# ---------------------------------------------------------------- Perfil médico
def importar_perfil_medico(conn: sqlite3.Connection, pid: int, ruta: Path | str) -> Informe:
    ruta = Path(ruta)
    r = perfil_medico.importar(ruta.read_bytes())
    inf = Informe("perfil_medico", ruta.name, errores=r.errores, avisos=r.avisos)
    if not r.valido:
        return inf
    with conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO perfil_medico (perfil_id, yaml_cifrado, sha256_md, generado) VALUES (?,?,?,?)",
            (pid, cifrar(json.dumps(r.yaml_datos, ensure_ascii=False)), r.sha256, r.yaml_datos.get("generado")))
        inf.nuevos, inf.duplicados = (1, 0) if cur.rowcount else (0, 1)
        _registrar(conn, pid, inf, r.sha256)
    return inf


def perfil_medico_vigente(conn: sqlite3.Connection, pid: int) -> dict | None:
    fila = conn.execute("SELECT yaml_cifrado FROM perfil_medico WHERE perfil_id=? ORDER BY importado DESC, id DESC LIMIT 1",
                        (pid,)).fetchone()
    return json.loads(descifrar(fila[0])) if fila else None


# ---------------------------------------------------------------- carpeta completa
def importar_carpeta(conn: sqlite3.Connection, pid: int, carpeta: Path | str) -> list[Informe]:
    """Recorre datos/<perfil>/{hevy,garmin_fit,fitdays,medico} e importa lo que haya."""
    carpeta = Path(carpeta)
    informes: list[Informe] = []
    for f in sorted((carpeta / "hevy").glob("*.csv")):
        informes.append(importar_hevy(conn, pid, f))
    for f in sorted([*(carpeta / "garmin_fit").glob("*.zip"), *(carpeta / "garmin_fit").glob("*.fit")]):
        informes.append(importar_fit(conn, pid, f))
    for f in sorted((carpeta / "fitdays").glob("*.json")):
        informes.append(importar_composicion(conn, pid, f))
    for f in sorted((carpeta / "medico").glob("*.md")):
        informes.append(importar_perfil_medico(conn, pid, f))
    return informes
