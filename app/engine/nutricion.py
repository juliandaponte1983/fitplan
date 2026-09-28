"""Objetivos nutricionales: TMB, gasto, déficit/superávit adaptativo y macros."""
from __future__ import annotations

from dataclasses import dataclass

AJUSTE_OBJETIVO = {          # fracción sobre el gasto de mantenimiento
    "perder_grasa": -0.20,
    "recomposicion": -0.10,
    "ganar_musculo": 0.08,
    "rendimiento": 0.0,
    "salud_general": -0.05,
}
RITMO_OBJETIVO_PCT_SEM = {   # cambio de peso buscado (% del peso por semana)
    "perder_grasa": (-1.0, -0.5),
    "recomposicion": (-0.5, -0.1),
    "ganar_musculo": (0.1, 0.35),
}


def tmb(peso: float, altura_cm: float, edad: int, sexo: str, masa_magra: float | None = None) -> tuple[float, str]:
    if masa_magra:
        return round(370 + 21.6 * masa_magra), "Katch-McArdle"
    s = 5 if sexo == "H" else -161
    return round(10 * peso + 6.25 * altura_cm - 5 * edad + s), "Mifflin-St Jeor"


@dataclass
class ObjetivosNutricion:
    kcal_entreno: int
    kcal_descanso: int
    proteina_g: int
    grasa_g_min: int
    carbohidratos_g_entreno: int
    carbohidratos_g_descanso: int
    fibra_g_min: int
    agua_ml: int
    tolerancia_kcal_pct: float
    base_calculo: str


def objetivos(peso: float, altura_cm: float, edad: int, sexo: str, objetivo: str,
              masa_magra: float | None, kcal_ejercicio_dia: float, factor_neat: float = 1.35,
              tendencia_kg_sem: float | None = None, limites: dict | None = None) -> ObjetivosNutricion:
    """kcal_ejercicio_dia: media diaria de kcal ACTIVAS de ejercicio de las últimas 4 semanas."""
    limites = limites or {}
    base, formula = tmb(peso, altura_cm, edad, sexo, masa_magra)
    mantenimiento = base * factor_neat + kcal_ejercicio_dia
    ajuste = AJUSTE_OBJETIVO.get(objetivo, 0.0)
    nota_tend = "sin tendencia suficiente"
    if tendencia_kg_sem is not None and objetivo in RITMO_OBJETIVO_PCT_SEM:
        lo, hi = (x * peso / 100 for x in RITMO_OBJETIVO_PCT_SEM[objetivo])
        if tendencia_kg_sem > hi:        # pierde menos (o gana más) de lo buscado
            ajuste -= 0.05
            nota_tend = f"tendencia {tendencia_kg_sem:+.2f} kg/sem más lenta que el objetivo → −5 %"
        elif tendencia_kg_sem < lo:      # pierde demasiado rápido
            ajuste += 0.05
            nota_tend = f"tendencia {tendencia_kg_sem:+.2f} kg/sem más rápida que el objetivo → +5 %"
        else:
            nota_tend = f"tendencia {tendencia_kg_sem:+.2f} kg/sem dentro del objetivo"
    media = mantenimiento * (1 + ajuste)
    suelo = max(base, limites.get("kcal_min_diarias") or 0)   # nunca por debajo de la TMB
    kcal_ent, kcal_desc = max(media * 1.06, suelo), max(media * 0.92, suelo)

    ref_prot = masa_magra * 2.3 if masa_magra else peso * 1.8
    if limites.get("proteina_max_g_kg"):
        ref_prot = min(ref_prot, limites["proteina_max_g_kg"] * peso)
    prot = round(ref_prot / 5) * 5
    grasa = round(peso * 0.8)
    carb = lambda k: max(round((k - prot * 4 - grasa * 9) / 4), 0)
    return ObjetivosNutricion(
        kcal_entreno=round(kcal_ent / 10) * 10, kcal_descanso=round(kcal_desc / 10) * 10,
        proteina_g=prot, grasa_g_min=grasa,
        carbohidratos_g_entreno=carb(kcal_ent), carbohidratos_g_descanso=carb(kcal_desc),
        fibra_g_min=round(14 * media / 1000), agua_ml=round(peso * 35 / 100) * 100,
        tolerancia_kcal_pct=5,
        base_calculo=(f"TMB {base:.0f} ({formula}) × NEAT {factor_neat} + ejercicio {kcal_ejercicio_dia:.0f} kcal/día "
                      f"= mantenimiento {mantenimiento:.0f}; objetivo {objetivo} ({ajuste:+.0%}); {nota_tend}"),
    )
