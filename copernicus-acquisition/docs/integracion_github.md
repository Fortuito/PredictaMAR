# Integración en PredictaMAR

El módulo se incorpora en `copernicus-acquisition/`. Los workflows se ubican en `.github/workflows/` de la raíz y ejecutan los comandos desde el directorio del módulo. Los archivos Python conservan el contenido de la versión local v2.1.0 validada.

## Comprobación después de subir

1. Revisar el pull request y el resultado de `Copernicus pruebas`.
2. Configurar en Settings > Secrets and variables > Actions los secretos `COPERNICUSMARINE_SERVICE_USERNAME` y `COPERNICUSMARINE_SERVICE_PASSWORD`.
3. Integrar la rama revisada en main. El workflow de adquisición configura las 14:17 UTC, equivalentes a las 09:17 de Perú.
4. En Actions > Copernicus adquisición > Run workflow, ejecutar una corrida y descargar el artefacto. Conservar después el registro de un disparo automático para acreditar periodicidad.
5. Crear la etiqueta remota v2.1.0 sobre el commit integrado. Registrar ese SHA en el informe junto con el SHA de la validación local previa. Son identificadores de dos etapas de la entrega.

La validación local del 15 de noviembre de 2026 procesó siete productos en dos zonas. Produjo ocho resultados disponibles y seis parciales. Las pruebas locales de aquella versión registraron 75 aprobadas y 14 omitidas. La evidencia de esa corrida se adjunta al informe del servicio.

Los originales NetCDF y los registros operacionales se conservan fuera del código. Los artefactos de Actions se retienen 90 días y requieren conservación privada permanente según las decisiones del proyecto.
