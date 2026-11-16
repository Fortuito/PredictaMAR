"""Pruebas integradas: descargas reales de Copernicus Marine Service (requieren credenciales)."""

import os
from pathlib import Path

import pytest

from acquisition.config import cargar
from acquisition.run import ejecutar

pytestmark = [
    pytest.mark.integracion,
    pytest.mark.skipif(not (os.environ.get("COPERNICUSMARINE_SERVICE_USERNAME")
                            and os.environ.get("COPERNICUSMARINE_SERVICE_PASSWORD")),
                       reason="sin credenciales de Copernicus Marine en el entorno"),
]

CONFIG = Path(__file__).resolve().parents[1] / "config" / "adquisicion.yaml"


@pytest.mark.parametrize("zona", ["pucusana_costera", "pucusana_dominio"])
@pytest.mark.parametrize("producto", [p.id for p in cargar(CONFIG, raiz_datos="datos_prueba").productos])
def test_descarga_real_en_pucusana(tmp_path, producto, zona):
    from acquisition.cliente import ClienteCopernicus

    cfg = cargar(CONFIG, raiz_datos=str(tmp_path))
    manifiesto, ruta = ejecutar(cfg, tmp_path, ClienteCopernicus(), modo="manual",
                                zonas=[zona], productos=[producto], eco=False)
    el = manifiesto["elementos"][0]
    assert el["estado"] in ("disponible", "parcial", "sin_dato"), el["causa"]
    assert el["dataset_version"] is not None
    if el["archivo"]:
        assert (tmp_path / el["archivo"]).exists() and len(el["sha256"]) == 64
