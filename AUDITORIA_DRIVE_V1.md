# Auditoria Drive V1 - Octopus

Fecha: 2026-08-06

## Fuente oficial

Desde esta version, la fuente oficial del proyecto es Google Drive:

- Carpeta raiz: Octopus Base De Clientes
- ID: 1VzjdYgBrXA1zpYDWULw1RNGN6uN3SQbL

Los IDs operativos quedaron registrados en `drive_sources.json`.

## Hallazgos iniciales

1. La estructura esta creada y accesible desde el conector de Google Drive.
2. Los nombres reales aun no coinciden exactamente con la convencion pedida:
   - Se ve `Cuadros Octopus`, no `01 - Cuadros`.
   - Se ve `Facturación Historica`, no `02 - Facturación Histórica`.
   - Los meses aparecen como `julio 2026` / `agosto 2026`, no `2026-07` / `2026-08`.
3. Esto no bloquea el trabajo porque la app puede usar IDs fijos, pero para automatizacion conviene estandarizar nombres.
4. La carpeta `Facturación Historica` contiene un shortcut, pero el archivo real oficial ya fue identificado:
   - `FACTURACION OCTOPUS.xlsx`
   - ID: `13LybCGEaAD6e6cn9VTdoXD3N_-kbBjeV`
   - Este ID queda como fuente oficial de facturacion historica para automatizacion.
5. `Clientes y alias` esta vacia. Todavia no existe una fuente oficial para alias aprobados.
6. `Procesamiento Automatico` ya tiene subcarpetas utiles:
   - Procesados
   - Requiere Revision
   - Duplicados

## Cuadros e inconsistencias detectadas

1. En `Cuadros Octopus > Pendientes Octopus > julio 2026` hay imagenes de julio disponibles para reconstruir rentabilidad.
2. En `Cuadros Octopus > Pendientes Octopus > agosto 2026` aparecen imagenes con fecha de julio:
   - PHOTO-2026-07-30-14-53-03.jpg
   - PHOTO-2026-07-28-15-54-40.jpg
   - PHOTO-2026-07-26-20-13-53.jpg
   Estas deben validarse: pueden corresponder a operaciones de julio cargadas tarde o estar mal ubicadas.
3. Hay nombres repetidos con distinto tamaño:
   - PHOTO-2026-07-21-13-23-07.jpg aparece dos veces.
   - PHOTO-2026-07-08-16-37-11.jpg aparece dos veces.
   - PHOTO-2026-08-03-17-20-22.jpg aparece dos veces en agosto.
   No deben eliminarse automaticamente: pueden ser dos cuadros distintos enviados en el mismo minuto.
4. La rentabilidad mensual de julio ya existe y fue subida a `Rentabilidad Mensual > julio 2026`.
5. La carpeta `Pagos Octopus > julio 2026` esta vacia al momento de esta auditoria.
6. La carpeta `Pagos Octopus > agosto 2026` esta vacia al momento de esta auditoria.

## Reglas de calidad que quedan fijadas

1. No calcular rentabilidad si falta `Facturado` o `Ganancia Octopus`.
2. No promediar porcentajes individuales.
3. Calcular siempre:
   - `rentabilidad = ganancia_octopus_acumulada / facturado_acumulado`
4. Mantener separado `cliente + canal`.
5. No unificar alias automaticamente.
6. Todo cuadro debe conservar:
   - Drive file ID
   - nombre de archivo
   - carpeta origen
   - fecha inferida
   - cliente leido
   - canal leido
   - facturado
   - ganancia Octopus
   - estado de validacion
7. Ante duda, marcar `requiere_revision`.
8. El mes operativo se imputa por fecha de ECHEQ visible en el cuadro, no por fecha de carga en Drive ni por carpeta.
9. No se renombraran carpetas de Drive. La automatizacion debe trabajar con IDs fijos registrados en `drive_sources.json`.
10. Si un cuadro tiene multiples fechas de ECHEQ, se marca `requiere_revision_manual`.
11. Si la fecha de ECHEQ no se ve, se marca `requiere_revision_manual`.

## Pendiente de validacion humana

1. Confirmar fuente oficial para alias de clientes.
2. Validar imagenes con fecha julio ubicadas en carpeta agosto: por regla nueva, si el ECHEQ es de julio deben imputarse a julio aunque esten en agosto.
3. Generar y validar lista completa de clientes/alias.

## Propuesta de modelo PostgreSQL

Tablas principales:

- `clients`
- `client_aliases`
- `channels`
- `source_files`
- `operation_cards`
- `operations`
- `monthly_client_channel_metrics`
- `validation_issues`
- `processing_runs`

Relaciones:

- Un cliente puede tener muchos alias.
- Un cliente puede operar en muchos canales.
- Un archivo de Drive puede producir cero, una o varias operaciones.
- Una operacion conserva referencia al cuadro original.
- Las metricas mensuales se calculan desde operaciones validadas, no se editan manualmente.

## Roadmap recomendado

## Reglas V2 validadas

### Alerta de caida de actividad mayor al 50%

Andy confirmo que la alerta debe comparar el monto facturado total por cliente de un mes contra el mes anterior. No debe basarse en cantidad de pedidos ni cantidad de facturas.

La finalidad es comercial: detectar clientes que redujeron fuertemente su actividad para poder contactarlos.

Antes de implementarla en Render queda pendiente una definicion: que campo exacto de Facturacion Historica representa mejor ese "total facturado". No se debe asumir automaticamente que es la columna `TOTAL`. La recomendacion tecnica inicial es usar `Neto`, porque representa mejor actividad comercial sin impuestos/percepciones, pero requiere validacion de negocio.

Andy confirmo que no quiere esperar necesariamente al cierre del mes. Cuando el cliente haga su pedido/facturacion del mes, si el monto total facturado resulta igual o inferior al 50% del mes anterior, OCTOPUS debe generar alerta.

Tambien debe existir una segunda alerta aproximadamente los dias 26/27 de cada mes para casos relevantes, con el objetivo de contactar al cliente y preguntarle si necesita algo mas.

Queda pendiente definir como detectar correctamente que el cliente ya hizo su pedido/facturacion del mes, para no generar alertas prematuras.

### Fecha habitual de pago

Andy confirmo que para patrones de pago/contacto se debe utilizar la Fecha de orden de Pagos Octopus. Representa la fecha en que se genera la orden de pago.

No debe confundirse con fecha de acreditacion, vencimiento, ECHEQ, fecha de valor/tesoreria ni Fecha Carga.

### Fecha Carga y resumen hasta hoy

Fecha Carga queda como corte administrativo de informacion registrada. Para el resumen "hasta hoy", la propuesta V2 es incluir informacion registrada hasta hoy y excluir periodos futuros, para evitar sumar movimientos futuros simplemente porque ya fueron cargados.

### Etapa 1 - Auditoria Drive y calidad de datos

Objetivo: saber exactamente que hay y que no es confiable.

Entregables:
- Inventario Drive.
- Lista de duplicados.
- Lista de cuadros no incorporados.
- Lista de cuadros en revision.
- Lista inicial de posibles alias.

Estado: iniciado.

### Etapa 2 - Base PostgreSQL

Objetivo: reemplazar SQLite local por base productiva compartida.

Entregables:
- Esquema PostgreSQL.
- Migracion inicial.
- Carga desde Drive.
- Validaciones.

### Etapa 3 - Normalizacion y alias

Objetivo: que los clientes se agrupen solo cuando haya validacion humana.

Entregables:
- Tabla de alias.
- Interfaz/listado para aprobar alias.
- Reporte de posibles duplicados.

### Etapa 4 - Automatizacion Drive

Objetivo: detectar cuadros nuevos y procesarlos.

Flujo recomendado n8n:
- Trigger programado cada 15 minutos.
- Buscar archivos nuevos en carpetas `Cuadros`.
- Registrar archivo en `source_files`.
- Ejecutar extraccion visual/OCR.
- Si completa: crear operacion.
- Si dudosa: crear issue y mover/copiado logico a `Requiere Revision`.
- Recalcular metricas mensuales.
- Notificar resumen.

### Etapa 5 - Actualizacion app Render

Objetivo: que la app lea la base productiva y no archivos viejos.

Entregables:
- Conexion segura a PostgreSQL.
- Variables privadas en Render.
- Cache controlado.
- Boton de refresco.

### Etapa 6 - Reportes y dashboard

Objetivo: dar respuestas simples a Mariano/Martin.

Entregables:
- Rentabilidad mensual.
- Clientes activos/inactivos.
- Clientes a llamar.
- Alertas de baja rentabilidad.
- Seguimiento por canal.
