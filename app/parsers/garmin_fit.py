"""Lector de actividades Garmin (.fit o el .zip que descarga Garmin Connect).

Extrae el resumen de la sesión, el tiempo en zonas de FC, la serie temporal de FC
(para TRIMP en el motor) y, en fuerza, las series activas y los descansos.
No guarda coordenadas GPS: solo se usan para saber que la carrera fue en exterior.
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import fitdecode

# (sport, sub_sport) → tipo_actividad de los esquemas
_TIPOS = {
    ("running", "treadmill"): "cinta",
    ("running", "indoor_running"): "cinta",
    ("running", "virtual_activity"): "cinta",
    ("running", "generic"): "carrera_exterior",
    ("running", "street"): "carrera_exterior",
    ("running", "trail"): "carrera_exterior",
    ("running", "track"): "carrera_exterior",
    ("training", "strength_training"): "fuerza",
    ("training", "cardio_training"): "cardio",
    ("training", "yoga"): "movilidad",
    ("training", "pilates"): "movilidad",
    ("training", "flexibility_training"): "movilidad",
    ("hiit", None): "hiit",
    ("rowing", "indoor_rowing"): "remo",
    ("cycling", "indoor_cycling"): "bici_indoor",
    ("cycling", "virtual_activity"): "bici_indoor",
    ("fitness_equipment", "elliptical"): "eliptica",
    ("fitness_equipment", "indoor_rowing"): "remo",
    ("fitness_equipment", "indoor_cycling"): "bici_indoor",
    ("walking", None): "caminar",
}


def tipo_actividad(sport: str | None, sub_sport: str | None) -> str:
    return _TIPOS.get((sport, sub_sport)) or _TIPOS.get((sport, None)) or "otro"


@dataclass(frozen=True)
class SerieFuerza:
    inicio: datetime
    duracion_s: float
    reps: int | None
    peso_kg: float | None
    descanso_s: float | None       # descanso que sigue a esta serie
    categoria_garmin: int | None   # código de categoría de ejercicio del SDK FIT (None = sin etiquetar)


@dataclass
class ActividadFIT:
    clave: str                     # "<serial>|<time_created ISO>" — única por fichero
    garmin_id: str | None          # id de Garmin Connect (del nombre del fichero)
    tipo: str
    sport: str | None
    sub_sport: str | None
    inicio: datetime               # UTC
    duracion_s: float
    distancia_km: float | None
    kcal: int | None
    fc_media: int | None
    fc_max: int | None
    ascenso_m: int | None
    cadencia_media: int | None
    te_aerobico: float | None
    te_anaerobico: float | None
    carga_garmin: float | None
    zonas_s: dict[str, float] = field(default_factory=dict)   # z0..z5 (z0 = por debajo de Z1)
    limites_zonas: tuple[int, ...] = ()
    fc_max_config: int | None = None
    fc: list[tuple[int, int]] = field(default_factory=list)    # (segundos desde inicio, ppm)
    series: list[SerieFuerza] = field(default_factory=list)
    peso_perfil_garmin_kg: float | None = None
    con_gps: bool = False
    avisos: list[str] = field(default_factory=list)

    @property
    def ritmo_min_km(self) -> str | None:
        if not self.distancia_km:
            return None
        s = self.duracion_s / self.distancia_km
        return f"{int(s // 60)}:{int(round(s % 60)):02d}"


def _bytes_fit(fuente: str | Path | bytes, nombre: str | None) -> tuple[bytes, str | None]:
    if isinstance(fuente, (str, Path)):
        nombre = nombre or Path(fuente).name
        fuente = Path(fuente).read_bytes()
    if fuente[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(fuente)) as zf:
            fits = [n for n in zf.namelist() if n.lower().endswith(".fit")]
            if len(fits) != 1:
                raise ValueError(f"el ZIP debe contener exactamente un .fit (tiene {len(fits)})")
            return zf.read(fits[0]), fits[0]
    return fuente, nombre


def _v(m: fitdecode.FitDataMessage, campo: str):
    try:
        return m.get_value(campo)
    except KeyError:
        return None


def leer(fuente: str | Path | bytes, nombre: str | None = None) -> ActividadFIT:
    datos, nombre = _bytes_fit(fuente, nombre)
    file_id = sesion = tiz = perfil = zonas = None
    registros: list[tuple[datetime, int]] = []
    sets: list[fitdecode.FitDataMessage] = []
    con_gps = False

    with fitdecode.FitReader(io.BytesIO(datos), check_crc=fitdecode.CrcCheck.WARN) as fr:
        for m in fr:
            if not isinstance(m, fitdecode.FitDataMessage):
                continue
            if m.name == "file_id":
                file_id = m
            elif m.name == "session":
                sesion = m
            elif m.name == "time_in_zone" and _v(m, "reference_mesg") == "session":
                tiz = m
            elif m.name == "user_profile":
                perfil = m
            elif m.name == "zones_target":
                zonas = m
            elif m.name == "set":
                sets.append(m)
            elif m.name == "record":
                hr, ts = _v(m, "heart_rate"), _v(m, "timestamp")
                if hr and ts:
                    registros.append((ts, int(hr)))
                if not con_gps and _v(m, "position_lat") is not None:
                    con_gps = True

    if file_id is None or sesion is None:
        raise ValueError("FIT sin file_id o sin session: no es una actividad válida")

    creado = _v(file_id, "time_created")
    serial = _v(file_id, "serial_number")
    inicio = _v(sesion, "start_time")
    sport, sub = _v(sesion, "sport"), _v(sesion, "sub_sport")
    dist = _v(sesion, "total_distance")
    cad = _v(sesion, "avg_running_cadence") or _v(sesion, "avg_cadence")
    garmin_id = None
    if nombre and (mm := re.match(r"(\d{6,})", Path(nombre).name)):
        garmin_id = mm.group(1)

    act = ActividadFIT(
        clave=f"{serial}|{creado.isoformat() if creado else inicio.isoformat()}",
        garmin_id=garmin_id,
        tipo=tipo_actividad(sport, sub), sport=sport, sub_sport=sub,
        inicio=inicio,
        duracion_s=float(_v(sesion, "total_timer_time") or 0),
        distancia_km=round(dist / 1000, 3) if dist else None,
        kcal=_v(sesion, "total_calories"),
        fc_media=_v(sesion, "avg_heart_rate"), fc_max=_v(sesion, "max_heart_rate"),
        ascenso_m=_v(sesion, "total_ascent"),
        cadencia_media=int(cad * 2) if cad and sport == "running" else cad,  # FIT guarda ciclos (1 por zancada doble)
        te_aerobico=_v(sesion, "total_training_effect"),
        te_anaerobico=_v(sesion, "total_anaerobic_training_effect"),
        carga_garmin=round(_v(sesion, "training_load_peak"), 1) if _v(sesion, "training_load_peak") else None,
        con_gps=con_gps,
    )

    if tiz is not None:
        t = _v(tiz, "time_in_hr_zone") or ()
        act.zonas_s = {f"z{i}": round(float(x or 0), 1) for i, x in enumerate(t[:6])}
        act.limites_zonas = tuple(x for x in (_v(tiz, "hr_zone_high_boundary") or ()) if x)
        act.fc_max_config = _v(tiz, "max_heart_rate")
    elif zonas is not None:
        act.fc_max_config = _v(zonas, "max_heart_rate")

    if registros:
        t0 = registros[0][0]
        act.fc = [(int((ts - t0).total_seconds()), hr) for ts, hr in registros]

    if perfil is not None:
        act.peso_perfil_garmin_kg = _v(perfil, "weight")

    # Series de fuerza: 'active' seguidas de 'rest'
    for i, s in enumerate(sets):
        if _v(s, "set_type") != "active":
            continue
        sig = sets[i + 1] if i + 1 < len(sets) else None
        cat = _v(s, "category")
        cat0 = cat[0] if isinstance(cat, tuple) and cat else cat
        act.series.append(SerieFuerza(
            inicio=_v(s, "start_time"), duracion_s=float(_v(s, "duration") or 0),
            reps=_v(s, "repetitions"), peso_kg=_v(s, "weight"),
            descanso_s=float(_v(sig, "duration")) if sig is not None and _v(sig, "set_type") == "rest" else None,
            categoria_garmin=cat0 if isinstance(cat0, int) and cat0 < 65534 else None,
        ))

    # Avisos de calidad del dato
    if act.tipo == "fuerza" and act.series:
        sin_etiqueta = sum(s.categoria_garmin is None for s in act.series)
        if sin_etiqueta:
            act.avisos.append(f"{sin_etiqueta} series sin ejercicio asignado en el reloj")
        ultimo = act.series[-1].descanso_s or 0
        if ultimo > 600:
            act.avisos.append(f"último descanso de {ultimo / 60:.0f} min: probablemente la actividad no se detuvo al terminar")
    if act.tipo == "cinta" and act.distancia_km:
        act.avisos.append("distancia de cinta estimada por el reloj: verificar calibración")
    return act
