import json
from datetime import datetime, timezone

from acquisition import estados as E
from acquisition.almacenamiento import sha256
from acquisition.run import ejecutar, toca, ventana
from conftest import AHORA, ClienteFalso, config, producto, zona

CAMPOS_ELEMENTO = {
    "zona_id", "area_solicitada", "producto_id", "dataset_id", "product_id", "dataset_version", "tipo_dato",
    "variables", "unidades", "ventana_solicitada", "ventana_descargada", "cobertura_efectiva", "ultima_disponible",
    "antiguedad_horas", "profundidad_solicitada_m", "niveles_efectivos_m", "archivo", "tamano_bytes", "sha256",
    "estado", "causa", "intentos", "duracion_s", "control", "controles_aplicados",
}


def _correr(tmp_path, cliente, cfg=None, **kw):
    return ejecutar(cfg or config(tmp_path), tmp_path, cliente, ahora=AHORA, dormir=lambda s: None, eco=False, **kw)


def test_ventana_de_dos_dias_utc():
    ini, fin = ventana(AHORA, 2)
    assert ini == datetime(2026, 11, 14, tzinfo=timezone.utc)
    assert fin == datetime(2026, 11, 15, 23, 59, 59, tzinfo=timezone.utc)


def test_ejecucion_completa_genera_manifiesto_bitacora_y_originales(tmp_path):
    cfg = config(tmp_path, productos=[producto(), producto(id="p2", dataset_id="ds2", variables=("VHM0",),
                                                          profundidad_m=None, unidades_esperadas={},
                                                          rango_plausible={})])
    manifiesto, ruta = _correr(tmp_path, ClienteFalso(), cfg)
    assert ruta.exists() and ruta.relative_to(tmp_path).as_posix() == f"manifiestos/2026/11/manifiesto_{manifiesto['run_id']}.json"
    assert json.loads(ruta.read_text(encoding="utf-8"))["schema_version"] == "1.1"
    assert manifiesto["run_id"].startswith("20261116T141703Z_") and manifiesto["modo"] == "manual"
    assert manifiesto["resumen_estados"][E.DISPONIBLE] == 2
    for el in manifiesto["elementos"]:
        assert CAMPOS_ELEMENTO <= set(el)
        assert el["estado"] == E.DISPONIBLE and el["dataset_version"] == "202406"
        archivo = tmp_path / el["archivo"]
        assert archivo.exists() and archivo.as_posix().startswith((tmp_path / "originales").as_posix())
        assert el["sha256"] == sha256(archivo)
    lineas = next(tmp_path.rglob("bitacora_*.jsonl")).read_text(encoding="utf-8").splitlines()
    eventos = [json.loads(x)["evento"] for x in lineas]
    assert eventos[0] == "inicio_ejecucion" and eventos[-1] == "fin_ejecucion"
    assert not (tmp_path / ".tmp" / manifiesto["run_id"]).exists()


def test_sin_dato_no_descarga_otra_fecha(tmp_path):
    cliente = ClienteFalso()
    cliente.meta["tiempo_max"] = datetime(2026, 11, 10, tzinfo=timezone.utc)
    manifiesto, _ = _correr(tmp_path, cliente)
    el = manifiesto["elementos"][0]
    assert el["estado"] == E.SIN_DATO and cliente.descargas == 0
    assert el["ultima_disponible"] == "2026-11-10T00:00:00Z" and el["antiguedad_horas"] > 0


def test_demora_del_producto_queda_como_parcial(tmp_path):
    cliente = ClienteFalso()
    cliente.meta["tiempo_max"] = datetime(2026, 11, 14, 18, tzinfo=timezone.utc)
    el = _correr(tmp_path, cliente)[0]["elementos"][0]
    assert el["estado"] == E.PARCIAL
    assert el["ventana_descargada"]["fin"] == "2026-11-14T18:00:00Z"
    assert el["ventana_solicitada"]["fin"] == "2026-11-15T23:59:59Z"


def test_zona_fuera_del_producto(tmp_path):
    cliente = ClienteFalso()
    cliente.meta.update(lat_min=10.0, lat_max=20.0)
    el = _correr(tmp_path, cliente)[0]["elementos"][0]
    assert el["estado"] == E.FUERA_DE_DOMINIO and cliente.descargas == 0


def test_profundidad_fuera_del_producto(tmp_path):
    cliente = ClienteFalso()
    cliente.meta["profundidades"] = [50.0, 100.0]
    assert _correr(tmp_path, cliente)[0]["elementos"][0]["estado"] == E.FUERA_DE_DOMINIO


def test_error_tras_reintentos(tmp_path):
    cliente = ClienteFalso(fallas_descarga=[ConnectionError("caído")] * 4)
    el = _correr(tmp_path, cliente)[0]["elementos"][0]
    assert el["estado"] == E.ERROR and el["intentos"] == 1 + 4 and "transitorio" in el["causa"]


def test_archivo_invalido_va_a_cuarentena(tmp_path):
    cliente = ClienteFalso(opciones_nc={"unidades": "kelvin"})
    el = _correr(tmp_path, cliente)[0]["elementos"][0]
    assert el["estado"] == E.NO_VALIDADO and el["archivo"].startswith("cuarentena/")


def test_frecuencia_por_producto(tmp_path):
    p48 = producto(frecuencia_h=48)
    impar = datetime(2026, 11, 16, 14, 17, tzinfo=timezone.utc)
    assert toca(p48, impar, "manual") is True
    assert toca(p48, impar, "programada") == (impar.date().toordinal() % 2 == 0)


def test_dos_ejecuciones_no_se_sobrescriben(tmp_path):
    _, r1 = _correr(tmp_path, ClienteFalso())
    _, r2 = _correr(tmp_path, ClienteFalso())
    assert r1 != r2 and r1.exists() and r2.exists()
    assert len(list((tmp_path / "originales").rglob("*.nc"))) == 2


def test_la_bitacora_no_registra_credenciales(tmp_path, monkeypatch):
    monkeypatch.setenv("COPERNICUSMARINE_SERVICE_USERNAME", "usuario_secreto")
    cliente = ClienteFalso(fallas_descarga=[RuntimeError("fallo para usuario_secreto: dataset no existe")])
    _correr(tmp_path, cliente)
    texto = next(tmp_path.rglob("bitacora_*.jsonl")).read_text(encoding="utf-8")
    assert "usuario_secreto" not in texto and "***" in texto
