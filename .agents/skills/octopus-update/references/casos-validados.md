# Casos Validados y Decisiones Persistentes

Este archivo resume decisiones ya tomadas para no volver a preguntarlas. La fuente operativa sigue siendo el codigo, `manual_rentability_operations.csv` y `client_aliases.csv`.

## Alias Confirmados

- Respetar todas las filas `unificar` de `client_aliases.csv`.
- Ejemplos importantes ya validados: `ACMED S` -> `ACMED`, `LX ARGENTINA S.A.` -> `LX`, `Grupo Monaci` -> `Grupo Monaco`, `Vega y Camil` -> `Vega y Camji`, `Wolf Pack`/`Wolfpack`, `Ovniplast`, `Alimentos Viandas`, `Centro Medico Amenabar`.
- Un alias ya validado no debe reaparecer como cliente independiente.

## Ovniplast

- Ovniplast fue validado manualmente y puede publicarse.
- Sus cuadros validos de julio con rentabilidades cercanas a 10,43% y 9,84% son correctos.
- No cargar porcentajes manuales: calcular desde facturado total y ganancia total.

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

