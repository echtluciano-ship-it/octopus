# Cierre Mensual Completo

Usar ante `Cierre mensual OCTOPUS`, `Cerra OCTOPUS` o un pedido equivalente. Este flujo es distinto de la actualizacion incremental cotidiana y de la auditoria historica completa: revisa exhaustivamente un periodo mensual determinado y demuestra la cadena `documentos fuente -> operaciones -> base -> indicadores -> Render`.

## Periodo y estado

- Trabajar con un mes explicito `YYYY-MM`. Si no se indica, inferir el mes que termina solo cuando la fecha local de Buenos Aires sea su ultimo dia; en otro momento pedir el periodo.
- Estados del cierre: `EN_REVISION` o `CERRADO`.
- No declarar `CERRADO` mientras exista un documento sin clasificar, una diferencia sin explicar o un caso `REVISION` pendiente.
- Las correcciones humanas son definitivas y deben persistirse con su archivo/Drive ID para no volver a consultarlas.

## 1. Congelar fuentes e inventario

1. Registrar hora de inicio, periodo, commit/base de partida y metadatos/hash de las fuentes oficiales.
2. Inventariar todos los hijos directos de las carpetas del periodo en Pendientes y Pagos, sin depender del watermark incremental.
3. Revisar tambien las carpetas mensuales adyacentes para detectar archivos mal ubicados cuya fecha economica visible corresponda al periodo de cierre.
4. Reconciliar cada archivo con `data/incremental_update_state.json`, `source_documents.csv`, `manual_rentability_operations.csv` y `octopus.db`.
5. Conservar por documento Drive ID, nombre, carpeta, tamano, fecha de deteccion/modificacion, SHA-256, huella visual cuando corresponda, operacion asociada, estado, `duplicate_of` y evidencia.

Cada documento debe terminar en una clasificacion explicita: operacion valida, duplicado documental, excluido/no procesar, documento de validacion Pagos o `REVISION`. Debe cumplirse:

`documentos inventariados = clasificados validos + duplicados + excluidos/no procesar + validacion Pagos + REVIEW`

No borrar archivos de Drive durante el cierre.

## 2. Validar operaciones del periodo

- Aplicar sin cambios [Reglas Operativas](reglas-operativas.md) y, solo cuando corresponda, [Casos Validados](casos-validados.md).
- Confirmar cliente canonico y canal antes de crear un cliente nuevo.
- Verificar fecha economica visible y mes correcto; la carpeta o el nombre del archivo no determinan el periodo.
- Resolver operaciones multi-mes solo con evidencia inequivoca de Pagos y montos reales. Sin evidencia suficiente, `REVISION`.
- Mantener separados ECHEQ/transferencia, Facturacion Neta y Ganancia Octopus.
- Rentabilidad = Ganancia Octopus / Facturacion Neta. Nunca promediar porcentajes.
- Revalidar duplicados solo con identidad documental fuerte; mismo cliente, fecha o importe no prueban duplicacion.
- Confirmar que exclusiones y decisiones humanas persistidas siguen aplicadas y no alimentan calculos.

## 3. Facturacion Historica y base

1. Leer metadatos de la Facturacion Historica oficial y descargar su ultima version si cambio.
2. Normalizar periodos y aliases con las reglas existentes; no inventar clientes, fechas ni importes ambiguos.
3. Reconciliar el periodo de `billing_operations` con la fuente oficial y registrar filas no interpretables.
4. Reconstruir el snapshot de base de forma atomica cuando haya cambios estructurales o de fuente; de lo contrario aplicar cambios deterministas y verificar el resultado completo del periodo.
5. Validar estados de operaciones, conteos, sumas y trazabilidad de cada operacion valida hacia el documento de origen.

## 4. Reconciliacion obligatoria

Para el mes objetivo controlar y guardar:

- Facturacion total: suma valida de `billing_operations.net_amount` segun las reglas vigentes.
- Facturacion con rentabilidad: `SUM(rentability_operations.billed_amount)` sobre operaciones validas.
- Ganancia Octopus: `SUM(rentability_operations.octopus_profit)` sobre el mismo universo.
- Rentabilidad global ponderada: Ganancia / Facturacion con rentabilidad.
- Cantidad de registros de facturacion y operaciones de rentabilidad utilizadas.
- Rankings completos por facturacion y rentabilidad, sin clientes canonicos repetidos.
- Totales por cliente y canal, fichas afectadas y ultima operacion.
- Estados `DUPLICADO`, `EXCLUIDO`, `NO_PROCESAR` y `REVISION` del periodo.

Ejecutar la suite de pruebas, `scripts/verify_sync.py` y controles de identidad. Toda diferencia debe quedar corregida o explicada como `REVISION`; nunca ajustar manualmente un numero para forzar coincidencia.

## 5. Publicacion y verificacion

- Persistir los cambios, el inventario confirmado y el baseline solo despues de superar los controles locales.
- Commit/push cuando existan cambios. Si no existen, registrar `SIN CAMBIOS` y continuar con la verificacion.
- Esperar el despliegue del Render actual y comprobar en la aplicacion publicada: cuatro indicadores, cantidad de operaciones, rankings de facturacion/rentabilidad, total de clientes y fichas afectadas.
- Comparar Render contra el snapshot local. Si difieren, el cierre queda `EN_REVISION`.

## 6. Evidencia persistente e informe

Guardar por cada ejecucion un control versionado en `data/monthly_closures/YYYY-MM.json` con:

- periodo, estado, fecha/hora y commit;
- metadatos/hash de fuentes;
- conteos por clasificacion documental;
- operaciones validas y estados no validos;
- totales e indicadores reconciliados;
- diferencias encontradas, correcciones y decisiones humanas;
- resultados de pruebas;
- estado de GitHub y Render.

El informe al usuario debe ser breve e incluir como minimo:

```text
Cierre: YYYY-MM - CERRADO/EN_REVISION
Documentos revisados: X
Operaciones validas: X
Duplicados: X
Excluidos/no procesar: X
Casos REVIEW: X
Facturacion total: $X
Facturacion con rentabilidad: $X
Ganancia Octopus: $X
Rentabilidad global: X%
Diferencias encontradas/corregidas: ...
Controles: OK/ERROR
GitHub: OK/SIN CAMBIOS/ERROR
Render: OK/SIN CAMBIOS/ERROR
```

Si queda `REVISION`, listar cada archivo, link de Drive, datos legibles y una unica pregunta concreta sobre lo que falta confirmar.
