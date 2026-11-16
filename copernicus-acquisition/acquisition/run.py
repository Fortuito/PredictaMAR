"""Ejecución de la adquisición: python -m acquisition.run --config config/adquisicion.yaml

Por cada zona y producto: consulta la cobertura del dataset, descarga el recorte en NetCDF,
valida el archivo, asigna un estado y lo conserva sin sobrescribir. Cada ejecución deja un
manifiesto (salida estructurada) y una bitácora.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import __version__
from . import estados as E
from .almacenamiento import (escribir_json, iso, mover_sin_sobrescribir, nombre_archivo, ruta_bitacora,
                             ruta_cuarentena, ruta_manifiesto, ruta_original, sello, sha256, utc)
from .bitacora import Bitacora
from .config import ConfigError, cargar
from .reintentos import FUERA_DE_LIMITES, FallaDescarga, con_reintentos, resumen
from .validacion import validar_archivo
from .seguridad import limpiar
from .almacenamiento import ruta_nativa

SCHEMA_VERSION = "1.1"
CREDENCIALES = ("COPERNICUSMARINE_SERVICE_USERNAME", "COPERNICUSMARINE_SERVICE_PASSWORD")


def ventana(ahora: datetime, dias: int):
    """Los `dias` últimos días UTC completos, sin incluir el día en curso."""
    hoy = utc(ahora).replace(hour=0, minute=0, second=0, microsecond=0)
    return hoy - timedelta(days=dias), hoy - timedelta(seconds=1)


def toca(producto, ahora: datetime, modo: str) -> bool:
    """El flujo corre una vez al día; un producto con frecuencia_h=48 se descarga día por medio."""
    if modo == "manual":
        return True
    return utc(ahora).date().toordinal() % (producto.frecuencia_h // 24) == 0


def _commit():
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        base = Path(__file__).resolve().parents[1]
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=base, capture_output=True,
                             text=True, timeout=5, check=True)
        if Path(top.stdout.strip()).resolve() != base:
            return None  # no atribuir al módulo un commit de una carpeta padre
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=base, capture_output=True, text=True, timeout=5, check=True)
        return r.stdout.strip() or None
    except Exception:  # noqa: BLE001
        return None


def _interseca(a0, a1, b0, b1) -> bool:
    return a0 <= b1 and b0 <= a1


def _elemento_base(producto, zona, inicio, fin) -> dict:
    return {
        "zona_id": zona.id, "area_solicitada": zona.area(),
        "producto_id": producto.id, "dataset_id": producto.dataset_id,
        "product_id": None, "dataset_version": None, "tipo_dato": producto.tipo_dato,
        "variables": list(producto.variables), "unidades": {},
        "ventana_solicitada": {"inicio": iso(inicio), "fin": iso(fin)},
        "ventana_descargada": None, "cobertura_efectiva": None,
        "ultima_disponible": None, "antiguedad_horas": None,
        "profundidad_solicitada_m": list(producto.profundidad_m) if producto.profundidad_m else None,
        "niveles_efectivos_m": None,
        "archivo": None, "tamano_bytes": None, "sha256": None,
        "estado": None, "causa": "", "intentos": 0, "duracion_s": None,
        "control": {}, "controles_aplicados": [],
        "area_efectiva": None, "resolucion_efectiva": {},
        "tratamiento": "recorte_nativo_sin_interpolacion_ni_imputacion",
        "seleccion_espacial": "area; no se seleccionan puntos ni se asignan valores a tierra",
        "distancia_coordenadas_km": None,
        "procesado_utc": None,
    }


def procesar(cfg, raiz: Path, cliente, producto, zona, inicio, fin, ahora, run_id, bit, dormir, elemento=None) -> dict:
    t0 = time.monotonic()
    ctx = {"zona": zona.id, "producto": producto.id, "dataset_id": producto.dataset_id,
           "variables": list(producto.variables), "ventana_inicio": iso(inicio), "ventana_fin": iso(fin)}
    el = elemento if elemento is not None else _elemento_base(producto, zona, inicio, fin)
    bit.evento(evento="inicio_elemento", **ctx)

    def cerrar(estado, causa=""):
        el["estado"], el["causa"] = estado, limpiar(causa)
        el["procesado_utc"] = iso(datetime.now(timezone.utc))
        el["duracion_s"] = round(time.monotonic() - t0, 2)
        bit.evento(evento="fin_elemento", estado=estado, causa=causa, intentos=el["intentos"],
                   duracion_s=el["duracion_s"], archivo=el["archivo"], **ctx)
        return el

    el.update(cliente.identificacion(producto.dataset_id))
    if producto.dataset_version:
        el["dataset_version"] = producto.dataset_version

    # 1. cobertura del dataset según sus coordenadas
    try:
        meta, n = con_reintentos(lambda: cliente.metadatos(producto), cfg.reintentos_maximo, cfg.esperas_s,
                                 bit, {**ctx, "paso": "metadatos"}, dormir)
        el["intentos"] += n
    except FallaDescarga as f:
        el["intentos"] += f.intentos
        return cerrar(E.ERROR, f"{f.tipo}: {f.mensaje}")

    tmin, tmax = meta.get("tiempo_min"), meta.get("tiempo_max")
    if tmax is not None:
        el["ultima_disponible"] = iso(tmax)
        el["antiguedad_horas"] = round((utc(ahora) - tmax).total_seconds() / 3600, 1)

    # 2. dominio del producto: espacio, profundidad y periodo
    if "lat_min" in meta and "lon_min" in meta and not (
            _interseca(zona.lat_min, zona.lat_max, meta["lat_min"], meta["lat_max"])
            and _interseca(zona.lon_min, zona.lon_max, meta["lon_min"], meta["lon_max"])):
        return cerrar(E.FUERA_DE_DOMINIO, "la zona está fuera de la cobertura espacial del producto")
    if producto.profundidad_m and meta.get("profundidades") is not None:
        pmin, pmax = producto.profundidad_m
        if not any(pmin <= p <= pmax for p in meta["profundidades"]):
            return cerrar(E.FUERA_DE_DOMINIO, "el producto no tiene niveles en el rango de profundidad solicitado")
    if tmin is not None and tmin > fin:
        return cerrar(E.FUERA_DE_DOMINIO, "el periodo solicitado es anterior al inicio del producto")
    if tmax is None or tmax < inicio:
        return cerrar(E.SIN_DATO, "el producto aún no publica datos para la ventana solicitada; no se descarga otra fecha en su lugar")

    # 3. descarga del recorte disponible dentro de la ventana (la diferencia queda como cobertura parcial)
    d_ini = max(inicio, tmin) if tmin else inicio
    d_fin = min(fin, tmax)
    el["ventana_descargada"] = {"inicio": iso(d_ini), "fin": iso(d_fin)}
    nombre = nombre_archivo(producto.dataset_id, producto.variables, zona.id, d_ini, d_fin, run_id)
    temporal = Path(raiz) / ".tmp" / run_id
    Path(ruta_nativa(temporal)).mkdir(parents=True, exist_ok=True)
    try:
        ruta_tmp, n = con_reintentos(lambda: cliente.descargar(producto, zona, d_ini, d_fin, temporal, nombre),
                                     cfg.reintentos_maximo, cfg.esperas_s, bit, {**ctx, "paso": "descarga"}, dormir)
        el["intentos"] += n
    except FallaDescarga as f:
        el["intentos"] += f.intentos
        if f.tipo == FUERA_DE_LIMITES:
            return cerrar(E.FUERA_DE_DOMINIO, f.mensaje)
        return cerrar(E.ERROR, f"{f.tipo}: {f.mensaje}")

    # 4. validación y conservación del original
    res = validar_archivo(ruta_tmp, producto, zona, inicio, fin, cfg.fraccion_minima_validas, meta.get("paso_tiempo_s"))
    el.update(unidades=res.unidades, control=res.estadisticos, controles_aplicados=res.controles,
              niveles_efectivos_m=res.niveles_m, area_efectiva=res.area_efectiva,
              resolucion_efectiva=res.resolucion_efectiva)
    if res.cobertura_inicio is not None:
        el["cobertura_efectiva"] = {"inicio": iso(res.cobertura_inicio), "fin": iso(res.cobertura_fin),
                                    "instantes": res.n_tiempos}
        el["antiguedad_horas"] = round((utc(ahora) - res.cobertura_fin).total_seconds() / 3600, 1)
    ruta_tmp = Path(ruta_tmp)
    if Path(ruta_nativa(ruta_tmp)).exists():
        destino = (ruta_cuarentena(raiz, run_id, nombre) if res.estado == E.NO_VALIDADO
                   else ruta_original(raiz, producto.dataset_id, producto.variables, zona.id, d_ini, nombre))
        final = mover_sin_sobrescribir(ruta_tmp, destino)
        el["archivo"] = final.relative_to(raiz).as_posix()
        el["tamano_bytes"] = Path(ruta_nativa(final)).stat().st_size
        el["sha256"] = sha256(final)
    return cerrar(res.estado, res.causa)


def ejecutar(cfg, raiz, cliente, ahora: datetime | None = None, modo: str = "manual",
             zonas=None, productos=None, dormir=time.sleep, eco: bool = True):
    ahora = utc(ahora or datetime.now(timezone.utc))
    run_id = sello(ahora) + "_" + uuid.uuid4().hex[:12]
    raiz = Path(raiz)
    Path(ruta_nativa(raiz)).mkdir(parents=True, exist_ok=True)
    bit = Bitacora(ruta_bitacora(raiz, ahora, run_id), run_id, eco)
    inicio, fin = ventana(ahora, cfg.ventana_dias)
    bit.evento(evento="inicio_ejecucion", modo=modo, ventana_inicio=iso(inicio), ventana_fin=iso(fin),
               config=cfg.ruta, config_sha256=cfg.sha256, version_modulo=__version__)

    elementos, omitidos = [], []
    for seleccion, existentes, nombre in ((zonas, cfg.zonas, "zonas"), (productos, cfg.productos, "productos")):
        desconocidos = set(seleccion or ()) - {x.id for x in existentes}
        if desconocidos:
            raise ConfigError(f"{nombre} desconocidos: {', '.join(sorted(desconocidos))}")
    for zona in cfg.zonas:
        if zonas and zona.id not in zonas:
            continue
        for producto in cfg.productos:
            if productos and producto.id not in productos:
                continue
            if not toca(producto, ahora, modo):
                omitidos.append({"zona_id": zona.id, "producto_id": producto.id, "motivo": "frecuencia_h"})
                bit.evento(evento="omitido_por_frecuencia", zona=zona.id, producto=producto.id)
                continue
            try:
                el = _elemento_base(producto, zona, inicio, fin)
                elementos.append(procesar(cfg, raiz, cliente, producto, zona, inicio, fin, ahora, run_id, bit, dormir, el))
            except Exception as exc:  # noqa: BLE001 - un elemento no detiene la ejecución
                el.update(estado=E.ERROR, causa=limpiar(f"inesperado: {resumen(exc)}"))
                el["procesado_utc"] = iso(datetime.now(timezone.utc))
                bit.evento(evento="fin_elemento", estado=E.ERROR, causa=el["causa"], zona=zona.id, producto=producto.id)
                elementos.append(el)

    fin_run = datetime.now(timezone.utc)
    resumen_estados = {e: sum(1 for x in elementos if x["estado"] == e) for e in E.ESTADOS}
    manifiesto = {
        "schema_version": SCHEMA_VERSION, "run_id": run_id,
        "inicio_utc": iso(ahora), "fin_utc": iso(fin_run), "modo": modo,
        "commit": _commit(), "config": cfg.ruta, "config_sha256": cfg.sha256, "version_modulo": __version__,
        "herramientas": {"python": platform.python_version(), "copernicusmarine": cliente.version_herramienta()},
        "ventana_solicitada": {"inicio": iso(inicio), "fin": iso(fin)},
        "resumen_estados": resumen_estados, "omitidos": omitidos, "elementos": elementos,
        "temporales_conservados": [p.relative_to(Path(ruta_nativa(raiz))).as_posix()
                                   for p in Path(ruta_nativa(raiz / ".tmp" / run_id)).glob("*")]
                                  if resumen_estados[E.ERROR] else [],
    }
    manifiesto = limpiar(manifiesto)
    from .snapshot import construir_snapshot
    escribir_json(raiz / "snapshots" / f"snapshot_{run_id}.json", construir_snapshot(manifiesto))
    ruta = escribir_json(ruta_manifiesto(raiz, ahora, run_id), manifiesto)
    bit.evento(evento="fin_ejecucion", manifiesto=ruta.relative_to(raiz).as_posix(),
               resumen_estados=resumen_estados, duracion_s=round((fin_run - ahora).total_seconds(), 1))
    if not resumen_estados[E.ERROR]:
        shutil.rmtree(ruta_nativa(raiz / ".tmp" / run_id), ignore_errors=True)
    return manifiesto, ruta


def _cargar_env(ruta: Path = Path(".env")):
    """Carga KEY=VALOR de un archivo .env local (excluido del control de versiones), sin sobrescribir el entorno."""
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m acquisition.run",
                                description="Descarga periódica de datos de Copernicus Marine Service")
    p.add_argument("--config", default="config/adquisicion.yaml")
    p.add_argument("--data-root", default=None, help="carpeta de datos; por defecto, la variable DATA_ROOT")
    p.add_argument("--modo", choices=["programada", "manual"], default="manual")
    p.add_argument("--zonas", default=None, help="ids de zona separados por coma (por defecto, todas)")
    p.add_argument("--productos", default=None, help="ids de producto separados por coma (por defecto, todos)")
    a = p.parse_args(argv)

    _cargar_env()
    try:
        cfg = cargar(a.config, a.data_root)
    except ConfigError as exc:
        print(f"Configuración inválida: {exc}", file=sys.stderr)
        return 2
    faltan = [n for n in CREDENCIALES if not os.environ.get(n)]
    if faltan:
        print("Faltan las variables de entorno: " + ", ".join(faltan), file=sys.stderr)
        return 2

    from .cliente import ClienteCopernicus

    try:
        manifiesto, ruta = ejecutar(cfg, cfg.raiz_datos, ClienteCopernicus(), modo=a.modo,
                                    zonas=[x.strip() for x in a.zonas.split(",")] if a.zonas else None,
                                    productos=[x.strip() for x in a.productos.split(",")] if a.productos else None)
    except ConfigError as exc:
        print(f"Configuración inválida: {exc}", file=sys.stderr)
        return 2
    print(f"Manifiesto: {ruta}")
    print("Resumen de estados: " + json.dumps(manifiesto["resumen_estados"], ensure_ascii=False))
    return codigo_salida(manifiesto)


def codigo_salida(manifiesto):
    """La ausencia publicada no es un fallo técnico; error/no_validado sí lo son."""
    return 1 if any(manifiesto["resumen_estados"].get(e, 0) for e in (E.ERROR, E.NO_VALIDADO)) else 0


if __name__ == "__main__":
    sys.exit(main())
