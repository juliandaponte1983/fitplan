"""Cliente de la API pública de Hevy (requiere Hevy Pro).

Base https://api.hevyapp.com · cabecera 'api-key'. Se usa para:
- leer entrenamientos nuevos (equivalente al CSV, misma clave de deduplicación),
- leer el catálogo de ejercicios (exercise_template_id reales),
- crear/actualizar las rutinas del plan en una carpeta 'FitPlan'.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

BASE = "https://api.hevyapp.com"


class ErrorHevy(RuntimeError):
    pass


class ClienteHevy:
    def __init__(self, clave: str, transporte: httpx.BaseTransport | None = None):
        self._http = httpx.Client(base_url=BASE, headers={"api-key": clave, "accept": "application/json"},
                                  timeout=30, transport=transporte)

    def _pedir(self, metodo: str, ruta: str, **kw) -> Any:
        r = self._http.request(metodo, ruta, **kw)
        if r.status_code == 401:
            raise ErrorHevy("clave de API de Hevy no válida o sin Hevy Pro")
        if r.status_code >= 400:
            raise ErrorHevy(f"Hevy {metodo} {ruta} → {r.status_code}: {r.text[:200]}")
        return r.json() if r.content else None

    def _paginar(self, ruta: str, clave: str, tam: int, **params) -> list[dict]:
        out, pagina = [], 1
        while True:
            d = self._pedir("GET", ruta, params={"page": pagina, "pageSize": tam, **params})
            out += d.get(clave, [])
            if pagina >= int(d.get("page_count", 1) or 1):
                return out
            pagina += 1

    # ------------------------------------------------------------- lectura
    def probar(self) -> dict:
        d = self._pedir("GET", "/v1/workouts/count")
        return {"entrenos": d.get("workout_count", d)}

    def entrenos(self) -> list[dict]:
        return self._paginar("/v1/workouts", "workouts", 10)

    def eventos_desde(self, desde: datetime) -> list[dict]:
        """Entrenos creados/actualizados/borrados desde una fecha (sincronización incremental)."""
        return self._paginar("/v1/workouts/events", "events", 10, since=desde.isoformat())

    def plantillas(self) -> list[dict]:
        return self._paginar("/v1/exercise_templates", "exercise_templates", 100)

    def rutinas(self) -> list[dict]:
        return self._paginar("/v1/routines", "routines", 10)

    def carpetas(self) -> list[dict]:
        return self._paginar("/v1/routine_folders", "routine_folders", 10)

    # ------------------------------------------------------------- escritura
    def crear_carpeta(self, titulo: str) -> dict:
        d = self._pedir("POST", "/v1/routine_folders", json={"routine_folder": {"title": titulo}})
        f = d.get("routine_folder", d)
        return f[0] if isinstance(f, list) else f

    def crear_rutina(self, rutina: dict, carpeta_id: int | None) -> dict:
        d = self._pedir("POST", "/v1/routines", json={"routine": {**rutina, "folder_id": carpeta_id}})
        r = d.get("routine", d)
        return r[0] if isinstance(r, list) else r

    def actualizar_rutina(self, rutina_id: str, rutina: dict) -> dict:
        d = self._pedir("PUT", f"/v1/routines/{rutina_id}", json={"routine": rutina})
        r = d.get("routine", d)
        return r[0] if isinstance(r, list) else r


def rutina_a_hevy(r: dict) -> dict:
    """Rutina del plan (plan_semanal/v1) → cuerpo de rutina de la API de Hevy."""
    ejercicios = []
    for e in r["ejercicios"]:
        series = []
        for s in e["series"]:
            x: dict[str, Any] = {"type": s["tipo"] if s["tipo"] in ("warmup", "normal", "failure", "dropset") else "normal",
                                 "weight_kg": s.get("peso_kg"), "reps": s.get("reps"),
                                 "duration_seconds": s.get("duracion_s"), "distance_meters": None, "custom_metric": None}
            if s.get("reps_rango"):
                x["rep_range"] = {"start": s["reps_rango"][0], "end": s["reps_rango"][1]}
                x["reps"] = None
            series.append(x)
        ejercicios.append({"exercise_template_id": e["exercise_template_id"], "superset_id": e.get("superset_id"),
                           "rest_seconds": e.get("descanso_s"), "notes": e.get("notas") or None, "sets": series})
    return {"title": r["titulo"], "notes": r.get("notas") or None, "exercises": ejercicios}
