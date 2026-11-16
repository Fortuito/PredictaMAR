from datetime import datetime, timezone

import pytest

from acquisition import estados as E
from acquisition.validacion import validar_archivo
from conftest import escribir_nc, producto, zona

INI = datetime(2026, 11, 14, 0, 0, 0, tzinfo=timezone.utc)
FIN = datetime(2026, 11, 15, 23, 59, 59, tzinfo=timezone.utc)


def _validar(ruta, prod=None, z=None, frac=0.5):
    return validar_archivo(ruta, prod or producto(), z or zona(), INI, FIN, frac, 21600.0)


def test_archivo_completo_disponible(tmp_path):
    r = _validar(escribir_nc(tmp_path / "a.nc", inicio=INI, fin=FIN))
    assert r.estado == E.DISPONIBLE, r.causa
    assert r.niveles_m == [0.494, 9.573, 11.405]
    assert r.n_tiempos == 8 and r.estadisticos["thetao"]["fraccion_validas"] == 1.0
    assert r.unidades["thetao"] == "degrees_C"
    assert all(c["cumple"] for c in r.controles)


def test_cobertura_temporal_parcial(tmp_path):
    r = _validar(escribir_nc(tmp_path / "a.nc", inicio=INI, fin=datetime(2026, 11, 14, 18, tzinfo=timezone.utc)))
    assert r.estado == E.PARCIAL and "parte de la ventana" in r.causa


def test_pocas_celdas_con_dato_es_parcial(tmp_path):
    r = _validar(escribir_nc(tmp_path / "a.nc", inicio=INI, fin=FIN, frac_nan=0.6))
    assert r.estado == E.PARCIAL and "umbral" in r.causa


def test_sin_celdas_con_dato_es_sin_dato(tmp_path):
    r = _validar(escribir_nc(tmp_path / "a.nc", inicio=INI, fin=FIN, frac_nan=1.0))
    assert r.estado == E.SIN_DATO


def test_sin_instantes_es_sin_dato(tmp_path):
    r = _validar(escribir_nc(tmp_path / "a.nc", inicio=INI, fin=FIN, sin_tiempos=True))
    assert r.estado == E.SIN_DATO


def test_archivo_vacio_no_validado(tmp_path):
    f = tmp_path / "vacio.nc"
    f.write_bytes(b"")
    assert _validar(f).estado == E.NO_VALIDADO


def test_archivo_corrupto_no_validado(tmp_path):
    f = tmp_path / "corrupto.nc"
    f.write_bytes(b"esto no es netcdf")
    assert _validar(f).estado == E.NO_VALIDADO


@pytest.mark.parametrize("opciones, prod, texto", [
    ({"var": "otra"}, None, "faltan variables"),
    ({"unidades": "kelvin"}, None, "unidades"),
    ({"valor": 99.0}, None, "rango plausible"),
    ({"lat": (-14.0, -13.5)}, None, "fuera del área"),
    ({"profundidades": (0.494, 50.0)}, None, "niveles fuera"),
    ({}, producto(profundidad_m=None, variables=("thetao",)), None),
])
def test_controles_que_fallan(tmp_path, opciones, prod, texto):
    r = _validar(escribir_nc(tmp_path / "a.nc", inicio=INI, fin=FIN, **opciones), prod=prod)
    if texto is None:
        assert r.estado == E.DISPONIBLE   # sin rango de profundidad configurado, los niveles solo se registran
        assert r.niveles_m == [0.494, 9.573, 11.405]
    else:
        assert r.estado == E.NO_VALIDADO and texto in r.causa
