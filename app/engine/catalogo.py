"""Catálogo de ejercicios: grupo muscular, patrones de movimiento y material.

Los patrones usan el mismo vocabulario que restricciones_ejercicio.ambito del perfil médico,
más patrones descriptivos (empuje_horizontal, traccion_vertical…) para el diseño de rutinas.
Mientras no haya API de Hevy, el exercise_template_id es provisional: 'hevy:<nombre>'.
"""
from __future__ import annotations

# (palabras clave en el nombre de Hevy) → (grupo, patrones)
REGLAS: list[tuple[tuple[str, ...], str, list[str]]] = [
    (("squat",), "pierna", ["carga_axial", "rodilla_flexion_profunda", "valsalva"]),
    (("romanian deadlift", "deadlift"), "pierna", ["bisagra_cadera", "carga_axial", "flexion_columna_cargada", "agarre", "valsalva"]),
    (("leg press",), "pierna", ["rodilla_flexion_profunda", "valsalva"]),
    (("lunge", "split squat"), "pierna", ["rodilla_flexion_profunda", "unilateral"]),
    (("hip thrust", "glute bridge"), "gluteo", ["bisagra_cadera"]),
    (("leg extension",), "pierna", ["extension_rodilla"]),
    (("leg curl",), "pierna", ["flexion_rodilla"]),
    (("calf",), "pierna", ["tobillo"]),
    (("bench press", "chest press", "push up", "pushup"), "pecho", ["empuje_horizontal", "valsalva"]),
    (("incline bench", "incline press"), "pecho", ["empuje_horizontal", "empuje_inclinado"]),
    (("chest fly", "pec deck", "cable fly"), "pecho", ["aduccion_hombro"]),
    (("dip",), "triceps", ["empuje_vertical_abajo", "hombro_extension"]),
    (("overhead press", "shoulder press", "military"), "hombro", ["overhead", "carga_axial", "valsalva"]),
    (("lateral raise",), "hombro", ["abduccion_hombro"]),
    (("face pull",), "hombro", ["traccion_horizontal", "hombro_rotacion_externa"]),
    (("pull up", "chin up"), "espalda", ["traccion_vertical", "agarre"]),
    (("lat pulldown",), "espalda", ["traccion_vertical", "agarre"]),
    (("row",), "espalda", ["traccion_horizontal", "agarre"]),
    (("curl",), "biceps", ["flexion_codo", "agarre"]),
    (("triceps", "skullcrusher", "pressdown"), "triceps", ["extension_codo"]),
    (("plank", "hollow", "side plank"), "core", ["isometrico_intenso", "antiextension"]),
    (("crunch", "leg raise", "reverse crunch"), "core", ["flexion_columna"]),
    (("russian twist",), "core", ["rotacion_columna_cargada"]),
    (("mountain climber", "hiit", "burpee", "jump"), "cardio", ["alta_intensidad_cardio", "impacto", "saltos"]),
    (("running",), "cardio", ["carrera", "impacto"]),
]
MATERIAL = [("(barbell)", "barra"), ("(dumbbell)", "mancuernas"), ("(machine)", "maquina"), ("(cable)", "polea"),
            ("machine", "maquina"), ("cable", "polea"), ("pulldown", "polea")]


def clasificar(nombre: str, ids: dict[str, str] | None = None) -> dict:
    n = nombre.lower()
    grupo, patrones = "otro", []
    for claves, g, p in REGLAS:
        if any(k in n for k in claves):
            grupo, patrones = g, p
            break
    material = next((m for k, m in MATERIAL if k in n), "peso_corporal")
    if "(weighted)" in n:
        material = "lastre"
    tid = (ids or {}).get(nombre.lower()) or f"hevy:{nombre}"
    return {"exercise_template_id": tid, "nombre": nombre, "grupo": grupo,
            "patrones": patrones, "material": material}


def construir(nombres: list[str], prohibidos: set[str], ids: dict[str, str] | None = None) -> tuple[list[dict], list[dict]]:
    """Devuelve (catálogo permitido, excluidos con motivo)."""
    permitidos, excluidos = [], []
    for nombre in sorted(set(nombres)):
        e = clasificar(nombre, ids)
        choque = prohibidos.intersection(e["patrones"])
        (excluidos if choque else permitidos).append({**e, **({"motivo": sorted(choque)} if choque else {})})
    return permitidos, excluidos
