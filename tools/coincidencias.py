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

RUTA = pathlib.Path(__file__).resolve().parent.parent / "data" / "alimentos_grupos.json"
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


if __name__ == "__main__":
    d = Diccionario()
    casos = [
        # (alimento, restricción, ¿debe coincidir?)
        ("Pan integral de trigo", "gluten", True),
        ("Pan sin gluten", "gluten", False),
        ("Copos de avena", "gluten", True),
        ("Avena sin gluten", "gluten", False),
        ("Harina de arroz", "gluten", False),
        ("Leche de almendra", "lácteos", False),
        ("Leche de almendra", "frutos secos", True),
        ("Yogur griego natural", "lacteos", True),
        ("Yogur griego sin lactosa", "lactosa", False),
        ("Yogur griego sin lactosa", "lacteos", True),
        ("Mantequilla de cacahuete", "lacteos", False),
        ("Mantequilla de cacahuete", "frutos secos", True),
        ("Gambas al ajillo", "marisco", True),
        ("Calamares a la romana", "marisco", True),
        ("Salmón al horno", "sal", False),
        ("Salsa de soja", "sal", True),
        ("Tomate triturado sin sal", "sal", False),
        ("Tortilla de trigo", "huevo", False),
        ("Tortilla de patatas", "huevo", True),
        ("Nuez moscada", "frutos secos", False),
        ("Nueces de California", "frutos secos", True),
        ("Café descafeinado", "cafeína", False),
        ("Café con leche", "cafeína", True),
        ("Zumo de pomelo", "pomelo", True),
        ("Cerveza 0,0", "alcohol", False),
        ("Vino blanco para cocinar", "alcohol", True),
        ("Pechuga de pollo", "carne roja", False),
        ("Solomillo de cerdo", "carne roja", True),
        ("Aceite de oliva virgen extra", "grasas saturadas", False),
        ("Kiwi", "kiwi", True),
    ]
    fallos = 0
    for alimento, restr, esperado in casos:
        res = d.comprobar([alimento], [restr])
        ok = bool(res) == esperado
        fallos += not ok
        print(f"{'✔' if ok else '✘'} {alimento!r:34} vs {restr!r:18} → {res[0]['termino'] if res else '—'}")
    print(f"\n{len(casos) - fallos}/{len(casos)} casos correctos")
    raise SystemExit(1 if fallos else 0)
