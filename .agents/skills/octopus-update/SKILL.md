---
name: octopus-update
description: Actualizar OCTOPUS desde Google Drive cuando el usuario diga "Actualiza OCTOPUS" o pida sincronizar cuadros/base/Render. La actualizacion cotidiana es incremental; ejecutar una auditoria historica completa solo ante "Audita OCTOPUS completo" o una imposibilidad tecnica explicada al usuario.
---

# OCTOPUS Update

Mantener la aplicacion existente `app_octopus` sincronizada desde la carpeta oficial de Drive hasta Render, sin cambiar reglas de negocio ni interfaz.

## Elegir el modo

- **`Actualiza OCTOPUS`**: usar siempre el flujo incremental de [Actualizacion Incremental](references/flujo-incremental.md). No revisar ni descargar documentos historicos sin cambios.
- **`Audita OCTOPUS completo`**: usar [Auditoria Completa](references/flujo-auditoria-completa.md). Es el unico disparador normal de la revision historica pesada.
- Si el flujo incremental detecta una condicion que impide garantizar integridad, detener antes de iniciar una auditoria completa y explicar el motivo. Recargar una fuente oficial completa que efectivamente cambio no equivale a auditar visualmente todo Drive.

Leer siempre [Reglas Operativas](references/reglas-operativas.md). Consultar [Casos Validados](references/casos-validados.md) solo para archivos/clientes alcanzados por la actualizacion.

## Invariantes

- Drive es la fuente oficial viva; `data/incremental_update_state.json` conserva el ultimo watermark e inventario conocido.
- `source_documents.csv` y `source_identity.py` conservan identidad documental, trazabilidad y decisiones humanas.
- Mismo cliente no implica misma operacion. Duplicar automaticamente solo por Drive ID, SHA-256 o pixeles identicos.
- Descargar, abrir y extraer solo archivos nuevos, modificados o dudosos.
- Si una fuente no cambio, no reprocesarla. Si Facturacion Historica cambio, cargar su nueva version; si no cambio, no descargarla.
- Aplicar operaciones Drive-backed con `scripts/incremental_refresh.py`. Recalcular solo clientes y meses afectados. El control global rapido de integridad se mantiene.
- Un caso nuevo dudoso va a `REVISION`; continuar con los demas.
- Commit/push y Render solo cuando haya cambios persistidos. Verificar en Render los meses, rankings y fichas afectados.

## Cierre

Responder en formato breve:

```text
Archivos detectados en Drive: X
Archivos ya conocidos/sin cambios: X
Archivos nuevos: X
Archivos modificados: X
Duplicados confirmados: X
Operaciones incorporadas: X
Casos en REVIEW: X
Meses/clientes afectados: ...
Facturacion Historica cambio: SI/NO
GitHub actualizado: OK/SIN CAMBIOS/ERROR
Render actualizado y verificado: OK/SIN CAMBIOS/ERROR
Tiempo total: X
```

