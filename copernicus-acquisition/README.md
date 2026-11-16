# Adquisición periódica de datos de Copernicus Marine Service — PredictaMAR

Versión **2.1.0**. Desde la raíz del repositorio, ejecutar `cd copernicus-acquisition` antes de los comandos siguientes. Los workflows están en `.github/workflows/copernicus-adquisicion.yml` y `.github/workflows/copernicus-pruebas.yml` de la raíz. Ver `docs/integracion_github.md`.

Primer entregable del servicio «Automatización de la descarga periódica de datos desde Copernicus».
El módulo descarga, de forma programada, los archivos originales (NetCDF) de los productos y zonas
definidos en `config/adquisicion.yaml`; valida cada archivo; le asigna un estado de disponibilidad;
lo conserva sin sobrescribir; y deja un manifiesto y una bitácora por ejecución.

Este entregable no transforma los datos. La lectura y transformación de los NetCDF, la extracción
por punto, las variables derivadas y la conversión a hora local corresponden al pipeline de
procesamiento (siguiente entregable).

## Estructura

| Carpeta | Contenido |
|---|---|
| `acquisition/` | cliente de Copernicus Marine, descarga, validación, estados, manifiesto y bitácora |
| `config/` | `adquisicion.yaml`: productos, variables, zonas, profundidades, frecuencias y parámetros |
| `tests/` | pruebas unitarias (datos sintéticos) e integradas (descargas reales, requieren credenciales) |
| `docs/` | manual de operación y esquema del manifiesto |
| `../.github/workflows/` | `copernicus-adquisicion.yml` y `copernicus-pruebas.yml` |

## Uso rápido

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.lock
export COPERNICUSMARINE_SERVICE_USERNAME=...   # o en un archivo .env (excluido de git)
export COPERNICUSMARINE_SERVICE_PASSWORD=...
export DATA_ROOT=/ruta/fuera/del/repositorio
python -m acquisition.run --config config/adquisicion.yaml
```

Opciones: `--data-root`, `--modo programada|manual`, `--zonas id1,id2`, `--productos id1,id2`.
Validar la configuración: `python -m acquisition.validar_config config/adquisicion.yaml`.
Pruebas: `pytest --cov=acquisition` (las integradas se omiten si no hay credenciales).

## Salidas (bajo `DATA_ROOT`)

```
originales/<dataset_id>/<variables>/<zona>/<AAAA>/<MM>/<dataset>__<variables>__<zona>__<inicio>_<fin>__<run_id>.nc
cuarentena/<run_id>/                      archivos que no pasaron la validación
manifiestos/<AAAA>/<MM>/manifiesto_<run_id>.json
snapshots/snapshot_<run_id>.json          resumen por variable y área, sin imputación
bitacoras/<AAAA>/<MM>/bitacora_<run_id>.jsonl
```

Todas las fechas están en UTC. Estados: `disponible`, `parcial`, `sin_dato`, `fuera_de_dominio`,
`no_validado`, `error`. Ningún archivo, dato descargado ni credencial se versiona en el repositorio.
