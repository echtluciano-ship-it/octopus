# Reglas de Negocio V2 - OCTOPUS

Ultima actualizacion: 2026-09-05

## Alerta de caida de actividad mayor al 50%

Definicion validada por Andy:

- La alerta debe comparar el monto facturado total por cliente de un mes contra el mes anterior.
- No se compara cantidad de pedidos.
- No se compara cantidad de facturas.
- La finalidad es comercial: detectar clientes que redujeron fuertemente su actividad para contactarlos.

Regla conceptual:

- Si un cliente hace su pedido/facturacion del mes y el monto total facturado resulta igual o inferior al 50% del monto facturado el mes anterior, debe quedar marcado como alerta comercial.
- No hace falta esperar necesariamente al cierre del mes para generar la alerta.

Ejemplo validado:

- Mes anterior: $100M.
- Mes actual: el cliente hace su pedido/facturacion por $40M.
- Resultado: generar alerta comercial.

Pendiente de definicion antes de implementar:

- Confirmar que campo de Facturacion Historica representa mejor "total facturado" para esta alerta.
- No asumir automaticamente que corresponde a la columna `TOTAL`.
- Candidato tecnico recomendado: `Neto`, porque representa mejor la actividad comercial sin distorsiones de IVA, percepciones o retenciones.
- La columna `TOTAL` debe conservarse, pero puede variar por impuestos/percepciones y no necesariamente refleja mejor la actividad pura del cliente.

Mes abierto:

- Andy confirmo que no quiere esperar necesariamente al cierre del mes.
- Queda pendiente definir como detectar correctamente que el cliente ya hizo su pedido/facturacion del mes, para no generar alertas prematuras.
- Tambien debe existir una segunda alerta aproximadamente los dias 26/27 de cada mes para casos relevantes, con el objetivo de contactar al cliente y preguntarle si necesita algo mas.
- No debe compararse automaticamente un mes abierto incompleto contra todo el mes anterior si todavia no hay evidencia de pedido/facturacion del cliente.

## Cliente que dejo de operar

Definicion validada por negocio:

- Para esta alerta, se considera que un cliente "opero" cuando tuvo facturacion.
- Si un cliente que anteriormente operaba completa 2 meses consecutivos sin ninguna facturacion, OCTOPUS debe marcarlo para alerta.
- La medicion debe basarse en Facturacion Historica normalizada y clientes canonicos/alias validados.

Ejemplo validado:

- Ultima facturacion: junio.
- Sin facturacion en julio.
- Sin facturacion en agosto.
- Resultado: en septiembre debe aparecer como cliente que lleva 2 meses sin operar.

Estado:

- Definicion comercial incorporada.
- No implementado en Render.
- No implementado como funcionalidad visible.

## Fecha habitual de pago

Definicion validada por Andy:

- Para la funcionalidad futura de patrones de pago/contacto, la fecha habitual de pago se medira con la `Fecha de orden` de Pagos Octopus.
- Esta fecha representa la fecha en que se genera la orden de pago.
- No debe confundirse con fecha de acreditacion, vencimiento, ECHEQ, fecha de valor/tesoreria ni Fecha Carga.

Estado:

- Definicion comercial incorporada.
- No implementado en Render.
- No implementado como funcionalidad visible.

## Fecha Carga y resumen hasta hoy

Definicion para V2:

- `Fecha Carga` de Facturacion Historica se considera un corte administrativo: indica informacion registrada hasta esa fecha.
- No se considera por si sola una fecha economica de operacion, factura o pago.
- Para el resumen "hasta hoy", la propuesta queda como: informacion registrada hasta hoy + periodo no futuro.
- Esto evita incluir movimientos futuros simplemente porque ya fueron cargados en la planilla.

Estado:

- Definicion comercial incorporada.
- No implementado en Render.
- No implementado como funcionalidad visible.
