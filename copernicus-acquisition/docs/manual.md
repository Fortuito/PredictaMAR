# Manual de instalación, configuración, operación y mantenimiento

## 1. Instalación
1. Clonar el repositorio privado y entrar en `copernicus-acquisition/`.
2. Crear un entorno con Python 3.12 e instalar las dependencias fijadas: `pip install -r requirements.lock`.
3. Definir `COPERNICUSMARINE_SERVICE_USERNAME`, `COPERNICUSMARINE_SERVICE_PASSWORD` y `DATA_ROOT`
   como variables de entorno o en un archivo `.env` (excluido del control de versiones).

## 2. Ejecución manual
`python -m acquisition.run --config config/adquisicion.yaml`
Al terminar, revisar el manifiesto y la bitácora de la ejecución en `DATA_ROOT/manifiestos` y `DATA_ROOT/bitacoras`.
Para una prueba corta: `--zonas pucusana_costera --productos tsm_ostia`.

## 3. Ejecución programada
El flujo `.github/workflows/copernicus-adquisicion.yml` de la raíz corre todos los días a las 14:17 UTC (09:17 en Perú) y
también puede lanzarse a mano desde Actions → Copernicus adquisición → Run workflow. Cada ejecución
publica sus archivos originales, su manifiesto y su bitácora como artefacto, con retención de 90 días.
Las credenciales se cargan en Settings → Secrets and variables → Actions. Para cambiar el horario se
edita la expresión `cron` mediante una solicitud de cambio.

## 4. Agregar una zona o una variable
Editar `config/adquisicion.yaml`, validar con `python -m acquisition.validar_config config/adquisicion.yaml`
y abrir una solicitud de cambio. No se modifica el código. Las variables, productos, profundidades y
zonas los define el equipo investigador.

## 5. Mantenimiento y solución de problemas
- **Error de autenticación:** revisar los secretos o las variables de entorno; no se reintenta.
- **`sin_dato` repetido:** revisar en el catálogo la demora de publicación del producto.
- **`no_validado`:** revisar el archivo en `cuarentena/`, sus unidades y si cambió la versión del dataset.
- **Actualizar dependencias:** regenerar `requirements.lock` y ejecutar todas las pruebas antes de fusionar.
