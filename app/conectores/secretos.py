"""Secretos por perfil (clave de Hevy, token de Garmin) en el Llavero de macOS.

Nunca se guardan contraseñas: solo la clave de API de Hevy y el token de sesión de Garmin.
En tests se usa un almacén en memoria (FITPLAN_SECRETOS=memoria).
"""
from __future__ import annotations

import os

SERVICIO = "fitplan"
_MEMORIA: dict[str, str] = {}


def _mem() -> bool:
    return os.environ.get("FITPLAN_SECRETOS") == "memoria"


def leer(nombre: str) -> str | None:
    if _mem():
        return _MEMORIA.get(nombre)
    import keyring
    return keyring.get_password(SERVICIO, nombre)


def guardar(nombre: str, valor: str) -> None:
    if _mem():
        _MEMORIA[nombre] = valor
        return
    import keyring
    keyring.set_password(SERVICIO, nombre, valor)


def borrar(nombre: str) -> None:
    if _mem():
        _MEMORIA.pop(nombre, None)
        return
    import keyring
    try:
        keyring.delete_password(SERVICIO, nombre)
    except keyring.errors.PasswordDeleteError:
        pass
