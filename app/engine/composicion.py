"""Tendencia de composición corporal (regresión lineal simple)."""
from __future__ import annotations

from datetime import datetime, timedelta


def pendiente_semanal(puntos: list[tuple[datetime, float]], dias: int = 28) -> float | None:
    """kg (o %) por semana en los últimos `dias`. Necesita ≥ 2 mediciones separadas ≥ 5 días."""
    if not puntos:
        return None
    fin = max(p[0] for p in puntos)
    v = [(p[0], p[1]) for p in puntos if p[1] is not None and fin - p[0] <= timedelta(days=dias)]
    if len(v) < 2 or (max(x for x, _ in v) - min(x for x, _ in v)).days < 5:
        return None
    xs = [(x - v[0][0]).total_seconds() / 86400 for x, _ in v]
    ys = [y for _, y in v]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    den = sum((x - mx) ** 2 for x in xs)
    return round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den * 7, 2) if den else None
