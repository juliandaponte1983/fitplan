"""Historial por ejercicio, 1RM estimado, estancamiento y doble progresión."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

PERIODIZACION = json.loads((Path(__file__).resolve().parents[2] / "data" / "periodizacion.json").read_text(encoding="utf-8"))


def e1rm(peso: float | None, reps: int | None) -> float | None:
    """Epley, fiable hasta ~12 repeticiones; por encima se limita a 12."""
    if not peso or not reps:
        return None
    return round(peso * (1 + min(reps, 12) / 30), 1)


@dataclass
class SesionEjercicio:
    fecha: datetime
    series: list[tuple[float | None, int | None, float | None]]   # (peso, reps, rpe) de trabajo

    @property
    def top(self) -> tuple[float | None, int | None]:
        return max(self.series, key=lambda s: ((s[0] or 0), (s[1] or 0)))[:2]

    @property
    def mejor_e1rm(self) -> float | None:
        v = [e1rm(p, r) for p, r, _ in self.series if p and r]
        return max(v) if v else None

    @property
    def volumen(self) -> float:
        return sum((p or 0) * (r or 0) for p, r, _ in self.series)


@dataclass
class HistorialEjercicio:
    ejercicio: str
    sesiones: list[SesionEjercicio] = field(default_factory=list)

    def ultimas(self, n: int) -> list[SesionEjercicio]:
        return self.sesiones[-n:]

    @property
    def peso_corporal(self) -> bool:
        return all(p is None for s in self.sesiones for p, _, _ in s.series)

    def estancado(self, semanas: int = 4) -> bool:
        """Sin mejora de peso ni reps en el top set durante `semanas` (con ≥ 3 sesiones en ese periodo)."""
        if len(self.sesiones) < 3:
            return False
        fin = self.sesiones[-1].fecha
        ventana = [s for s in self.sesiones if (fin - s.fecha).days <= semanas * 7]
        previas = [s for s in self.sesiones if (fin - s.fecha).days > semanas * 7]
        if len(ventana) < 3 or not previas:
            return False
        mejor_prev = max((s.top[0] or 0, s.top[1] or 0) for s in previas)
        mejor_vent = max((s.top[0] or 0, s.top[1] or 0) for s in ventana)
        return mejor_vent <= mejor_prev


def historiales(filas) -> dict[str, HistorialEjercicio]:
    """filas: iterable de (inicio_utc, ejercicio, tipo, peso_kg, reps, rpe) ordenadas por fecha."""
    h: dict[str, HistorialEjercicio] = {}
    actual: dict[str, SesionEjercicio] = {}
    for inicio, ej, tipo, peso, reps, rpe in filas:
        if tipo == "warmup" or (reps is None and peso is None):
            continue
        f = datetime.fromisoformat(inicio)
        he = h.setdefault(ej, HistorialEjercicio(ej))
        ses = actual.get(ej)
        if ses is None or ses.fecha != f:
            ses = SesionEjercicio(f, [])
            he.sesiones.append(ses)
            actual[ej] = ses
        ses.series.append((peso, reps, rpe))
    return h


def incremento_kg(ejercicio: str) -> float:
    inc = PERIODIZACION["progresion"]["incremento_kg"]
    e = ejercicio.lower()
    if "(barbell)" in e:
        pierna = any(k in e for k in ("squat", "deadlift", "hip thrust", "lunge", "leg"))
        return inc["tren_inferior_barra"] if pierna else inc["tren_superior_barra"]
    if "(dumbbell)" in e:
        return inc["mancuerna"]
    return inc["maquina_polea"]


def _redondear(peso: float, paso: float) -> float:
    return round(round(peso / paso) * paso, 2)


@dataclass
class Prescripcion:
    ejercicio: str
    series: int
    reps_min: int
    reps_max: int
    peso_kg: float | None
    rpe_objetivo: float | None
    motivo: str
    historial: str


def rango_por_defecto(ejercicio: str) -> tuple[int, int]:
    """Básicos con barra 8–12; accesorios (mancuerna, máquina, polea, peso corporal) 10–15."""
    e = ejercicio.lower()
    basico = "(barbell)" in e and any(k in e for k in ("bench", "squat", "deadlift", "row", "press", "hip thrust"))
    return (8, 12) if basico else (10, 15)


def peso_trabajo(ses: SesionEjercicio) -> float | None:
    """Peso más repetido en las series de trabajo (en empate, el mayor)."""
    pesos = [p for p, _, _ in ses.series if p]
    if not pesos:
        return None
    return max(set(pesos), key=lambda x: (pesos.count(x), x))


def prescribir(h: HistorialEjercicio, fase: str, rango: tuple[int, int] | None = None,
               incremento_max_pct: float | None = None, permitir_subir_peso: bool = True) -> Prescripcion:
    """Doble progresión sobre la última sesión del ejercicio, modulada por la fase del bloque.

    - Todas las series al peso de trabajo en reps_max → subir peso (paso del material, tope %).
    - Dos sesiones seguidas con alguna serie < reps_min → bajar ~5 %.
    - Si no → mismo peso, buscar más repeticiones.
    - Reintroducción / descarga → % del peso de trabajo según periodizacion.json.
    El estancamiento se informa aparte (HistorialEjercicio.estancado) y se decide al cambiar de bloque.
    """
    fases = {f["fase"]: f for f in PERIODIZACION["bloque_inicial"] + PERIODIZACION["bloque_estandar"]}
    rpe = fases.get(fase, {}).get("rpe_objetivo")
    tope = (incremento_max_pct or PERIODIZACION["progresion"]["incremento_max_pct"]) / 100
    ult = h.sesiones[-1]
    n = max(1, len(ult.series))
    if rango is None:
        rango = rango_por_defecto(h.ejercicio)
        habituales = sorted(r for s in h.ultimas(3) for _, r, _ in s.series if r)
        if habituales:
            med = habituales[len(habituales) // 2]
            if med < rango[0]:          # el usuario trabaja más pesado que el rango estándar: se respeta
                rango = (max(med - 2, 4), med + 2)
    rmin, rmax = rango
    hist = ", ".join(f"{p:g}×{r}" if p else f"{r}" for p, r, _ in ult.series if r)
    hist = f"{ult.fecha:%d/%m}: {hist}"
    pt = peso_trabajo(ult)

    if h.peso_corporal or pt is None:
        return Prescripcion(h.ejercicio, n, rmin, rmax, None, rpe, "subir_reps", hist)

    paso = incremento_kg(h.ejercicio)
    if fase in ("reintroduccion", "descarga"):
        factor = fases[fase].get("intensidad_pct_ultimo_top_set", 90) / 100
        return Prescripcion(h.ejercicio, max(2, n - 1) if fase == "descarga" else n, rmin, rmax,
                            _redondear(pt * factor, paso), rpe, "descarga", hist)

    reps_al_peso = [r for p, r, _ in ult.series if p == pt and r]
    if permitir_subir_peso and reps_al_peso and all(r >= rmax for r in reps_al_peso):
        if "(barbell)" in h.ejercicio.lower():   # con barra hay discos pequeños: se respeta el tope %
            peso = _redondear(pt + min(paso, max(pt * tope, paso / 2)), paso / 2)
        else:                                     # mancuernas y máquinas van por saltos fijos
            peso = pt + paso
        return Prescripcion(h.ejercicio, n, rmin, rmax, peso, rpe, "subir_peso", hist)
    fallos = [s for s in h.ultimas(2) if any((r or 0) < rmin for p, r, _ in s.series if p == peso_trabajo(s))]
    if len(fallos) == 2:
        return Prescripcion(h.ejercicio, n, rmin, rmax, _redondear(pt * 0.95, paso), rpe, "mantener", hist)
    return Prescripcion(h.ejercicio, n, rmin, rmax, pt, rpe, "subir_reps" if permitir_subir_peso or not reps_al_peso or not all(r >= rmax for r in reps_al_peso) else "mantener", hist)
