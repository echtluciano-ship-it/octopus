# Casos Validados y Decisiones Persistentes

Este archivo resume decisiones ya tomadas para no volver a preguntarlas. La fuente operativa sigue siendo el codigo, `manual_rentability_operations.csv` y `client_aliases.csv`.

## Alias Confirmados

- Respetar todas las filas `unificar` de `client_aliases.csv`.
- Ejemplos importantes ya validados: `ACMED S` -> `ACMED`, `LX ARGENTINA S.A.` -> `LX`, `Grupo Monaci` -> `Grupo Monaco`, `Vega y Camil` -> `Vega y Camji`, `Wolf Pack`/`Wolfpack`, `Ovniplast`, `Alimentos Viandas`, `Centro Medico Amenabar`.
- Un alias ya validado no debe reaparecer como cliente independiente.

## Ovniplast

- Ovniplast fue validado manualmente y puede publicarse.
- No cargar porcentajes manuales: calcular desde Facturacion Neta total y Ganancia Octopus total.
- En los cuadros nuevos donde aparece ECHEQ arriba y `FC neta` debajo, el ECHEQ no es el denominador. Usar `FC neta` para rentabilidad y conservar el ECHEQ solo como dato trazable.
- Los cuadros viejos `PHOTO-2026-07-08-19-11-01.jpg` / `00003864-PHOTO-2026-07-08-19-11-01.jpg` y `PHOTO-2026-07-08-19-16-38.jpg` / `00003865-PHOTO-2026-07-08-19-16-38.jpg` fueron revisados por Luciano y su padre el 2026-09-02 y quedaron excluidos definitivamente por error de retenciones en origen. No contabilizarlos ni reincorporarlos aunque reaparezcan en Drive.
- Los cuadros nuevos de Ovniplast cargados en septiembre de 2026 con rentabilidades aproximadas de 5-6% estan validados y deben mantenerse.

## LX - Espora

- LX/LX Argentina estan unificados como cliente `LX`, pero algunos cuadros `LX - Espora` fueron marcados como problematicos.
- Si aparece un nuevo cuadro `LX - Espora`, no publicarlo automaticamente si no hay validacion clara del caso; registrarlo como `REVISION` con facturado, ganancia y fecha visibles.

## Fechas Multiples

- Si un cuadro muestra multiples fechas de ECHEQ, clasificar como revision salvo que todas las fechas caigan en el mismo mes o exista validacion previa clara.
- Si la fecha visible pertenece a otro mes distinto de la carpeta, mover el archivo al mes correcto cuando la fecha sea inequivoca.

## Transferencia 1,20%

- Cuando Mariano indico que ciertas facturas ya pagaron costos anteriormente, se valido que esos cuadros pueden procesarse aunque no tengan `FACTURADO` visible si la Ganancia Octopus coincide claramente con el 1,20% del importe transferido.
- Guardar la operacion como `OK_TRANSFERENCIA_1_2` y no confundirla con una operacion normal.

## Revision

- Una fila en revision no alimenta Render ni metricas publicadas.
- Debe conservarse en base/CSV para resolverla despues sin perder trazabilidad.
- Si el usuario completa una respuesta en un Excel de control o por chat, tomarla como definitiva y persistirla.

## Fechas y Operaciones Validadas el 2026-09-18

- Los cuadros `Mas Metros - Espora` con ECHEQ 16/07/26 y 24/07/26 son operaciones distintas. Contabilizar ambos por separado aunque compartan Facturacion Neta.
- Star Medical con ECHEQ 29/07 corresponde a julio de 2026.
- El Perro de la Luna con ECHEQ 31/07 corresponde a julio de 2026.
- Managing con ECHEQ 31/07/26 corresponde a julio de 2026.

## Hasar - Canal Corregido

- Para `PHOTO-2026-09-23-11-52-07.jpg` (Drive ID `18etnvM0kn-HSGkKRdMtymT5SY17E__Qe`), Luciano confirmo el 2026-09-23 que el canal correcto es `HYF`, aunque el encabezado del cuadro dice `HASAR-ESPORA`.
- Luciano confirmo despues que la fecha `25/10` es incorrecta. Este archivo NO es multi-mes: toda la operacion corresponde al `25/09/2026`.
- Imputar en septiembre el ECHEQ completo 29.496.064,77, la Facturacion Neta 24.805.152 y la Ganancia Octopus 1.713.756. No crear ni reponer un tramo de octubre, aunque la orden `O_P_0201500033107.pdf` conserve esa fecha en el documento original.

## Alimentos Viandas - Operacion Agosto/Septiembre

- `PHOTO-2026-08-28-15-32-49.jpg` (Drive ID `1E-KylRmviBfoivwCSc_Ia1Cm9_nT3NNM`) corresponde a `Alimentos Viandas - HYF`.
- La orden `ORDEN_DE_PAGO_12373.pdf` (Drive ID `1BWBwdE9ogr5dmsEnbYu71h69zt1B_nQX`) reconcilia el ECHEQ total 67.394.427,09 y la base de retenciones 57.845.448,14 con la FC neta visible 57.845.447.
- Los valores son 55.220.592,28 en agosto y 12.173.834,81 en septiembre. Distribucion definitiva: agosto FC neta 47.396.498,23 / ganancia 2.795.489,33; septiembre FC neta 10.448.948,77 / ganancia 616.288,67. Estado `OK_MULTI_MONTH_SPLIT`.

## BASIC A - Octubre/Noviembre

- `PHOTO-2026-09-22-11-23-21.jpg` (HYF) y `PHOTO-2026-09-22-14-58-07.jpg` (Espora) muestran fechas de octubre y noviembre.
- No existe aun una orden de pago correspondiente en `Pagos Octopus` que permita demostrar la distribucion real. Mantener ambos en `REVISION`; no asumir porcentajes ni publicar.

