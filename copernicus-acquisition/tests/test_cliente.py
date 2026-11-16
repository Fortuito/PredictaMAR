import inspect
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from acquisition.cliente import ClienteCopernicus, extraer_metadatos
from conftest import producto, zona


class HerramientaFalsa:
    __version__ = "falsa"

    def __init__(self, catalogo=None, falla_describe=None):
        self.catalogo = catalogo
        self.falla_describe = falla_describe
        self.llamadas = []

    def describe(self, **kw):
        self.llamadas.append(("describe", kw))
        if self.falla_describe:
            raise self.falla_describe
        return self.catalogo

    def subset(self, **kw):
        self.llamadas.append(("subset", kw))
        return SimpleNamespace(file_path=Path(kw["output_directory"]) / kw["output_filename"])


def _cliente(herramienta):
    c = ClienteCopernicus.__new__(ClienteCopernicus)
    c._cm = herramienta
    return c


def test_extraer_metadatos():
    t = pd.date_range("2026-11-01", "2026-11-03", freq="6h")
    ds = xr.Dataset(coords={"time": t, "latitude": [-13.0, -12.0], "longitude": [-78.0, -76.0],
                            "depth": [0.494, 9.573]})
    meta = extraer_metadatos(ds)
    assert meta["tiempo_min"] == datetime(2026, 11, 1, tzinfo=timezone.utc)
    assert meta["tiempo_max"] == datetime(2026, 11, 3, tzinfo=timezone.utc)
    assert meta["paso_tiempo_s"] == 21600.0
    assert (meta["lat_min"], meta["lon_max"]) == (-13.0, -76.0)
    assert meta["profundidades"] == [0.494, 9.573]


def test_descarga_usa_los_argumentos_de_la_herramienta(tmp_path):
    h = HerramientaFalsa()
    ruta = _cliente(h).descargar(producto(dataset_version="202406"), zona(), datetime(2026, 11, 14, tzinfo=timezone.utc),
                                 datetime(2026, 11, 15, 23, 59, 59, tzinfo=timezone.utc), tmp_path, "a.nc")
    assert ruta == tmp_path / "a.nc"
    kw = h.llamadas[-1][1]
    assert kw["start_datetime"] == "2026-11-14T00:00:00" and kw["maximum_depth"] == 12.0
    try:
        import copernicusmarine
    except ImportError:
        pytest.skip("copernicusmarine no instalado")
    reales = set(inspect.signature(copernicusmarine.subset).parameters)
    assert set(kw) <= reales, set(kw) - reales


def test_identificacion_toma_la_version_vigente():
    version = lambda e: SimpleNamespace(label=e)  # noqa: E731
    cat = SimpleNamespace(products=[SimpleNamespace(product_id="PROD_X", datasets=[
        SimpleNamespace(dataset_id="ds_prueba", versions=[version("202211"), version("202406")])])])
    assert _cliente(HerramientaFalsa(cat)).identificacion("ds_prueba") == {"product_id": "PROD_X",
                                                                            "dataset_version": "202406"}


def test_identificacion_tolera_fallas_del_catalogo():
    c = _cliente(HerramientaFalsa(falla_describe=RuntimeError("sin catálogo")))
    assert c.identificacion("ds") == {"product_id": None, "dataset_version": None}


def test_cli_exige_credenciales(monkeypatch, tmp_path, capsys):
    from acquisition.run import main
    monkeypatch.delenv("COPERNICUSMARINE_SERVICE_USERNAME", raising=False)
    monkeypatch.delenv("COPERNICUSMARINE_SERVICE_PASSWORD", raising=False)
    monkeypatch.chdir(tmp_path)
    config = Path(__file__).resolve().parents[1] / "config" / "adquisicion.yaml"
    assert main(["--config", str(config), "--data-root", str(tmp_path)]) == 2
    assert "Faltan las variables de entorno" in capsys.readouterr().err


def test_cli_rechaza_configuracion_invalida(tmp_path, capsys):
    from acquisition.run import main
    mala = tmp_path / "mala.yaml"
    mala.write_text("version_configuracion: 9\n", encoding="utf-8")
    assert main(["--config", str(mala), "--data-root", str(tmp_path)]) == 2
    assert "Configuración inválida" in capsys.readouterr().err
