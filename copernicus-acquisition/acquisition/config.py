"""Carga y validación del archivo de configuración (config/adquisicion.yaml)."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

TIPOS_DATO = ("modelo", "observacion_L3", "analisis_L4")
_ID = re.compile(r"^[a-z0-9_]+$")


class ConfigError(ValueError):
    """La configuración no cumple el esquema esperado."""


@dataclass(frozen=True)
class Zona:
    id: str
    descripcion: str
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float

    def area(self) -> dict:
        return {"lat_min": self.lat_min, "lat_max": self.lat_max,
                "lon_min": self.lon_min, "lon_max": self.lon_max}


@dataclass(frozen=True)
class Producto:
    id: str
    dataset_id: str
    tipo_dato: str
    variables: tuple
    frecuencia_h: int
    profundidad_m: tuple | None = None
    unidades_esperadas: dict = field(default_factory=dict)
    rango_plausible: dict = field(default_factory=dict)
    dataset_version: str | None = None
    resolucion: str = "nativa"


@dataclass(frozen=True)
class Config:
    ruta: str
    sha256: str
    version: int
    raiz_datos: str
    ventana_dias: int
    reintentos_maximo: int
    esperas_s: tuple
    fraccion_minima_validas: float
    zonas: tuple
    productos: tuple


def _num(valor, nombre):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ConfigError(f"{nombre} debe ser numérico")
    return float(valor)


def _par(valor, nombre, minimo, maximo):
    if not isinstance(valor, (list, tuple)) or len(valor) != 2:
        raise ConfigError(f"{nombre} debe ser una lista [mínimo, máximo]")
    a, b = _num(valor[0], nombre), _num(valor[1], nombre)
    if not (minimo <= a < b <= maximo):
        raise ConfigError(f"{nombre} fuera de rango o con mínimo >= máximo: {valor}")
    return a, b


def _zona(d, i) -> Zona:
    if not isinstance(d, dict):
        raise ConfigError(f"zonas[{i}] debe ser un objeto")
    zid = d.get("id")
    if not isinstance(zid, str) or not _ID.match(zid):
        raise ConfigError(f"zonas[{i}].id inválido: {zid!r}")
    lat = _par(d.get("lat"), f"zonas[{zid}].lat", -90, 90)
    lon = _par(d.get("lon"), f"zonas[{zid}].lon", -180, 180)
    return Zona(zid, str(d.get("descripcion", "")), lat[0], lat[1], lon[0], lon[1])


def _producto(d, i) -> Producto:
    if not isinstance(d, dict):
        raise ConfigError(f"productos[{i}] debe ser un objeto")
    pid = d.get("id")
    if not isinstance(pid, str) or not _ID.match(pid):
        raise ConfigError(f"productos[{i}].id inválido: {pid!r}")
    ds = d.get("dataset_id")
    if not isinstance(ds, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", ds):
        raise ConfigError(f"productos[{pid}].dataset_id es obligatorio")
    tipo = d.get("tipo_dato")
    if tipo not in TIPOS_DATO:
        raise ConfigError(f"productos[{pid}].tipo_dato debe ser uno de {TIPOS_DATO}")
    variables = d.get("variables")
    if not isinstance(variables, list) or not variables or not all(isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9_]+", v) for v in variables):
        raise ConfigError(f"productos[{pid}].variables debe ser una lista no vacía de nombres")
    frecuencia = d.get("frecuencia_h", 24)
    if not isinstance(frecuencia, int) or frecuencia <= 0 or frecuencia % 24 != 0:
        raise ConfigError(f"productos[{pid}].frecuencia_h debe ser múltiplo de 24 (el flujo corre una vez al día)")
    prof = d.get("profundidad_m")
    if prof is not None:
        prof = _par(prof, f"productos[{pid}].profundidad_m", 0, 11000)
    unidades = d.get("unidades_esperadas") or {}
    rangos = d.get("rango_plausible") or {}
    if not isinstance(unidades, dict) or not isinstance(rangos, dict):
        raise ConfigError(f"productos[{pid}]: unidades_esperadas y rango_plausible deben ser objetos")
    for var in list(unidades) + list(rangos):
        if var not in variables:
            raise ConfigError(f"productos[{pid}]: la variable {var!r} no está en variables")
    rangos_ok = {v: _par(r, f"productos[{pid}].rango_plausible.{v}", -1e9, 1e9) for v, r in rangos.items()}
    version = d.get("dataset_version")
    if version is not None and (not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", version)):
        raise ConfigError(f"productos[{pid}].dataset_version inválida")
    if d.get("resolucion", "nativa") != "nativa":
        raise ConfigError("Solo se admite resolucion: nativa; no se interpola ni remuestrea")
    return Producto(pid, ds.strip(), tipo, tuple(variables), frecuencia, prof,
                    {k: str(v) for k, v in unidades.items()}, rangos_ok, version)


def cargar(ruta: str | os.PathLike, raiz_datos: str | None = None) -> Config:
    """Lee y valida la configuración. raiz_datos, si se indica, reemplaza a salida.raiz_datos."""
    ruta = Path(ruta)
    try:
        contenido = ruta.read_bytes()
    except OSError as exc:
        raise ConfigError(f"No se pudo leer {ruta}: {exc}") from exc
    huella = hashlib.sha256(contenido).hexdigest()
    try:
        d = yaml.safe_load(contenido) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML inválido: {exc}") from exc
    if not isinstance(d, dict):
        raise ConfigError("La configuración debe ser un objeto YAML")

    version = d.get("version_configuracion")
    if version != 1:
        raise ConfigError("version_configuracion debe ser 1")

    salida = d.get("salida") or {}
    raiz = raiz_datos or os.path.expandvars(str(salida.get("raiz_datos", "")))
    if not raiz or "$" in raiz:
        raise ConfigError("Defina la carpeta de datos con la variable DATA_ROOT o con --data-root")

    ventana = (d.get("programacion") or {}).get("ventana_dias", 2)
    if not isinstance(ventana, int) or not 1 <= ventana <= 31:
        raise ConfigError("programacion.ventana_dias debe ser un entero entre 1 y 31")

    reint = d.get("reintentos") or {}
    maximo = reint.get("maximo", 3)
    esperas = reint.get("esperas_s", [30, 120, 300])
    if not isinstance(maximo, int) or not 0 <= maximo <= 10:
        raise ConfigError("reintentos.maximo debe ser un entero entre 0 y 10")
    if not isinstance(esperas, list) or len(esperas) != maximo or not all(isinstance(e, (int, float)) and e >= 0 for e in esperas):
        raise ConfigError("reintentos.esperas_s debe tener una espera (en segundos) por cada reintento")

    fraccion = (d.get("calidad") or {}).get("fraccion_minima_celdas_validas", 0.5)
    fraccion = _num(fraccion, "calidad.fraccion_minima_celdas_validas")
    if not 0 <= fraccion <= 1:
        raise ConfigError("calidad.fraccion_minima_celdas_validas debe estar entre 0 y 1")

    zonas = tuple(_zona(z, i) for i, z in enumerate(d.get("zonas") or []))
    productos = tuple(_producto(p, i) for i, p in enumerate(d.get("productos") or []))
    if not zonas or not productos:
        raise ConfigError("Debe haber al menos una zona y un producto")
    for nombre, items in (("zonas", zonas), ("productos", productos)):
        ids = [x.id for x in items]
        if len(ids) != len(set(ids)):
            raise ConfigError(f"Hay identificadores repetidos en {nombre}")

    return Config(str(ruta), huella, version, raiz, ventana, maximo, tuple(float(e) for e in esperas),
                  fraccion, zonas, productos)
