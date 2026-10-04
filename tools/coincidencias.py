"""Casos de prueba del matcher de alimentos (la lógica vive en app/engine/alimentos.py).

Uso: python tools/coincidencias.py
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.engine.alimentos import Diccionario  # noqa: E402

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
