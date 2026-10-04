"""Línea de comandos de FitPlan.

  python -m app.cli perfil-nuevo julian --sexo H --nacimiento 1983-01-01 --altura 169
  python -m app.cli importar julian ../datos/julian
  python -m app.cli resumen julian
  python -m app.cli ajustes julian --objetivo perder_grasa --fc-reposo 58
  python -m app.cli analisis julian [--semana 2026-09-28] [--json]
  python -m app.cli perfil-cargar julian ../datos/julian/perfil.yaml
  python -m app.cli paquete julian ../datos/julian [--semana 2026-09-28] [--nota "esta semana viajo el jueves"]
  python -m app.cli plan-importar julian ../datos/julian respuesta_claude.md
"""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta

from app import config
from app.db.conexion import conectar
from app import ingesta
from app.engine import analisis as motor
from app.packages import exportar, importar as importar_plan


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
    p = sub.add_parser("ajustes")
    p.add_argument("alias")
    p.add_argument("--objetivo", choices=["perder_grasa", "recomposicion", "ganar_musculo", "rendimiento", "salud_general"])
    p.add_argument("--nivel", choices=["principiante", "intermedio", "avanzado"])
    p.add_argument("--fc-reposo", type=int)
    p.add_argument("--fc-max", type=int)
    p.add_argument("--factor-neat", type=float, help="1.2 sedentario · 1.35 oficina con algo de movimiento · 1.5 activo")
    p = sub.add_parser("analisis")
    p.add_argument("alias")
    p.add_argument("--semana", help="lunes de la semana a planificar (AAAA-MM-DD)")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("perfil-cargar")
    p.add_argument("alias")
    p.add_argument("yaml")
    p = sub.add_parser("paquete")
    p.add_argument("alias")
    p.add_argument("carpeta", help="carpeta de datos del perfil (datos/<perfil>)")
    p.add_argument("--semana")
    p.add_argument("--nota", default="")
    p = sub.add_parser("plan-importar")
    p.add_argument("alias")
    p.add_argument("carpeta")
    p.add_argument("respuesta", help="fichero con la respuesta de Claude (.md o .json)")
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

    elif a.cmd == "ajustes":
        pid = ingesta.perfil_id(conn, a.alias)
        aj = motor.guardar_ajustes(conn, pid, objetivo=a.objetivo, nivel=a.nivel, fc_reposo=a.fc_reposo,
                                   fc_max=a.fc_max, factor_neat=a.factor_neat)
        print(json.dumps(aj, ensure_ascii=False))
    elif a.cmd == "analisis":
        pid = ingesta.perfil_id(conn, a.alias)
        r = motor.analizar(conn, pid, date.fromisoformat(a.semana) if a.semana else None)
        print(json.dumps(r, ensure_ascii=False, indent=2, default=str) if a.json else _informe(r))
    elif a.cmd == "perfil-cargar":
        pid = ingesta.perfil_id(conn, a.alias)
        aj = exportar.cargar_perfil_yaml(conn, pid, a.yaml)
        pp = aj["perfil_plan"]
        print(f"Perfil de plan cargado: objetivo {pp['objetivo']['principal']}, {pp['sesiones_semana']}, "
              f"{len(pp['disponibilidad'])} franjas, {len(pp['horario_comidas'])} comidas")
    elif a.cmd == "paquete":
        pid = ingesta.perfil_id(conn, a.alias)
        semana = date.fromisoformat(a.semana) if a.semana else motor.lunes(date.today() + timedelta(days=7 if date.today().weekday() >= 5 else 0))
        paq, avisos = exportar.construir(conn, pid, semana, a.nota)
        ruta = exportar.guardar(conn, pid, paq, a.carpeta)
        for x in avisos:
            print("⚠ ", x)
        o = paq["objetivos"]
        print(f"Paquete {paq['paquete_id'][:8]} · semana {paq['semana']['inicio']} · fase {paq['semana']['fase']}")
        print(f"  Entreno: {o['entreno']['sesiones_fuerza']} fuerza + {o['entreno']['sesiones_cardio']} cardio · Z2 ≥{o['entreno']['min_z2_semana']} min · "
              f"{len(o['entreno']['progresiones'])} progresiones · {len(paq['catalogo_ejercicios'])} ejercicios en catálogo")
        print(f"  Nutrición: {o['nutricion']['kcal_entreno']}/{o['nutricion']['kcal_descanso']} kcal · {o['nutricion']['proteina_g']} g proteína")
        print(f"  → {ruta}  ({ruta.stat().st_size // 1024} KB)")
    elif a.cmd == "plan-importar":
        pid = ingesta.perfil_id(conn, a.alias)
        r = importar_plan.importar(conn, pid, a.respuesta, a.carpeta)
        print(f"Plan {r['estado'].upper()} · {r['bloqueos']} bloqueos · {r['avisos']} avisos")
        for h in r["hallazgos"]:
            print(f"  {'✘' if h['severidad'] == 'bloqueo' else '·'} [{h['regla']}] {h['mensaje']}")
        print("  →", r.get("plan") or f"lleva a Claude el fichero de corrección: {r['correccion']}")


def _informe(r: dict) -> str:
    s, e, sa, n = r["semana"], r["estado"], r["semana_anterior"], r["nutricion"]
    c, t = e["composicion_actual"] or {}, e["tendencia_4s"]
    L = [f"══ Semana {s['inicio']} → {s['fin']} · fase sugerida: {s['fase_sugerida'].upper()}",
         f"   Días sin entrenar: {s['dias_sin_entrenar']} · parón ≥14 d en las últimas semanas: {'sí' if s['parada_reciente_14d'] else 'no'}",
         f"── Composición: {c.get('peso_kg')} kg · grasa {c.get('grasa_pct')} % · tendencia peso "
         f"{t['peso_kg_sem'] if t['peso_kg_sem'] is not None else 'n/d (faltan mediciones)'} kg/sem",
         f"── Semana anterior: {sa['sesiones_realizadas']} sesiones ({sa['sesiones_fuerza']} de fuerza) · "
         f"TRIMP {sa['carga']['trimp_semana']} · ACWR {sa['carga']['acwr']} · volumen fuerza {sa['carga']['volumen_fuerza_kg']:.0f} kg",
         f"   Min por zona: {sa['carga']['minutos_por_zona']}",
         f"── FC máx {e['cardio_referencia']['fc_max_estimada']} · Z2 {e['cardio_referencia']['zonas_fc']['Z2']} ppm",
         *[f"⚠  {x}" for x in r["alertas"]],
         "── Fuerza: prescripción para la semana"]
    for p in r["fuerza"]["prescripciones"][:12]:
        peso = f"{p['peso_kg']:g} kg" if p["peso_kg"] else "peso corporal"
        L.append(f"   {p['ejercicio'][:34]:34} {p['series']}×{p['reps_min']}-{p['reps_max']} @ {peso:13} [{p['motivo']}]  ← {p['historial']}")
    est = [x["ejercicio"] for x in r["fuerza"]["progresion"] if x["estancado"]]
    if est:
        L.append(f"   Estancados (4 sem sin progreso): {', '.join(est)}")
    if n:
        L += [f"── Nutrición: entreno {n['kcal_entreno']} kcal · descanso {n['kcal_descanso']} kcal · proteína {n['proteina_g']} g · "
              f"grasa ≥{n['grasa_g_min']} g · HC {n['carbohidratos_g_entreno']}/{n['carbohidratos_g_descanso']} g · fibra ≥{n['fibra_g_min']} g · agua {n['agua_ml']} ml",
              f"   {n['base_calculo']}"]
    return "\n".join(L)


if __name__ == "__main__":
    import sys
    try:
        main()
    except (ValueError, LookupError, FileNotFoundError) as e:
        print(f"✘ {e}", file=sys.stderr)
        sys.exit(1)
