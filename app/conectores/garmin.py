"""Sincronización con Garmin Connect mediante la librería no oficial `garminconnect`.

- No se guarda la contraseña: tras el primer inicio de sesión (con MFA si aplica) se guarda
  el token de sesión en el Llavero ('garmin:<alias>') y se reutiliza.
- Descarga el FIT ORIGINAL de las actividades nuevas a datos/<perfil>/garmin_fit/<id>.zip.
- Si la librería deja de funcionar, la subida manual de ZIP sigue disponible.
"""
from __future__ import annotations

import time
from datetime import date, timedelta
from pathlib import Path

from app.conectores import secretos

_PENDIENTES: dict[str, tuple[float, object, object]] = {}   # alias → (caduca, api, estado MFA)


class ErrorGarmin(RuntimeError):
    pass


def _clave(alias: str) -> str:
    return f"garmin:{alias}"


def conectado(alias: str) -> bool:
    return bool(secretos.leer(_clave(alias)))


def iniciar_sesion(alias: str, email: str, password: str) -> str:
    """Devuelve 'ok' o 'mfa' (entonces hay que llamar a completar_mfa con el código)."""
    from garminconnect import Garmin
    api = Garmin(email=email, password=password, return_on_mfa=True)
    try:
        estado, extra = api.login()
    except Exception as e:  # credenciales, bloqueo, cambios en Garmin…
        raise ErrorGarmin(f"no se pudo iniciar sesión en Garmin: {e}") from None
    if estado == "needs_mfa":
        _PENDIENTES[alias] = (time.time() + 300, api, extra)
        return "mfa"
    secretos.guardar(_clave(alias), api.client.dumps())
    return "ok"


def completar_mfa(alias: str, codigo: str) -> str:
    caduca, api, estado = _PENDIENTES.pop(alias, (0, None, None))
    if not api or time.time() > caduca:
        raise ErrorGarmin("no hay un inicio de sesión pendiente o ha caducado: vuelve a introducir email y contraseña")
    try:
        api.resume_login(estado, codigo.strip())
    except Exception as e:
        raise ErrorGarmin(f"código MFA rechazado: {e}") from None
    secretos.guardar(_clave(alias), api.client.dumps())
    return "ok"


def desconectar(alias: str) -> None:
    secretos.borrar(_clave(alias))


def _api(alias: str):
    from garminconnect import Garmin
    token = secretos.leer(_clave(alias))
    if not token:
        raise ErrorGarmin("Garmin no está conectado para este perfil")
    api = Garmin()
    try:
        api.login(tokenstore=token)
    except Exception as e:
        raise ErrorGarmin(f"la sesión de Garmin ha caducado o falló ({e}); vuelve a conectar") from None
    nuevo = api.client.dumps()
    if nuevo != token:
        secretos.guardar(_clave(alias), nuevo)
    return api


def descargar_nuevas(alias: str, carpeta_fit: Path, desde: date, ya_tengo: set[str]) -> list[Path]:
    """Descarga los FIT originales de las actividades desde `desde` que no estén ya importadas."""
    from garminconnect import Garmin
    api = _api(alias)
    carpeta_fit.mkdir(parents=True, exist_ok=True)
    actividades = api.get_activities_by_date(desde.isoformat(), (date.today() + timedelta(days=1)).isoformat())
    nuevas = []
    for a in actividades:
        aid = str(a.get("activityId"))
        destino = carpeta_fit / f"{aid}.zip"
        if aid in ya_tengo or destino.exists():
            continue
        datos = api.download_activity(aid, dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL)
        destino.write_bytes(datos)
        nuevas.append(destino)
    return nuevas


def fc_reposo_media(alias: str, dias: int = 7) -> float | None:
    """Media de la FC en reposo de los últimos días según Garmin (None si no hay datos)."""
    api = _api(alias)
    valores = []
    for i in range(1, dias + 1):
        try:
            s = api.get_user_summary((date.today() - timedelta(days=i)).isoformat())
            if s and s.get("restingHeartRate"):
                valores.append(s["restingHeartRate"])
        except Exception:
            continue
    return round(sum(valores) / len(valores), 1) if valores else None
