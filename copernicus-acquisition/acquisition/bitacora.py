"""Bitácora de eventos en JSON por líneas. Nunca registra credenciales."""

from __future__ import annotations

import json
import os
from .seguridad import limpiar
from .almacenamiento import ruta_nativa
from datetime import datetime, timezone
from pathlib import Path

_SECRETOS = ("COPERNICUSMARINE_SERVICE_USERNAME", "COPERNICUSMARINE_SERVICE_PASSWORD")


def _limpiar(texto: str) -> str:
    for nombre in _SECRETOS:
        valor = os.environ.get(nombre)
        if valor and len(valor) >= 3:
            texto = texto.replace(valor, "***")
    return texto


class Bitacora:
    def __init__(self, ruta: Path, run_id: str, eco: bool = True):
        self.ruta = Path(ruta_nativa(ruta))
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self.eco = eco

    def evento(self, **campos) -> dict:
        registro = {"ts_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"), "run_id": self.run_id}
        for clave, valor in campos.items():
            if any(s in clave.lower() for s in ("password", "contrasena", "username", "usuario")):
                continue
            registro[clave] = _limpiar(valor) if isinstance(valor, str) else valor
        registro = limpiar(registro)
        linea = json.dumps(registro, ensure_ascii=False, default=str)
        with open(self.ruta, "a", encoding="utf-8") as f:
            f.write(linea + "\n")
        if self.eco:
            print(linea, flush=True)
        return registro
