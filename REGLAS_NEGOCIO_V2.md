# Reglas de Negocio V2 - OCTOPUS

Ultima actualizacion: 2026-09-05

## Alerta de caida de actividad mayor al 50%

Definicion validada por Andy:

- La alerta debe comparar el monto facturado total por cliente de un mes contra el mes anterior.
- No se compara cantidad de pedidos.
- No se compara cantidad de facturas.
- La finalidad es comercial: detectar clientes que redujeron fuertemente su actividad para contactarlos.

Regla conceptual:

- Si un cliente factura menos del 50% de lo facturado el mes anterior, debe quedar marcado como alerta comercial.

Pendiente de definicion antes de implementar:

- Confirmar que campo de Facturacion Historica representa mejor "total facturado" para esta alerta.
- No asumir automaticamente que corresponde a la columna `TOTAL`.
- Candidato tecnico recomendado: `Neto`, porque representa mejor la actividad comercial sin distorsiones de IVA, percepciones o retenciones.
- La columna `TOTAL` debe conservarse, pero puede variar por impuestos/percepciones y no necesariamente refleja mejor la actividad pura del cliente.

Mes abierto:

- Todavia falta definir cuando evaluar la alerta durante un mes en curso.
- No debe compararse automaticamente, por ejemplo, los primeros dias de septiembre contra todo agosto, porque generaria falsos positivos.
- Opciones a definir con Mariano/Andy:
  - evaluar solo meses cerrados;
  - evaluar mes abierto solo despues de cierto dia;
  - comparar contra el mismo corte del mes anterior.

Estado:

- Definicion comercial incorporada.
- No implementado en Render.
- No implementado como alerta visible.
