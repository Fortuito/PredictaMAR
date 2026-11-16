"""Utilidades de prueba: archivos NetCDF sintéticos y un cliente simulado (sin conexión)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from acquisition.config import Config, Producto, Zona
from acquisition.almacenamiento import ruta_nativa

AHORA = datetime(2026, 11, 16, 14, 17, 3, tzinfo=timezone.utc)   # ventana: 14/11 00:00 a 15/11 23:59:59 UTC


def zona(**kw) -> Zona:
    base = dict(id="z1", descripcion="zona de prueba", lat_min=-12.6, lat_max=-12.3, lon_min=-77.0, lon_max=-76.7)
    base.update(kw)
    return Zona(**base)


def producto(**kw) -> Producto:
    base = dict(id="p1", dataset_id="ds_prueba", tipo_dato="modelo", variables=("thetao",), frecuencia_h=24,
                profundidad_m=(0.0, 12.0), unidades_esperadas={"thetao": "degrees_C"},
                rango_plausible={"thetao": (-3.0, 40.0)})
    base.update(kw)
    return Producto(**base)


def config(raiz, zonas=None, productos=None, **kw) -> Config:
    base = dict(ruta="config/prueba.yaml", sha256="0" * 64, version=1, raiz_datos=str(raiz), ventana_dias=2,
                reintentos_maximo=3, esperas_s=(30.0, 120.0, 300.0), fraccion_minima_validas=0.5,
                zonas=tuple(zonas or [zona()]), productos=tuple(productos or [producto()]))
    base.update(kw)
    return Config(**base)


def escribir_nc(ruta, *, inicio, fin, paso_h=6, lat=(-12.6, -12.3), lon=(-77.0, -76.7), n=4,
                profundidades=(0.494, 9.573, 11.405), var="thetao", unidades="degrees_C", valor=18.0,
                frac_nan=0.0, sin_tiempos=False):
    t = pd.date_range(inicio.replace(tzinfo=None), fin.replace(tzinfo=None), freq=f"{paso_h}h")
    if sin_tiempos:
        t = t[:0]
    coords = {"time": t, "latitude": np.linspace(lat[0], lat[1], n), "longitude": np.linspace(lon[0], lon[1], n)}
    dims = ["time", "latitude", "longitude"]
    if profundidades is not None:
        coords["depth"] = np.asarray(profundidades, dtype=float)
        dims = ["time", "depth", "latitude", "longitude"]
    forma = tuple(len(coords[d]) for d in dims)
    datos = np.full(forma, valor, dtype="float32")
    if frac_nan > 0 and datos.size:
        plano = datos.reshape(-1)
        plano[: int(round(frac_nan * plano.size))] = np.nan
    ds = xr.Dataset({var: (dims, datos, {"units": unidades})}, coords=coords)
    Path(ruta_nativa(Path(ruta).parent)).mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(ruta_nativa(ruta))
    return Path(ruta)


class ClienteFalso:
    """Simula la herramienta de Copernicus: metadatos configurables, fallas programadas y archivos sintéticos."""

    def __init__(self, meta=None, fallas_descarga=None, fallas_metadatos=None, opciones_nc=None):
        self.meta = meta or {
            "tiempo_min": datetime(2022, 1, 1, tzinfo=timezone.utc),
            "tiempo_max": datetime(2026, 11, 25, tzinfo=timezone.utc),
            "paso_tiempo_s": 21600.0, "lat_min": -80.0, "lat_max": 90.0, "lon_min": -180.0, "lon_max": 180.0,
            "profundidades": [0.494, 1.541, 9.573, 11.405, 13.467],
        }
        self.fallas_descarga = list(fallas_descarga or [])
        self.fallas_metadatos = list(fallas_metadatos or [])
        self.opciones_nc = opciones_nc or {}
        self.descargas = 0

    def version_herramienta(self):
        return "simulada"

    def identificacion(self, dataset_id):
        return {"product_id": "PRODUCTO_PRUEBA", "dataset_version": "202406"}

    def metadatos(self, producto):
        if self.fallas_metadatos:
            raise self.fallas_metadatos.pop(0)
        return dict(self.meta)

    def descargar(self, producto, zona, inicio, fin, carpeta, nombre):
        self.descargas += 1
        if self.fallas_descarga:
            raise self.fallas_descarga.pop(0)
        ruta = Path(carpeta) / nombre
        opciones = {"var": producto.variables[0],
                    "profundidades": (0.494, 9.573, 11.405) if producto.profundidad_m else None,
                    "lat": (zona.lat_min, zona.lat_max), "lon": (zona.lon_min, zona.lon_max)}
        opciones.update(self.opciones_nc)
        return escribir_nc(ruta, inicio=inicio, fin=fin, **opciones)


@pytest.fixture
def sin_espera():
    esperas = []
    return esperas, esperas.append
