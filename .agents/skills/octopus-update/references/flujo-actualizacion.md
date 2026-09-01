# Flujo de Actualizacion

## 1. Preparacion

- Confirmar que el working tree no tenga cambios no relacionados. No revertir cambios del usuario.
- Leer `drive_sources.json`, `client_aliases.csv`, `manual_rentability_operations.csv`, `data_loader.py` y `app.py` cuando haga falta confirmar una regla vigente.
- Usar la skill de Google Drive para listar la carpeta oficial y sus subcarpetas de Pendientes/Pagos por mes.

## 2. Deteccion de Archivos Nuevos

- Listar Pendientes y Pagos de todos los meses disponibles, no solo el mes actual.
- Comparar cada archivo contra los IDs y nombres ya registrados en `manual_rentability_operations.csv` y en la base.
- Descargar o abrir visualmente solo los candidatos nuevos o dudosos.

## 3. Clasificacion

Cada archivo de Pendientes debe terminar clasificado como:

- `OK` si tiene datos completos y confiables.
- `OK_TRANSFERENCIA_1_2` si aplica la regla de costos ya pagados y comision 1,20%.
- `OK_FC_NETA` u `OK_FC_HISTORICA` si aplica una regla validada de FC neta o cruce con Facturacion Historica.
- `DUPLICADO` si ya fue incorporado.
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
- No modificar manualmente resultados agregados de Render.
- Regenerar `octopus.db` ejecutando `data_loader.py` con el Python del workspace si el Python del sistema no tiene dependencias.
- Verificar conteos de estados, operaciones nuevas y clientes publicados.

## 6. Publicacion

- Ejecutar verificaciones basicas de Python.
- Commit y push a GitHub solo con archivos necesarios para la actualizacion.
- Confirmar que Render responde en `https://octopus-clientes.onrender.com/#base-de-clientes`.
- Si Render responde pero puede estar desplegando, aclararlo en el resumen solo si no se puede confirmar la sincronizacion completa.

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

