"""Carga de entrenamiento: TRIMP de Banister, carga aguda/crónica y ACWR."""
from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import date, timedelta


def trimp_banister(fc: list[tuple[int, int]], fc_reposo: int, fc_max: int, sexo: str = "H") -> float:
    """TRIMP = Σ Δt(min) · HRr · a · e^(b·HRr).  a,b = 0.64,1.92 (H) · 0.86,1.67 (M).
    fc: [(segundos desde inicio, ppm)]. Huecos > 60 s no se cuentan (pausas / pérdida de señal)."""
    if len(fc) < 2 or fc_max <= fc_reposo:
        return 0.0
    a, b = (0.64, 1.92) if sexo == "H" else (0.86, 1.67)
    total = 0.0
    for (t0, h0), (t1, h1) in zip(fc, fc[1:]):
        dt = t1 - t0
        if dt <= 0 or dt > 60:
            continue
        hrr = min(max(((h0 + h1) / 2 - fc_reposo) / (fc_max - fc_reposo), 0.0), 1.0)
        total += dt / 60 * hrr * a * math.exp(b * hrr)
    return round(total, 1)


def trimp_desde_zonas(zonas_s: dict[str, float]) -> float:
    """Aproximación de Edwards cuando no hay serie de FC: min en Zi × i."""
    return round(sum(float(v) / 60 * int(k[1:]) for k, v in zonas_s.items() if k != "z0"), 1)


def carga_diaria(cargas: Iterable[tuple[date, float]]) -> dict[date, float]:
    d: dict[date, float] = {}
    for dia, c in cargas:
        d[dia] = d.get(dia, 0.0) + c
    return d


def acwr(diaria: dict[date, float], hoy: date) -> dict:
    """Carga aguda (7 d), crónica (media semanal de 28 d) y ratio. None si no hay base crónica."""
    aguda = sum(v for d, v in diaria.items() if hoy - timedelta(days=6) <= d <= hoy)
    cron28 = sum(v for d, v in diaria.items() if hoy - timedelta(days=27) <= d <= hoy)
    cronica = cron28 / 4
    return {
        "aguda_7d": round(aguda, 1),
        "cronica_semanal_28d": round(cronica, 1),
        "acwr": round(aguda / cronica, 2) if cronica > 0 else None,
    }
