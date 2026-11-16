"""Regresiones de la revisión; todos los datos son sintéticos, salvo firma del SDK instalado."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
import xarray as xr

from acquisition import estados as E
from acquisition.almacenamiento import escribir_json
from acquisition.config import ConfigError
from acquisition.run import ejecutar, codigo_salida
from conftest import AHORA, ClienteFalso, config, escribir_nc, zona, producto
from test_validacion import INI, FIN, _validar


def test_hueco_interior_no_es_disponible(tmp_path):
    ruta = escribir_nc(tmp_path / 'completo.nc', inicio=INI, fin=FIN)
    with xr.open_dataset(ruta) as ds:
        ds.isel(time=[0, -1]).to_netcdf(tmp_path / 'hueco.nc')
    r = _validar(tmp_path / 'hueco.nc')
    assert r.estado == E.PARCIAL
    assert 'faltan instantes' in r.causa


def test_tiempos_duplicados_no_son_validos(tmp_path):
    ruta = escribir_nc(tmp_path / 'completo.nc', inicio=INI, fin=FIN)
    with xr.open_dataset(ruta) as ds:
        ds.isel(time=[0, 0, 1, 2, 3, 4, 5, 6, 7]).to_netcdf(tmp_path / 'dup.nc')
    assert _validar(tmp_path / 'dup.nc').estado == E.NO_VALIDADO


def test_area_incompleta_no_es_disponible(tmp_path):
    ruta = escribir_nc(tmp_path / 'area.nc', inicio=INI, fin=FIN,
                       lat=(-12.48, -12.42), lon=(-76.88, -76.82))
    assert _validar(ruta).estado == E.PARCIAL


def test_fallo_lectura_se_conserva_en_cuarentena(tmp_path, monkeypatch):
    import acquisition.validacion as val
    def fallar(self, **kw):
        raise OSError('contenido truncado')
    monkeypatch.setattr(val.xr.Dataset, 'load', fallar)
    m, _ = ejecutar(config(tmp_path), tmp_path, ClienteFalso(), ahora=AHORA, eco=False)
    el = m['elementos'][0]
    assert el['estado'] == E.NO_VALIDADO
    assert el['intentos'] == 2
    assert el['archivo'].startswith('cuarentena/')
    assert (tmp_path / el['archivo']).exists()


def test_secretos_no_aparecen_en_ninguna_salida(tmp_path, monkeypatch):
    monkeypatch.setenv('COPERNICUSMARINE_SERVICE_USERNAME', 'secreto_usuario')
    monkeypatch.setenv('COPERNICUSMARINE_SERVICE_PASSWORD', 'clave_privada')
    cliente = ClienteFalso(fallas_descarga=[ValueError('secreto_usuario clave_privada')])
    m, _ = ejecutar(config(tmp_path), tmp_path, cliente, ahora=AHORA, eco=False)
    assert 'secreto_usuario' not in json.dumps(m)
    for p in tmp_path.rglob('*'):
        if p.suffix in ('.json', '.jsonl'):
            texto = p.read_text(encoding='utf-8')
            assert 'secreto_usuario' not in texto and 'clave_privada' not in texto


@pytest.mark.parametrize('estado,esperado', [(E.ERROR, 1), (E.NO_VALIDADO, 1), (E.SIN_DATO, 0), (E.PARCIAL, 0)])
def test_codigo_salida_refleja_fallos(estado, esperado):
    assert codigo_salida({'resumen_estados': {estado: 1}}) == esperado


def test_no_sobrescribe_con_escritores_concurrentes(tmp_path):
    with ThreadPoolExecutor(max_workers=8) as pool:
        rutas = list(pool.map(lambda i: escribir_json(tmp_path / 'm.json', {'i': i}), range(20)))
    assert len(set(rutas)) == 20
    assert {json.loads(p.read_text())['i'] for p in rutas} == set(range(20))


def test_snapshot_dos_zonas_con_trazabilidad(tmp_path):
    cfg = config(tmp_path, zonas=[zona(), zona(id='z2', lat_min=-13, lat_max=-12.7)])
    m, _ = ejecutar(cfg, tmp_path, ClienteFalso(), ahora=AHORA, eco=False)
    snap = json.loads(next((tmp_path / 'snapshots').glob('*.json')).read_text(encoding='utf-8'))
    assert {v['zona_id'] for v in snap['variables']} == {'z1', 'z2'}
    assert all(v['estadisticas_area_ventana']['media'] == 18 for v in snap['variables'])
    assert all(v['niveles_efectivos_m'] == [0.494, 9.573, 11.405] for v in snap['variables'])
    assert all(v['area_efectiva'] and v['resolucion_efectiva'] for v in snap['variables'])


def test_seleccion_inexistente_no_da_exito_vacio(tmp_path):
    with pytest.raises(ConfigError):
        ejecutar(config(tmp_path), tmp_path, ClienteFalso(), zonas=['inexistente'], eco=False)


def test_version_fijada_se_envia_al_sdk(tmp_path):
    from test_cliente import HerramientaFalsa, _cliente
    h = HerramientaFalsa()
    _cliente(h).descargar(producto(dataset_version='202406'), zona(), INI, FIN, tmp_path, 'a.nc')
    assert h.llamadas[-1][1]['dataset_version'] == '202406'


def test_cli_finaliza_con_error_y_conserva_reporte(tmp_path, monkeypatch):
    from pathlib import Path
    from acquisition.run import main
    import acquisition.cliente as cliente
    monkeypatch.setenv('COPERNICUSMARINE_SERVICE_USERNAME', 'usuario_prueba')
    monkeypatch.setenv('COPERNICUSMARINE_SERVICE_PASSWORD', 'clave_prueba')
    monkeypatch.setattr(cliente, 'ClienteCopernicus', lambda: ClienteFalso(
        fallas_descarga=[ValueError('configuración incorrecta')]))
    cfg = Path(__file__).resolve().parents[1] / 'config/adquisicion.yaml'
    assert main(['--config', str(cfg), '--data-root', str(tmp_path),
                 '--zonas', 'pucusana_costera', '--productos', 'temperatura_modelo']) == 1
    assert list(tmp_path.rglob('manifiesto_*.json'))


def test_infinito_no_es_solo_ausencia(tmp_path):
    ruta = escribir_nc(tmp_path / 'infinito.nc', inicio=INI, fin=FIN, valor=float('inf'))
    assert _validar(ruta).estado == E.NO_VALIDADO


def test_no_acepta_fecha_cercana_fuera_de_ventana(tmp_path):
    from datetime import timedelta
    ruta = escribir_nc(tmp_path / 'fuera.nc', inicio=INI - timedelta(hours=6), fin=FIN)
    assert _validar(ruta).estado == E.NO_VALIDADO


def test_netcdf_en_ruta_larga(tmp_path):
    ruta = tmp_path / ('a' * 75) / ('b' * 75) / ('c' * 75) / 'archivo.nc'
    escribir_nc(ruta, inicio=INI, fin=FIN)
    assert _validar(ruta).estado == E.DISPONIBLE


def test_permiso_denegado_no_genera_reintentos():
    from acquisition.reintentos import clasificar, PARAMETROS
    assert clasificar(PermissionError('ruta no escribible')) == PARAMETROS


def test_ejecucion_completa_en_directorio_largo(tmp_path):
    from pathlib import Path
    from acquisition.almacenamiento import ruta_nativa
    raiz = tmp_path / ('d' * 70) / ('e' * 70) / ('f' * 70)
    m, ruta = ejecutar(config(raiz), raiz, ClienteFalso(), ahora=AHORA, eco=False)
    assert m['elementos'][0]['estado'] == E.DISPONIBLE
    assert Path(ruta_nativa(ruta)).exists()
