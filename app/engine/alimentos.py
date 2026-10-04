"""Matcher de alimentos contra restricciones (regla V5 del validador).

Reglas:
- Normaliza: minúsculas, sin tildes, espacios simples.
- Cada término se busca como frase completa, admitiendo plural (-s / -es).
- Excepciones que empiezan por 'sin ' o 'bajo en ' eximen al item entero para ese grupo.
- El resto de excepciones se eliminan del texto (de la más larga a la más corta) antes de buscar.
- Una restricción se resuelve a grupos por: clave de grupo → alias → término literal.
"""
from __future__ import annotations

import json
import pathlib
import re
import unicodedata

RUTA = pathlib.Path(__file__).resolve().parents[2] / "data" / "alimentos_grupos.json"
EXIME = ("sin ", "bajo en ", "bajo ")


def norm(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t).strip()


def _plural(w: str) -> str:
    if w.endswith("z"):  # nuez → nueces, maiz → maices
        return re.escape(w[:-1]) + r"(?:z|ces)"
    return re.escape(w) + r"(?:s|es)?"


def _patron(term: str) -> re.Pattern:
    palabras = [_plural(w) for w in norm(term).split(" ")]
    return re.compile(r"(?<![a-z0-9])" + r" ".join(palabras) + r"(?![a-z0-9])")


class Diccionario:
    def __init__(self, ruta: pathlib.Path = RUTA):
        d = json.loads(ruta.read_text(encoding="utf-8"))
        self.alias = {norm(k): v for k, v in d["alias"].items()}
        self.grupos = {}
        for g, v in d["grupos"].items():
            exc = sorted((norm(e) for e in v.get("excepciones", [])), key=len, reverse=True)
            self.grupos[g] = {
                "incluye": [(t, _patron(t)) for t in v["incluye"]],
                "exime": [e for e in exc if e.startswith(EXIME)],
                "quita": [_patron(e) for e in exc if not e.startswith(EXIME)],
            }

    def resolver(self, restriccion: str) -> list[str]:
        r = norm(restriccion)
        clave = r.replace(" ", "_")
        if clave in self.grupos:
            return [clave]
        if r in self.alias:
            return self.alias[r]
        self.grupos[f"literal:{r}"] = {"incluye": [(r, _patron(r))], "exime": [], "quita": []}
        return [f"literal:{r}"]

    def coincide(self, alimento: str, grupo: str) -> str | None:
        """Devuelve el término que dispara la coincidencia, o None."""
        g = self.grupos[grupo]
        texto = norm(alimento)
        if any(e in texto for e in g["exime"]):
            return None
        for p in g["quita"]:
            texto = p.sub(" ", texto)
        for term, p in g["incluye"]:
            if p.search(texto):
                return term
        return None

    def comprobar(self, alimentos: list[str], restricciones: list[str]) -> list[dict]:
        hallazgos = []
        for r in restricciones:
            for g in self.resolver(r):
                for a in alimentos:
                    t = self.coincide(a, g)
                    if t:
                        hallazgos.append({"restriccion": r, "grupo": g, "alimento": a, "termino": t})
        return hallazgos
