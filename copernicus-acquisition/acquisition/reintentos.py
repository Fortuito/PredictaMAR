"""Clasificación de errores y reintentos con espera creciente."""

from __future__ import annotations

import time

TRANSITORIO = "transitorio"
AUTENTICACION = "autenticacion"
PARAMETROS = "parametros"
FUERA_DE_LIMITES = "fuera_de_limites"


class FallaDescarga(Exception):
    def __init__(self, tipo: str, mensaje: str, intentos: int):
        super().__init__(mensaje)
        self.tipo = tipo
        self.mensaje = mensaje
        self.intentos = intentos


def resumen(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {str(exc)[:500]}"


def clasificar(exc: BaseException) -> str:
    """Distingue fallas temporales (se reintentan) de las que no se resuelven reintentando."""
    nombres = " ".join(c.__name__ for c in type(exc).__mro__).lower()
    msg = str(exc).lower()
    if isinstance(exc, (PermissionError, FileNotFoundError, IsADirectoryError)):
        return PARAMETROS
    if any(k in nombres for k in ("couldnotconnect", "servicenotavailable")):
        return TRANSITORIO
    if any(k in nombres for k in ("credential", "username", "password", "authentication", "unauthorized")) \
            or ("credential" in msg and ("invalid" in msg or "incorrect" in msg)):
        return AUTENTICACION
    if "outofdatasetbounds" in nombres or ("exceed" in msg and ("bound" in msg or "coordinate" in msg)):
        return FUERA_DE_LIMITES
    if isinstance(exc, (TimeoutError, ConnectionError)) \
            or any(k in nombres for k in ("timeout", "connection", "servererror", "serviceunavailable", "httperror", "clienterror")) \
            or any(k in msg for k in ("timed out", "timeout", "connection", " 502", " 503", " 504", "temporarily", "unavailable")):
        return TRANSITORIO
    if isinstance(exc, OSError):
        return TRANSITORIO
    return PARAMETROS


def con_reintentos(fn, maximo: int, esperas, bitacora, contexto: dict, dormir=time.sleep):
    """Ejecuta fn con un intento inicial y hasta `maximo` reintentos ante fallas transitorias.

    Devuelve (resultado, intentos). Si falla, lanza FallaDescarga con el tipo y el número de intentos.
    """
    intentos = 0
    while True:
        intentos += 1
        try:
            return fn(), intentos
        except Exception as exc:  # noqa: BLE001 - se clasifica y se registra
            tipo = clasificar(exc)
            bitacora.evento(evento="falla", intento=intentos, tipo_error=tipo, error=resumen(exc), **contexto)
            if tipo == TRANSITORIO and intentos <= maximo:
                espera = float(esperas[intentos - 1])
                bitacora.evento(evento="reintento", intento=intentos + 1, espera_s=espera, **contexto)
                dormir(espera)
                continue
            raise FallaDescarga(tipo, resumen(exc), intentos) from exc
