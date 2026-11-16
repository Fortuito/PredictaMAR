import json
from datetime import datetime, timezone

from acquisition.almacenamiento import (destino_libre, escribir_json, iso, mover_sin_sobrescribir, nombre_archivo,
                                        ruta_original, sello, sha256)

T0 = datetime(2026, 11, 14, 0, 0, 0, tzinfo=timezone.utc)
T1 = datetime(2026, 11, 15, 23, 59, 59, tzinfo=timezone.utc)


def test_fechas_en_utc_con_z():
    assert iso(T0) == "2026-11-14T00:00:00Z"
    assert sello(T1) == "20261115T235959Z"


def test_nombre_y_ruta_del_original(tmp_path):
    nombre = nombre_archivo("ds", ("uo", "vo"), "z1", T0, T1, "20261116T141703Z")
    assert nombre == "ds__uo-vo__z1__20261114T000000Z_20261115T235959Z__20261116T141703Z.nc"
    ruta = ruta_original(tmp_path, "ds", ("uo", "vo"), "z1", T0, nombre)
    assert ruta.relative_to(tmp_path).as_posix() == f"originales/ds/uo-vo/z1/2026/11/{nombre}"


def test_nunca_sobrescribe(tmp_path):
    destino = tmp_path / "a" / "x.nc"
    destino.parent.mkdir()
    destino.write_bytes(b"original")
    origen = tmp_path / "nuevo.nc"
    origen.write_bytes(b"nuevo")
    final = mover_sin_sobrescribir(origen, destino)
    assert final.name == "x__2.nc"
    assert destino.read_bytes() == b"original" and final.read_bytes() == b"nuevo"
    assert destino_libre(destino).name == "x__3.nc"


def test_json_atomico_y_sin_sobrescritura(tmp_path):
    a = escribir_json(tmp_path / "m.json", {"a": 1})
    b = escribir_json(tmp_path / "m.json", {"a": 2})
    assert a != b and json.loads(a.read_text())["a"] == 1 and json.loads(b.read_text())["a"] == 2
    assert not list(tmp_path.glob("*.tmp"))


def test_huella_sha256(tmp_path):
    f = tmp_path / "f.bin"
    f.write_bytes(b"abc")
    assert sha256(f) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
