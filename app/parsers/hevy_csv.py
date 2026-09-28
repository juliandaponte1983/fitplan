"""Lector del CSV de exportación de Hevy (Ajustes → Exportar datos).

- Acepta fechas en español ("25 sept 2026, 7:04") y en inglés ("25 Sep 2026, 07:04").
- Cada serie recibe una clave estable para deduplicar entre exportaciones sucesivas:
  inicio del entreno | orden del ejercicio dentro del entreno | set_index.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

MESES = {
    "ene": 1, "jan": 1, "feb": 2, "mar": 3, "abr": 4, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11,
    "dic": 12, "dec": 12,
}
_RE_FECHA = re.compile(r"^\s*(\d{1,2})\s+([A-Za-zé.]+)\s+(\d{4}),?\s+(\d{1,2}):(\d{2})\s*$")
COLUMNAS = {"title", "start_time", "end_time", "exercise_title", "set_index", "set_type",
            "weight_kg", "reps", "distance_km", "duration_seconds", "rpe"}


def parse_fecha(texto: str) -> datetime:
    m = _RE_FECHA.match(texto or "")
    if not m:
        raise ValueError(f"fecha no reconocida: {texto!r}")
    dia, mes, anio, h, mi = m.groups()
    mes = mes.lower().rstrip(".")
    if mes not in MESES:
        raise ValueError(f"mes no reconocido: {mes!r}")
    return datetime(int(anio), MESES[mes], int(dia), int(h), int(mi))


def _num(v: str | None) -> float | None:
    if v is None or str(v).strip() == "":
        return None
    return float(str(v).replace(",", "."))


@dataclass(frozen=True)
class Serie:
    clave: str
    inicio: datetime
    fin: datetime
    titulo: str
    ejercicio: str
    ejercicio_orden: int
    set_index: int
    tipo: str
    peso_kg: float | None
    reps: int | None
    distancia_km: float | None
    duracion_s: float | None
    rpe: float | None
    superset_id: int | None
    notas: str


@dataclass
class Entreno:
    inicio: datetime
    fin: datetime
    titulo: str
    series: list[Serie] = field(default_factory=list)

    @property
    def duracion_min(self) -> float:
        return (self.fin - self.inicio).total_seconds() / 60

    @property
    def volumen_kg(self) -> float:
        return sum((s.peso_kg or 0) * (s.reps or 0) for s in self.series)


@dataclass
class ResultadoHevy:
    series: list[Serie]
    entrenos: list[Entreno]
    errores: list[str]


def leer(fuente: str | Path | bytes) -> ResultadoHevy:
    if isinstance(fuente, bytes):
        texto = fuente.decode("utf-8-sig")
    else:
        texto = Path(fuente).read_text(encoding="utf-8-sig")
    lector = csv.DictReader(io.StringIO(texto))
    faltan = COLUMNAS - set(lector.fieldnames or [])
    if faltan:
        raise ValueError(f"CSV de Hevy sin columnas: {sorted(faltan)}")

    series: list[Serie] = []
    errores: list[str] = []
    orden: dict[datetime, list[str]] = {}  # inicio → ejercicios en orden de aparición
    ultimo: dict[datetime, tuple[str, int]] = {}

    for n, f in enumerate(lector, start=2):
        try:
            inicio, fin = parse_fecha(f["start_time"]), parse_fecha(f["end_time"])
            ej, idx = f["exercise_title"].strip(), int(f["set_index"])
            bloques = orden.setdefault(inicio, [])
            prev = ultimo.get(inicio)
            # nuevo bloque si cambia el ejercicio o si set_index vuelve a 0 con el mismo ejercicio
            if prev is None or prev[0] != ej or idx <= prev[1]:
                bloques.append(ej)
            ultimo[inicio] = (ej, idx)
            eo = len(bloques)
            reps = _num(f["reps"])
            sup = _num(f.get("superset_id"))
            series.append(Serie(
                clave=f"{inicio.isoformat()}|{eo}|{idx}", inicio=inicio, fin=fin,
                titulo=f["title"].strip(), ejercicio=ej, ejercicio_orden=eo, set_index=idx,
                tipo=(f["set_type"] or "normal").strip(), peso_kg=_num(f["weight_kg"]),
                reps=int(reps) if reps is not None else None, distancia_km=_num(f["distance_km"]),
                duracion_s=_num(f["duration_seconds"]), rpe=_num(f["rpe"]),
                superset_id=int(sup) if sup is not None else None,
                notas=(f.get("exercise_notes") or "").strip(),
            ))
        except (ValueError, KeyError) as e:
            errores.append(f"línea {n}: {e}")

    entrenos: dict[datetime, Entreno] = {}
    for s in series:
        entrenos.setdefault(s.inicio, Entreno(s.inicio, s.fin, s.titulo)).series.append(s)
    return ResultadoHevy(series, sorted(entrenos.values(), key=lambda e: e.inicio), errores)


def nuevas(resultado: ResultadoHevy, claves_existentes: set[str]) -> list[Serie]:
    """Series que aún no están en la base de datos (la 'diferencia' de cada exportación)."""
    return [s for s in resultado.series if s.clave not in claves_existentes]
