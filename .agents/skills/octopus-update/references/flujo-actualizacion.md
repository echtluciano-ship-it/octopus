# Flujo de Actualizacion

## 1. Preparacion

- Confirmar que el working tree no tenga cambios no relacionados. No revertir cambios del usuario.
- Leer `drive_sources.json`, `client_aliases.csv`, `manual_rentability_operations.csv`, `data_loader.py` y `app.py` cuando haga falta confirmar una regla vigente.
- Leer `source_documents.csv` antes de clasificar archivos y conservar sus decisiones humanas/identidades previas.
- Usar la skill de Google Drive para listar la carpeta oficial y sus subcarpetas de Pendientes/Pagos por mes.
- Leer los metadatos actuales de Facturacion Historica y Clientes/Alias. Comparar con `data/billing_source.json` y las validaciones persistidas. Si Facturacion cambio, descargar el XLSX oficial completo a `data/FACTURACION OCTOPUS.xlsx` y actualizar ID, version/fecha de modificacion y SHA-256 en `data/billing_source.json`. No dar la fuente por actualizada por haber procesado fotos nuevas.

## 2. Deteccion de Archivos Nuevos

- Listar Pendientes y Pagos de todos los meses disponibles, no solo el mes actual.
- Calcular/registrar la identidad documental en `source_documents.csv`: Drive ID, SHA-256, huella visual exacta, tamano y fecha de deteccion.
- Comparar cada archivo nuevo contra esas identidades. El nombre, cliente, fecha o importe no se usan como prueba automatica de duplicacion.
- Descargar o abrir visualmente solo los candidatos nuevos o dudosos.
- Ejecutar las pruebas de `tests/test_source_identity.py` cuando se modifique la deduplicacion.

## 3. Clasificacion

Cada archivo de Pendientes debe terminar clasificado como:

- `OK` si tiene datos completos y confiables.
- `OK_TRANSFERENCIA_1_2` si aplica la regla de costos ya pagados y comision 1,20%.
- `OK_FC_NETA` u `OK_FC_HISTORICA` si aplica una regla validada de FC neta o cruce con Facturacion Historica.
- `DUPLICADO` solo si coincide el Drive ID, SHA-256 o la imagen decodificada pixel por pixel con un archivo ya registrado; guardar `duplicate_of` y evidencia.
- `NO_PROCESAR` si una validacion humana previa o el contenido indica que no corresponde.
- `REVISION` si falta un dato clave o hay ambiguedad real.

Los archivos de Pagos se revisan como validacion/contexto, pero no se cargan como rentabilidad salvo instruccion especifica.

## 4. Fecha y Movimiento de Drive

- Leer la fecha real visible en el cuadro.
- Si el archivo esta en el mes equivocado y la fecha real es clara, moverlo a la carpeta mensual correcta usando Drive.
- Si no existe carpeta del mes correcto, informar el caso antes de improvisar una estructura nueva.
- Registrar en la nota del CSV que se movio o que se imputo por fecha real.

## 5. Carga de Datos

- Agregar operaciones validadas a `manual_rentability_operations.csv` conservando el `drive_id`.
- Cuando el cuadro tenga ECHEQ/cheque y Facturacion Neta, guardar ambos campos separados y usar Facturacion Neta como base de rentabilidad.
- No completar Facturacion Neta con ECHEQ para forzar un calculo; si falta y no aplica una regla especial validada, dejar el cuadro en `REVISION`.
- No modificar manualmente resultados agregados de Render.
- Regenerar `octopus.db` ejecutando `data_loader.py` con el Python del workspace si el Python del sistema no tiene dependencias.
- La carga construye una base temporal, recalcula clientes/resumenes, reconcilia los indicadores y reemplaza la base completa. Genera `data_sync_manifest.json` con hashes de fuentes/base y resultados de control.
- Ejecutar `python scripts/verify_sync.py`. Debe reconciliar cada mes disponible: Facturacion total, Facturacion con rentabilidad, Ganancia, porcentaje ponderado, ambos rankings Top 5/10/20, tablas mensuales y clientes publicados. No publicar si falla.
- Facturacion total y ranking de facturacion dependen de `billing_operations.net_amount`; los nuevos cuadros solo modifican rentabilidad/ganancia/fichas salvo que tambien haya novedades en Facturacion Historica.
- En el mes actual, tarjetas y rankings conservan el corte por Fecha Carga (facturacion) y fecha de operacion (rentabilidad), hasta el dia de consulta en Argentina. Las fichas individuales conservan su historial completo, que puede contener fechas futuras. Informar esa diferencia cuando explique un aparente desfase; no adelantar movimientos futuros para igualar totales.
- `data_access.py` invalida consultas por version de SQLite y su WAL; la app comprueba cambios de base/dia cada 30 segundos en sesiones abiertas. Todas las vistas deben usar esta lectura compartida.

## 6. Publicacion

- Ejecutar verificaciones basicas de Python.
- Ejecutar `python -m unittest discover -s tests -v` si se modifica la carga, cache, indicadores o deduplicacion.
- Commit y push a GitHub solo con archivos necesarios para la actualizacion.
- Incluir fuentes actualizadas, base y `data_sync_manifest.json` en el mismo commit; excluir `outputs/` y credenciales. Docker ejecuta `scripts/verify_sync.py` y rechaza una base que no corresponda a las fuentes enviadas.
- Esperar el despliegue del commit correcto. Abrir Render, comparar tarjetas y ambos rankings con `data_sync_manifest.json` para julio/agosto/septiembre y cualquier otro mes afectado. Probar busqueda y una ficha afectada; verificar total de clientes.
- Solo informar sincronizacion SI cuando los valores publicados coincidan con el control. Una respuesta HTTP correcta, un push exitoso o los nuevos cuadros en una ficha no prueban por si solos la sincronizacion de todos los indicadores.

## 7. Resumen Final

Responder corto, con los numeros de:

- nuevos encontrados;
- procesados;
- duplicados;
- en revision;
- clientes existentes actualizados;
- clientes nuevos creados;
- total publicado en Render;
- sincronizacion Drive -> base -> Render.

