"""Importación del perfil médico (.md devuelto por el prompt 01).

Decisión de diseño: solo se conserva el bloque YAML validado. El texto narrativo se
muestra al usuario para revisión y se descarta; se guarda su SHA-256 para trazabilidad.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ESQUEMA = Path(__file__).resolve().parents[2] / "schemas" / "perfil_medico.schema.json"
_VALIDADOR = Draft202012Validator(json.loads(ESQUEMA.read_text(encoding="utf-8")))


@dataclass
class ResultadoPerfilMedico:
    yaml_datos: dict | None
    narrativa: str                 # para mostrar en la revisión; NO se guarda
    sha256: str
    errores: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def valido(self) -> bool:
        return not self.errores and self.yaml_datos is not None


def importar(texto: str | bytes) -> ResultadoPerfilMedico:
    if isinstance(texto, bytes):
        texto = texto.decode("utf-8-sig")
    sha = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    t = texto.lstrip()
    if t.startswith("```"):  # el LLM a veces envuelve todo en un bloque de código
        t = t.split("\n", 1)[1].rsplit("```", 1)[0]
    if not t.startswith("---"):
        return ResultadoPerfilMedico(None, texto, sha, ["el documento no empieza con un bloque YAML '---'"])
    try:
        _, fm, narrativa = t.split("---", 2)
        datos = yaml.safe_load(fm)
    except (ValueError, yaml.YAMLError) as e:
        return ResultadoPerfilMedico(None, texto, sha, [f"YAML ilegible: {e}"])
    datos = json.loads(json.dumps(datos, default=str))  # fechas YAML → texto ISO

    r = ResultadoPerfilMedico(datos, narrativa.strip(), sha)
    r.errores = [f"/{'/'.join(map(str, e.path))}: {e.message}" for e in _VALIDADOR.iter_errors(datos)]
    if r.errores:
        return r

    ids = {f["id"] for f in datos["fuentes"]} | {"declarado_usuario"}
    for seccion in ("condiciones", "medicacion", "alergias_intolerancias", "analitica",
                    "restricciones_ejercicio", "restricciones_dieta"):
        for item in datos.get(seccion, []):
            if item.get("fuente") not in ids:
                r.errores.append(f"{seccion}: fuente {item.get('fuente')!r} no está en 'fuentes'")
    if datos["requiere_valoracion_medica"]["valor"]:
        r.avisos.append(f"requiere valoración médica: {datos['requiere_valoracion_medica']['motivo']}")
    if datos["confianza"] == "baja":
        r.avisos.append("confianza baja en la extracción: revisa el perfil con atención")
    if any(a["gravedad"] in ("grave", "anafilaxia") for a in datos["alergias_intolerancias"]):
        r.avisos.append("hay alergias graves: se tratarán como prohibición absoluta, incluidas trazas")
    return r
