"""Línea de comandos de FitPlan.

  python -m app.cli perfil-nuevo julian --sexo H --nacimiento 1983-01-01 --altura 169
  python -m app.cli importar julian ../datos/julian
  python -m app.cli resumen julian
"""
from __future__ import annotations

import argparse

from app import config
from app.db.conexion import conectar
from app import ingesta


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="fitplan")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("perfil-nuevo")
    p.add_argument("alias")
    p.add_argument("--sexo", choices=["H", "M"])
    p.add_argument("--nacimiento", help="AAAA-MM-DD")
    p.add_argument("--altura", type=float, help="cm")
    p = sub.add_parser("importar")
    p.add_argument("alias")
    p.add_argument("carpeta")
    p = sub.add_parser("resumen")
    p.add_argument("alias")
    a = ap.parse_args(argv)

    conn = conectar()
    if a.cmd == "perfil-nuevo":
        pid = ingesta.crear_perfil(conn, a.alias, a.sexo, a.nacimiento, a.altura)
        print(f"Perfil '{a.alias}' creado (id {pid}) en {config.DB_PATH}")
    elif a.cmd == "importar":
        pid = ingesta.perfil_id(conn, a.alias)
        for inf in ingesta.importar_carpeta(conn, pid, a.carpeta):
            print(("✔ " if not inf.errores else "✘ ") + str(inf))
            for x in inf.errores:
                print("   error:", x)
            for x in inf.avisos:
                print("   aviso:", x)
    elif a.cmd == "resumen":
        pid = ingesta.perfil_id(conn, a.alias)
        q = lambda sql: conn.execute(sql, (pid,)).fetchone()
        he = q("SELECT COUNT(*), MIN(inicio_utc), MAX(inicio_utc) FROM hevy_entreno WHERE perfil_id=?")
        hs = q("SELECT COUNT(*) FROM hevy_serie WHERE perfil_id=?")
        ac = conn.execute("SELECT tipo, COUNT(*) n FROM actividad WHERE perfil_id=? GROUP BY tipo ORDER BY n DESC", (pid,)).fetchall()
        co = q("SELECT COUNT(*), MAX(fecha_hora), (SELECT peso_kg FROM composicion WHERE perfil_id=p.id ORDER BY fecha_hora DESC LIMIT 1) FROM composicion, perfil p WHERE p.id=?1 AND composicion.perfil_id=?1")
        pm = ingesta.perfil_medico_vigente(conn, pid)
        print(f"Hevy:     {he[0]} entrenos, {hs[0]} series ({(he[1] or '')[:10]} → {(he[2] or '')[:10]})")
        print("Garmin:   " + (", ".join(f"{r['tipo']} {r['n']}" for r in ac) or "sin actividades"))
        print(f"Fitdays:  {co[0]} mediciones" + (f", última {co[1]} ({co[2]} kg)" if co[0] else ""))
        print(f"Médico:   {'perfil generado ' + str(pm.get('generado')) if pm else 'sin perfil médico'}")


if __name__ == "__main__":
    main()
