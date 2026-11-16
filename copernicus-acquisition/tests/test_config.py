from pathlib import Path

import pytest
import yaml

from acquisition.config import ConfigError, cargar

REPO_CONFIG = Path(__file__).resolve().parents[1] / "config" / "adquisicion.yaml"


def _escribir(tmp_path, cambios):
    d = yaml.safe_load(REPO_CONFIG.read_text(encoding="utf-8"))
    cambios(d)
    ruta = tmp_path / "c.yaml"
    ruta.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    return ruta


def test_config_del_repositorio_es_valida(tmp_path):
    cfg = cargar(REPO_CONFIG, raiz_datos=str(tmp_path))
    assert [z.id for z in cfg.zonas] == ["pucusana_costera", "pucusana_dominio"]
    assert len(cfg.productos) == 7
    assert cfg.reintentos_maximo == 3 and cfg.esperas_s == (30.0, 120.0, 300.0)
    assert len(cfg.sha256) == 64


def test_exige_carpeta_de_datos(monkeypatch):
    monkeypatch.delenv("DATA_ROOT", raising=False)
    with pytest.raises(ConfigError, match="DATA_ROOT"):
        cargar(REPO_CONFIG)


def test_toma_data_root_del_entorno(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    assert cargar(REPO_CONFIG).raiz_datos == str(tmp_path)


@pytest.mark.parametrize("cambio, mensaje", [
    (lambda d: d["zonas"][0].update(lat=[-12.3, -12.6]), "lat"),
    (lambda d: d["zonas"].append(dict(d["zonas"][0])), "repetidos"),
    (lambda d: d["reintentos"].update(esperas_s=[30, 120]), "esperas_s"),
    (lambda d: d["productos"][0].update(frecuencia_h=12), "múltiplo de 24"),
    (lambda d: d["productos"][0].update(tipo_dato="otro"), "tipo_dato"),
    (lambda d: d["productos"][0].update(rango_plausible={"xx": [0, 1]}), "no está en variables"),
    (lambda d: d["productos"][0].update(variables=[]), "variables"),
    (lambda d: d.update(version_configuracion=2), "version_configuracion"),
])
def test_rechaza_configuraciones_invalidas(tmp_path, cambio, mensaje):
    ruta = _escribir(tmp_path, cambio)
    with pytest.raises(ConfigError, match=mensaje):
        cargar(ruta, raiz_datos=str(tmp_path))


def test_validar_config_cli(capsys):
    from acquisition.validar_config import main
    assert main([str(REPO_CONFIG)]) == 0
    assert "OK" in capsys.readouterr().out
