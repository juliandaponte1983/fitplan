"""Importación de mediciones de composición corporal (JSON devuelto por el prompt 02).

Valida contra schemas/composicion_corporal.schema.json y aplica las comprobaciones
cruzadas del prompt. Devuelve la medición y la lista de problemas encontrados.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator

ESQUEMA = Path(__file__).resolve().parents[2] / "schemas" / "composicion_corporal.schema.json"
_VALIDADOR = Draft202012Validator(json.loads(ESQUEMA.read_text(encoding="utf-8")))


@dataclass
class ResultadoMedicion:
    datos: dict
    fecha_hora: datetime
    errores: list[str] = field(default_factory=list)   # bloquean la importación
    avisos: list[str] = field(default_factory=list)    # requieren confirmación del usuario

    @property
    def valido(self) -> bool:
        return not self.errores


def _extraer_json(texto: str) -> dict:
    """Acepta el JSON puro o la respuesta del LLM con un bloque ```json."""
    t = texto.strip()
    if "```" in t:
        t = t.split("```", 2)[1]
        t = t[4:] if t.startswith("json") else t
    return json.loads(t)


def importar(fuente: str | dict, perfil: dict | None = None, anterior: dict | None = None) -> ResultadoMedicion:
    """perfil: {'sexo','edad','altura_cm'} del perfil de la app; anterior: última medición guardada."""
    datos = fuente if isinstance(fuente, dict) else _extraer_json(fuente)
    errores = [f"/{'/'.join(map(str, e.path))}: {e.message}" for e in _VALIDADOR.iter_errors(datos)]
    if errores:
        return ResultadoMedicion(datos, datetime.min, errores)

    fh = datetime.fromisoformat(datos["fecha_hora"])
    r = ResultadoMedicion(datos, fh)
    c, p = datos["composicion"], datos["perfil"]

    if fh > datetime.now():
        r.errores.append(f"fecha futura: {fh}")
    peso, grasa, pct = c["peso_kg"], c.get("grasa_kg"), c.get("grasa_pct")
    if grasa is not None and pct is not None and abs(grasa / peso * 100 - pct) > 1:
        r.avisos.append(f"grasa: {grasa} kg / {peso} kg = {grasa / peso * 100:.1f} % ≠ {pct} %")
    if c.get("imc") is not None:
        imc = peso / (p["altura_cm"] / 100) ** 2
        if abs(imc - c["imc"]) > 0.3:
            r.avisos.append(f"IMC calculado {imc:.1f} ≠ informe {c['imc']}")
    if grasa is not None and c.get("masa_magra_kg") is not None and abs(peso - grasa - c["masa_magra_kg"]) > 0.5:
        r.avisos.append(f"masa magra: {peso} − {grasa} = {peso - grasa:.1f} ≠ {c['masa_magra_kg']}")

    if perfil:
        dif = [k for k in ("sexo", "altura_cm") if perfil.get(k) is not None and perfil[k] != p[k]]
        if perfil.get("edad") is not None and abs(perfil["edad"] - p["edad"]) > 1:
            dif.append("edad")
        if dif:
            r.avisos.append(f"el informe no coincide con el perfil en {dif}: ¿la báscula usó otro usuario?")
    if anterior:
        delta = peso - anterior["composicion"]["peso_kg"]
        if abs(delta) > 2:
            r.avisos.append(f"cambio de peso de {delta:+.1f} kg respecto a la medición anterior: confirmar")
    for campo in datos.get("extraccion", {}).get("campos_dudosos", []):
        r.avisos.append(f"campo dudoso según la extracción: {campo}")
    return r
