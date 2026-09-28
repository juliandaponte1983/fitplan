"""Cifrado de campos sensibles (perfil médico, claves de API) con Fernet.

La clave maestra se guarda en el Llavero de macOS (servicio 'fitplan').
Para tests o para otro sistema: variable de entorno FITPLAN_CLAVE.
"""
from __future__ import annotations

import os
from functools import lru_cache

from cryptography.fernet import Fernet

SERVICIO, CUENTA = "fitplan", "clave_maestra"


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    clave = os.environ.get("FITPLAN_CLAVE")
    if not clave:
        import keyring
        clave = keyring.get_password(SERVICIO, CUENTA)
        if not clave:
            clave = Fernet.generate_key().decode()
            keyring.set_password(SERVICIO, CUENTA, clave)
    return Fernet(clave.encode() if isinstance(clave, str) else clave)


def cifrar(texto: str) -> bytes:
    return _fernet().encrypt(texto.encode("utf-8"))


def descifrar(dato: bytes) -> str:
    return _fernet().decrypt(dato).decode("utf-8")
