"""Acceso a Copernicus Marine Service mediante la herramienta oficial (copernicusmarine).

Las credenciales se leen de COPERNICUSMARINE_SERVICE_USERNAME y COPERNICUSMARINE_SERVICE_PASSWORD;
nunca se pasan ni se guardan en el código.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .validacion import a_utc, paso
from .almacenamiento import ruta_nativa


def extraer_metadatos(ds) -> dict:
    """Cobertura temporal, espacial y de profundidad de un dataset abierto de forma diferida."""
    meta: dict = {}
    if "time" in ds.coords:
        t = np.atleast_1d(ds["time"].values)
        if t.size:
            meta["tiempo_min"] = a_utc(t.min())
            meta["tiempo_max"] = a_utc(t.max())
            if t.size > 1:
                segundos = t.astype("datetime64[s]").astype("int64")
                meta["paso_tiempo_s"] = paso(segundos[-50:])
    for nombre, claves in (("lat", ("latitude", "lat")), ("lon", ("longitude", "lon"))):
        for c in claves:
            if c in ds.coords:
                v = np.asarray(ds[c].values, dtype=float)
                meta[f"{nombre}_min"], meta[f"{nombre}_max"] = float(v.min()), float(v.max())
                break
    if "depth" in ds.coords:
        meta["profundidades"] = [float(x) for x in np.atleast_1d(ds["depth"].values)]
    return meta


class ClienteCopernicus:
    def __init__(self):
        import copernicusmarine  # importación diferida: las pruebas unitarias no la necesitan

        self._cm = copernicusmarine

    def version_herramienta(self) -> str:
        return str(getattr(self._cm, "__version__", "desconocida"))

    def metadatos(self, producto) -> dict:
        ds = self._cm.open_dataset(dataset_id=producto.dataset_id, variables=list(producto.variables),
                                   **self._version(producto))
        try:
            return extraer_metadatos(ds)
        finally:
            ds.close()

    def identificacion(self, dataset_id: str) -> dict:
        """Producto y versión vigente del dataset según el catálogo; None si no se puede consultar."""
        vacio = {"product_id": None, "dataset_version": None}
        if not hasattr(self, "_identidades"):
            self._identidades = {}
        if dataset_id in self._identidades:
            return self._identidades[dataset_id]
        try:
            catalogo = self._cm.describe(dataset_id=dataset_id, disable_progress_bar=True)
        except TypeError:
            try:
                catalogo = self._cm.describe(dataset_id=dataset_id)
            except Exception:  # noqa: BLE001
                return vacio
        except Exception:  # noqa: BLE001
            return vacio
        for prod in getattr(catalogo, "products", None) or []:
            for d in getattr(prod, "datasets", None) or []:
                if getattr(d, "dataset_id", None) == dataset_id:
                    etiquetas = sorted(e for e in (getattr(v, "label", None) for v in (getattr(d, "versions", None) or [])) if e)
                    identidad = {"product_id": getattr(prod, "product_id", None),
                                 "dataset_version": etiquetas[-1] if etiquetas else None}
                    self._identidades[dataset_id] = identidad
                    return identidad
        return vacio

    def _version(self, producto):
        version = producto.dataset_version or self.identificacion(producto.dataset_id)["dataset_version"]
        if version is None:
            raise ValueError("No se pudo resolver la versión del dataset; no se descarga sin trazabilidad")
        return {"dataset_version": version}

    def descargar(self, producto, zona, inicio, fin, carpeta: Path, nombre: str) -> Path:
        argumentos = dict(
            dataset_id=producto.dataset_id,
            variables=list(producto.variables),
            minimum_longitude=zona.lon_min, maximum_longitude=zona.lon_max,
            minimum_latitude=zona.lat_min, maximum_latitude=zona.lat_max,
            start_datetime=inicio.strftime("%Y-%m-%dT%H:%M:%S"),
            end_datetime=fin.strftime("%Y-%m-%dT%H:%M:%S"),
            output_directory=ruta_nativa(carpeta),
            output_filename=nombre,
            disable_progress_bar=True,
            **self._version(producto),
        )
        if producto.profundidad_m is not None:
            argumentos["minimum_depth"], argumentos["maximum_depth"] = producto.profundidad_m
        respuesta = self._cm.subset(**argumentos)
        ruta = getattr(respuesta, "file_path", None)
        # Normalizar el prefijo de Windows para mantener rutas relativas portables.
        if ruta:
            texto = str(ruta)
            if texto.startswith("\\\\?\\UNC\\"):
                texto = "\\\\" + texto[8:]
            elif texto.startswith("\\\\?\\"):
                texto = texto[4:]
            return Path(texto)
        return Path(carpeta) / nombre
