# Esquema del manifiesto (schema_version 1.1)

`run_id` contiene inicio UTC y sufijo aleatorio. `dataset_version` se fija en la descarga y consulta, configurada en YAML o resuelta del catálogo una vez por cliente. `area_efectiva` y `resolucion_efectiva` describen coordenadas y pasos nativos recibidos. `procesado_utc` marca el cierre del elemento. `tratamiento` declara recorte sin interpolación ni imputación. `temporales_conservados` lista archivos residuales de una ejecución con error.

## Snapshot de área (schema_version 1.0)

Se guarda en `snapshots/`. `tipo=resumen_adquisicion_por_area` distingue esta salida de un snapshot puntual. Cada entrada de `variables` contiene identificación del producto y versión, ventana nominal, cobertura efectiva, procesamiento UTC, antigüedad, área solicitada/efectiva, niveles solicitados/efectivos, resolución, estado, causa, tratamiento, unidades, fracción válida, estadísticas del área y ventana, archivo original y huella. `distancia_coordenadas_km=null` significa no aplicable a áreas, no distancia cero. `estadisticas_area_ventana` contiene mínimo, máximo y media solo para estados disponible/parcial; en los demás son null. No contiene valores imputados, gradientes ni interpolaciones. No se deben interpretar medias del área/ventana como valores en un punto o fecha nominal.

## Nivel de ejecución
| Campo | Descripción |
|---|---|
| `schema_version` | versión del esquema |
| `run_id`, `inicio_utc`, `fin_utc` | identificador (marca UTC de inicio) y horas UTC de inicio y fin |
| `modo` | `programada` o `manual` |
| `commit`, `config`, `config_sha256`, `version_modulo` | versión del código y huella de la configuración |
| `herramientas` | versiones de Python y de copernicusmarine |
| `ventana_solicitada` | inicio y fin UTC de la ventana |
| `resumen_estados` | número de elementos por estado |
| `omitidos` | combinaciones no ejecutadas por su frecuencia configurada |
| `elementos` | lista de elementos (zona × producto) |

## Nivel de elemento
| Campo | Descripción |
|---|---|
| `zona_id`, `area_solicitada` | zona y límites solicitados |
| `producto_id`, `dataset_id`, `product_id`, `dataset_version` | producto y versión vigente según el catálogo |
| `tipo_dato` | `modelo`, `observacion_L3` o `analisis_L4` |
| `variables`, `unidades` | variables y unidades tal como las entrega el producto |
| `ventana_solicitada`, `ventana_descargada` | ventana pedida y recorte realmente descargado |
| `cobertura_efectiva` | primer y último instante presentes en el archivo y número de instantes |
| `ultima_disponible`, `antiguedad_horas` | último instante publicado y horas hasta la ejecución |
| `profundidad_solicitada_m`, `niveles_efectivos_m` | rango pedido y niveles nativos descargados |
| `archivo`, `tamano_bytes`, `sha256` | ruta relativa a `DATA_ROOT`, tamaño y huella del original |
| `estado`, `causa` | estado de disponibilidad y motivo |
| `intentos`, `duracion_s` | intentos (incluye consulta de cobertura y descarga) y duración |
| `control` | por variable: número de celdas, fracción válida, mínimo, máximo, media y unidades |
| `controles_aplicados` | resultado de cada control de integridad |
