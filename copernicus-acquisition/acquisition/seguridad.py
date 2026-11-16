"""Redacción recursiva antes de persistir diagnósticos o imprimirlos."""
import os

SECRETOS = ("COPERNICUSMARINE_SERVICE_USERNAME", "COPERNICUSMARINE_SERVICE_PASSWORD")


def limpiar(valor):
    if isinstance(valor, str):
        for nombre in SECRETOS:
            secreto = os.environ.get(nombre)
            if secreto:
                valor = valor.replace(secreto, "***")
        return valor
    if isinstance(valor, dict):
        return {k: limpiar(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [limpiar(v) for v in valor]
    return valor
