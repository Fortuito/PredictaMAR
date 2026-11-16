import pytest

from acquisition.reintentos import (AUTENTICACION, FUERA_DE_LIMITES, PARAMETROS, TRANSITORIO, FallaDescarga,
                                    clasificar, con_reintentos)


class BitacoraNula:
    def __init__(self):
        self.eventos = []

    def evento(self, **campos):
        self.eventos.append(campos)


class InvalidUsernameOrPassword(Exception):
    pass


class CoordinatesOutOfDatasetBounds(Exception):
    pass


class DatasetNotFound(Exception):
    pass


@pytest.mark.parametrize("exc, tipo", [
    (TimeoutError("timed out"), TRANSITORIO),
    (ConnectionError("reset"), TRANSITORIO),
    (RuntimeError("HTTP 503 Service Unavailable"), TRANSITORIO),
    (InvalidUsernameOrPassword("bad"), AUTENTICACION),
    (CoordinatesOutOfDatasetBounds("x"), FUERA_DE_LIMITES),
    (DatasetNotFound("x"), PARAMETROS),
])
def test_clasificacion(exc, tipo):
    assert clasificar(exc) == tipo


def test_reintenta_fallas_transitorias(sin_espera):
    esperas, dormir = sin_espera
    fallas = [TimeoutError("t1"), ConnectionError("t2")]

    def fn():
        if fallas:
            raise fallas.pop(0)
        return "ok"

    bit = BitacoraNula()
    resultado, intentos = con_reintentos(fn, 3, (30, 120, 300), bit, {"zona": "z"}, dormir)
    assert resultado == "ok" and intentos == 3 and esperas == [30.0, 120.0]
    assert [e["evento"] for e in bit.eventos].count("reintento") == 2


def test_un_intento_inicial_y_tres_reintentos(sin_espera):
    esperas, dormir = sin_espera

    def fn():
        raise ConnectionError("caído")

    with pytest.raises(FallaDescarga) as info:
        con_reintentos(fn, 3, (30, 120, 300), BitacoraNula(), {}, dormir)
    assert info.value.tipo == TRANSITORIO and info.value.intentos == 4 and esperas == [30.0, 120.0, 300.0]


def test_no_reintenta_autenticacion(sin_espera):
    esperas, dormir = sin_espera

    def fn():
        raise InvalidUsernameOrPassword("credenciales")

    with pytest.raises(FallaDescarga) as info:
        con_reintentos(fn, 3, (30, 120, 300), BitacoraNula(), {}, dormir)
    assert info.value.tipo == AUTENTICACION and info.value.intentos == 1 and esperas == []
