"""Nombres, rutas y escritura sin sobrescritura. Todas las fechas en UTC."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from .seguridad import limpiar
from datetime import datetime, timezone
from pathlib import Path


def utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    return None if dt is None else utc(dt).strftime("%Y-%m-%dT%H:%M:%SZ")


def ruta_nativa(ruta) -> str:
    """Ruta extendida para bibliotecas C (NetCDF) sujetas a MAX_PATH en Windows."""
    valor = str(Path(ruta).resolve())
    if os.name == "nt" and not valor.startswith("\\\\?\\"):
        return "\\\\?\\UNC\\" + valor[2:] if valor.startswith("\\\\") else "\\\\?\\" + valor
    return valor


def sello(dt: datetime) -> str:
    """Marca compacta UTC: 20261116T141703Z."""
    return utc(dt).strftime("%Y%m%dT%H%M%SZ")


def nombre_archivo(dataset_id: str, variables, zona_id: str, inicio: datetime, fin: datetime, run_id: str) -> str:
    return f"{dataset_id}__{'-'.join(variables)}__{zona_id}__{sello(inicio)}_{sello(fin)}__{run_id}.nc"


def ruta_original(raiz: Path, dataset_id: str, variables, zona_id: str, inicio: datetime, nombre: str) -> Path:
    i = utc(inicio)
    return Path(raiz) / "originales" / dataset_id / "-".join(variables) / zona_id / f"{i:%Y}" / f"{i:%m}" / nombre


def ruta_cuarentena(raiz: Path, run_id: str, nombre: str) -> Path:
    return Path(raiz) / "cuarentena" / run_id / nombre


def ruta_manifiesto(raiz: Path, inicio_run: datetime, run_id: str) -> Path:
    i = utc(inicio_run)
    return Path(raiz) / "manifiestos" / f"{i:%Y}" / f"{i:%m}" / f"manifiesto_{run_id}.json"


def ruta_bitacora(raiz: Path, inicio_run: datetime, run_id: str) -> Path:
    i = utc(inicio_run)
    return Path(raiz) / "bitacoras" / f"{i:%Y}" / f"{i:%m}" / f"bitacora_{run_id}.jsonl"


def destino_libre(destino: Path) -> Path:
    """Devuelve una ruta que no existe; nunca reemplaza un archivo previo."""
    if not Path(ruta_nativa(destino)).exists():
        return destino
    n = 2
    while True:
        alternativa = destino.with_name(f"{destino.stem}__{n}{destino.suffix}")
        if not Path(ruta_nativa(alternativa)).exists():
            return alternativa
        n += 1


def mover_sin_sobrescribir(origen: Path, destino: Path) -> Path:
    Path(ruta_nativa(destino.parent)).mkdir(parents=True, exist_ok=True)
    # El enlace crea el destino de forma exclusiva y publica el archivo completo.
    # Los temporales y los originales deben estar en la misma unidad.
    while True:
        final = destino_libre(destino)
        try:
            os.link(ruta_nativa(origen), ruta_nativa(final))
            break
        except FileExistsError:
            continue
    Path(ruta_nativa(origen)).unlink()
    return final


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta_nativa(ruta), "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def escribir_json(ruta: Path, datos: dict) -> Path:
    """Escritura atómica de un JSON nuevo (nunca reemplaza uno existente)."""
    Path(ruta_nativa(ruta.parent)).mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_name(ruta.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        Path(ruta_nativa(tmp)).write_text(json.dumps(limpiar(datos), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        return mover_sin_sobrescribir(tmp, ruta)
    finally:
        Path(ruta_nativa(tmp)).unlink(missing_ok=True)
