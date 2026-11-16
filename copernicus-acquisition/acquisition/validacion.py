"""Controles de integridad y cobertura de cada archivo descargado (Tabla de controles del informe)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from . import estados as E
from .almacenamiento import iso, utc, ruta_nativa

LAT = ("latitude", "lat")
LON = ("longitude", "lon")
_SINONIMOS = {
    "k": "kelvin", "kelvin": "kelvin", "kelvins": "kelvin",
    "degrees_c": "degrees_c", "degree_c": "degrees_c", "degree_celsius": "degrees_c",
    "degrees_celsius": "degrees_c", "celsius": "degrees_c", "°c": "degrees_c", "deg_c": "degrees_c",
}


def norm_unidad(u) -> str:
    u = str(u or "").strip().lower().replace(" ", "_")
    return _SINONIMOS.get(u, u)


def a_utc(valor) -> datetime:
    """datetime64 sin zona (CF, UTC) -> datetime con zona UTC."""
    ts = pd.Timestamp(valor)
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    return ts.to_pydatetime()


def paso(valores) -> float | None:
    v = np.sort(np.asarray(valores, dtype=float).ravel())
    if v.size < 2:
        return None
    d = np.diff(v)
    d = d[d > 0]
    return float(np.median(d)) if d.size else None


def _coord(ds, nombres):
    for n in nombres:
        if n in ds.coords or n in ds.variables:
            return ds[n]
    return None


def _r(x):
    return None if x is None else round(float(x), 4)


@dataclass
class Resultado:
    estado: str
    causa: str = ""
    controles: list = field(default_factory=list)
    estadisticos: dict = field(default_factory=dict)
    unidades: dict = field(default_factory=dict)
    cobertura_inicio: datetime | None = None
    cobertura_fin: datetime | None = None
    niveles_m: list | None = None
    n_tiempos: int = 0
    area_efectiva: dict | None = None
    resolucion_efectiva: dict = field(default_factory=dict)


def validar_archivo(ruta, producto, zona, inicio: datetime, fin: datetime,
                    fraccion_minima: float, paso_tiempo_s: float | None = None) -> Resultado:
    controles: list = []

    def ok(nombre, cumple, detalle=""):
        controles.append({"control": nombre, "cumple": bool(cumple), "detalle": detalle})
        return bool(cumple)

    ruta = Path(ruta_nativa(ruta))
    existe = ruta.exists() and ruta.stat().st_size > 0
    if not existe:
        ok("archivo", False, "no existe o está vacío")
        return Resultado(E.NO_VALIDADO, "archivo inexistente o vacío", controles)
    try:
        ds = xr.open_dataset(ruta_nativa(ruta))
    except Exception as exc:  # noqa: BLE001
        ok("archivo", False, f"no se abre como NetCDF ({type(exc).__name__})")
        return Resultado(E.NO_VALIDADO, "el archivo no se abre como NetCDF", controles)
    ok("archivo", True, f"{ruta.stat().st_size} bytes; se abre como NetCDF")
    try:
        ds = ds.load()
        res = _validar(ds, producto, zona, utc(inicio), utc(fin), fraccion_minima, paso_tiempo_s, ok)
    except (OSError, ValueError, RuntimeError) as exc:
        ok("lectura_contenido", False, type(exc).__name__)
        res = Resultado(E.NO_VALIDADO, "no se pudo leer o interpretar el contenido NetCDF")
    finally:
        ds.close()
    res.controles = controles
    return res


def _validar(ds, producto, zona, inicio, fin, fraccion_minima, paso_tiempo_s, ok) -> Resultado:
    fallas: list = []
    parcial: list = []

    faltan = [v for v in producto.variables if v not in ds.data_vars]
    if not ok("variables", not faltan, ("faltan: " + ", ".join(faltan)) if faltan else "presentes"):
        return Resultado(E.NO_VALIDADO, "faltan variables: " + ", ".join(faltan))

    vacias = [f"{v}.{d}" for v in producto.variables for d, n in ds[v].sizes.items() if n == 0]
    if not ok("dimensiones", not vacias, ("vacías: " + ", ".join(vacias)) if vacias else "con elementos"):
        if any(x.endswith(".time") for x in vacias):
            return Resultado(E.SIN_DATO, "el archivo no tiene instantes en la ventana")
        return Resultado(E.NO_VALIDADO, "dimensiones vacías")

    # área
    lat, lon = _coord(ds, LAT), _coord(ds, LON)
    if lat is None or lon is None:
        ok("area", False, "sin coordenadas de latitud y longitud")
        return Resultado(E.NO_VALIDADO, "sin coordenadas de latitud y longitud")
    tol_lat = max(paso(lat.values) or 0.0, 0.01)
    tol_lon = max(paso(lon.values) or 0.0, 0.01)
    la0, la1, lo0, lo1 = float(lat.min()), float(lat.max()), float(lon.min()), float(lon.max())
    dentro = (la0 >= zona.lat_min - tol_lat and la1 <= zona.lat_max + tol_lat
              and lo0 >= zona.lon_min - tol_lon and lo1 <= zona.lon_max + tol_lon)
    if not ok("area", dentro, f"lat {la0:.3f} a {la1:.3f}; lon {lo0:.3f} a {lo1:.3f}"):
        fallas.append("coordenadas fuera del área solicitada")
    cubre = (la0 <= zona.lat_min + tol_lat and la1 >= zona.lat_max - tol_lat
             and lo0 <= zona.lon_min + tol_lon and lo1 >= zona.lon_max - tol_lon)
    if not ok("cobertura_espacial", cubre, "límites contrastados con un paso nativo de tolerancia"):
        parcial.append("cobertura espacial incompleta")

    # tiempo
    cob_ini = cob_fin = None
    n_t = 0
    t = _coord(ds, ("time",))
    if t is not None and t.size:
        tiempos = sorted(a_utc(v) for v in np.atleast_1d(t.values))
        cob_ini, cob_fin, n_t = tiempos[0], tiempos[-1], len(tiempos)
        p = paso_tiempo_s or paso([x.timestamp() for x in tiempos]) or 86400.0
        segundos = np.array([x.timestamp() for x in tiempos])
        unico = len(np.unique(segundos)) == len(segundos)
        if not ok("tiempos_unicos", unico, "no se admiten instantes duplicados"):
            fallas.append("instantes duplicados")
        continuo = not np.any(np.diff(segundos) > p * 1.01)
        if not ok("continuidad_temporal", continuo, f"paso esperado {p} segundos"):
            parcial.append("faltan instantes dentro de la ventana")
        tol = timedelta(seconds=p)
        en_ventana = cob_ini >= inicio and cob_fin <= fin
        if not ok("tiempo", en_ventana, f"{iso(cob_ini)} a {iso(cob_fin)} ({n_t} instantes)"):
            fallas.append("instantes fuera de la ventana solicitada")
        elif cob_fin < fin - tol or cob_ini > inicio + tol:
            parcial.append("cubre solo parte de la ventana solicitada")
    else:
        ok("tiempo", False, "sin coordenada de tiempo")
        fallas.append("sin coordenada de tiempo")

    # profundidad
    niveles = None
    d = _coord(ds, ("depth",))
    if d is not None:
        niveles = [round(float(x), 3) for x in np.atleast_1d(d.values)]
    if producto.profundidad_m is not None:
        if niveles is None:
            ok("profundidad", False, "sin coordenada de profundidad")
            fallas.append("sin coordenada de profundidad")
        else:
            pmin, pmax = producto.profundidad_m
            cumple = all(pmin - 0.5 <= x <= pmax + 0.5 for x in niveles)
            if not ok("profundidad", cumple, f"niveles efectivos (m): {niveles}"):
                fallas.append("niveles fuera del rango solicitado")

    # unidades, valores y cobertura por variable
    unidades, estad, fracs = {}, {}, []
    for v in producto.variables:
        u = ds[v].attrs.get("units")
        unidades[v] = u
        esperada = producto.unidades_esperadas.get(v)
        if esperada is not None and not ok(f"unidades:{v}", norm_unidad(u) == norm_unidad(esperada),
                                           f"{u!r} (esperada {esperada!r})"):
            fallas.append(f"unidades de {v} distintas de las esperadas")
        arr = np.asarray(ds[v].values, dtype=float)
        if not ok(f"finitud:{v}", not np.isinf(arr).any(), "NaN representa ausencia; infinito es inválido"):
            fallas.append(f"valores infinitos en {v}")
        fin_ = arr[np.isfinite(arr)]
        frac = float(fin_.size / arr.size) if arr.size else 0.0
        fracs.append(frac)
        estad[v] = {"n_celdas": int(arr.size), "fraccion_validas": round(frac, 4),
                    "min": _r(fin_.min()) if fin_.size else None, "max": _r(fin_.max()) if fin_.size else None,
                    "media": _r(fin_.mean()) if fin_.size else None, "unidades": u}
        rango = producto.rango_plausible.get(v)
        if rango is not None and fin_.size:
            fuera = int(((fin_ < rango[0]) | (fin_ > rango[1])).sum())
            if not ok(f"valores:{v}", fuera == 0, f"{fuera} valores fuera de [{rango[0]}, {rango[1]}]"):
                fallas.append(f"valores de {v} fuera del rango plausible")

    base = dict(estadisticos=estad, unidades=unidades, cobertura_inicio=cob_ini, cobertura_fin=cob_fin,
                niveles_m=niveles, n_tiempos=n_t,
                area_efectiva={"lat_min": la0, "lat_max": la1, "lon_min": lo0, "lon_max": lo1},
                resolucion_efectiva={"lat_grados": paso(lat.values), "lon_grados": paso(lon.values),
                                     "tiempo_s": paso_tiempo_s})
    if max(fracs, default=0.0) == 0.0:
        ok("cobertura", False, "ninguna celda con dato")
        if fallas:
            return Resultado(E.NO_VALIDADO, "; ".join(fallas), **base)
        return Resultado(E.SIN_DATO, "el archivo no tiene celdas con dato en la zona y la ventana", **base)
    minima = min(fracs)
    if not ok("cobertura", minima >= fraccion_minima,
              f"fracción mínima de celdas con dato {minima:.2f} (umbral {fraccion_minima:.2f})"):
        parcial.append("menos celdas con dato que el umbral")

    if fallas:
        return Resultado(E.NO_VALIDADO, "; ".join(fallas), **base)
    if parcial:
        return Resultado(E.PARCIAL, "; ".join(parcial), **base)
    return Resultado(E.DISPONIBLE, "", **base)
