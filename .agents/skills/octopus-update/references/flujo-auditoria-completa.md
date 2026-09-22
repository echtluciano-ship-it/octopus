# Auditoria Completa

Usar solo cuando el usuario diga `Audita OCTOPUS completo` o cuando una condicion grave impida demostrar integridad incremental y el motivo ya haya sido explicado.

1. Inventariar todas las carpetas y meses oficiales de Pendientes y Pagos.
2. Reconciliar cada Drive ID con `source_documents.csv` y el estado incremental.
3. Recalcular SHA-256/huella visual solo cuando falten o haya evidencia de modificacion; no declarar duplicados por campos de negocio.
4. Revisar periodos, clientes canonicos, aliases, exclusiones y casos REVIEW de toda la historia solicitada.
5. Comparar todas las fuentes oficiales, incluida Facturacion Historica y validaciones humanas.
6. Ejecutar `data_loader.py`, reconciliacion global y la suite completa de pruebas.
7. Regenerar `data/incremental_update_state.json` con el inventario confirmado y registrar el baseline.
8. Publicar y verificar todos los periodos relevantes en Render.

La auditoria puede reconstruir todo el snapshot porque su objetivo es demostrar integridad historica, no optimizar la carga cotidiana.
