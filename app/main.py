"""Punto de entrada de la API de FitPlan."""
from fastapi import FastAPI

app = FastAPI(title="FitPlan", version="0.1.0")


@app.get("/salud")
def salud() -> dict:
    """Comprobación de que la API está viva."""
    return {"estado": "ok", "version": app.version}
