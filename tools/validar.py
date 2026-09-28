"""Valida los esquemas de FitPlan y los ejemplos contra ellos.

Uso:  python tools/validar.py
Requiere: pip install jsonschema pyyaml
"""
import json
import pathlib
import sys

import yaml
from jsonschema import Draft202012Validator, FormatChecker

RAIZ = pathlib.Path(__file__).resolve().parent.parent
ESQ = RAIZ / "schemas"
EJ = RAIZ / "examples"

# ejemplo → esquema
PARES = {
    "composicion_2026-09-22.json": "composicion_corporal.schema.json",
    "paquete_2026-09-28.json": "paquete_semanal.schema.json",
    "plan_2026-09-28.json": "plan_semanal.schema.json",
    "perfil_medico_ejemplo.md": "perfil_medico.schema.json",
}


def cargar(p: pathlib.Path):
    if p.suffix == ".md":  # bloque YAML entre las dos primeras líneas '---'
        txt = p.read_text(encoding="utf-8")
        _, fm, _ = txt.split("---", 2)
        # YAML convierte fechas a date → las pasamos a str para JSON Schema
        return json.loads(json.dumps(yaml.safe_load(fm), default=str))
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    errores = 0
    for f in sorted(ESQ.glob("*.json")):
        Draft202012Validator.check_schema(json.loads(f.read_text(encoding="utf-8")))
        print(f"✔ esquema válido: {f.name}")
    for ej, esq in PARES.items():
        p = EJ / ej
        if not p.exists():
            print(f"· sin ejemplo: {ej}")
            continue
        v = Draft202012Validator(json.loads((ESQ / esq).read_text(encoding="utf-8")),
                                 format_checker=FormatChecker())
        errs = sorted(v.iter_errors(cargar(p)), key=lambda e: list(e.path))
        if errs:
            errores += len(errs)
            print(f"✘ {ej}:")
            for e in errs:
                print(f"   /{'/'.join(map(str, e.path))}: {e.message}")
        else:
            print(f"✔ ejemplo válido: {ej}")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
