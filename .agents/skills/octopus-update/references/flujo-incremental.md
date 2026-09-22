# Actualizacion Incremental Cotidiana

## 1. Preparar el delta

1. Confirmar el working tree y leer `data/incremental_update_state.json`.
2. Guardar `scan_started_at` antes de consultar Drive. Usar como watermark el `last_successful_scan` persistido, con un solapamiento corto si hace falta tolerar relojes; los Drive ID conocidos eliminan repeticiones.
3. Listar solo las carpetas padre de Pendientes/Pagos para descubrir meses nuevos.
4. En las carpetas mensuales conocidas, buscar archivos creados o modificados desde el watermark. No listar/descargar todo el contenido historico.
5. Leer metadatos de Facturacion Historica y compararlos con `data/billing_source.json` y el estado incremental.

Crear un snapshot temporal con este esquema y ejecutar:

```powershell
python scripts/drive_delta.py plan --snapshot outputs/drive_candidates.json --output outputs/drive_plan.json
```

Campos minimos por archivo: `drive_id`, `name`, `size_bytes`, `modified_time`, `folder_id`, `folder_period`, `source_type`, `url`. El snapshot incluye `scan_started_at`, `folders` y `official_sources`.

## 2. Procesar solo candidatos

- `unchanged`: no abrir, descargar ni interpretar.
- `new`: descargar/abrir, calcular SHA-256 y huella visual, aplicar reglas y persistir.
- `modified`: descargar la version nueva, comparar identidad/contenido con la registrada y conservar evidencia de la version anterior en la nota/control. Si cambia la operacion y no puede resolverse inequivocamente, `REVISION`.
- Para Pagos, conservar inventario/contexto; no incorporarlo a rentabilidad salvo regla puntual.
- Un mes nuevo se incorpora a `drive_sources.json` despues de verificar su carpeta.

## 3. Fuentes y base

- Si Facturacion Historica no cambio, no descargarla ni recargar `billing_operations`.
- Si cambio, descargar el XLSX oficial, actualizar `billing_source.json` y ejecutar la carga atomica completa de esa fuente. Esto no habilita una auditoria visual historica de Drive.
- Para cuadros nuevos/modificados con Drive ID, actualizar los CSV persistentes y ejecutar:

```powershell
python scripts/incremental_refresh.py
```

La ruta incremental reemplaza solo operaciones Drive-backed cambiadas y recalcula sus clientes/meses. Si devuelve `full_refresh_required`, leer el motivo: usar `data_loader.py` solo para cambios estructurales (Facturacion, aliases, filas historicas sin Drive ID o eliminaciones) y registrar nuevamente la base incremental:

```powershell
python data_loader.py
python scripts/incremental_refresh.py --record-baseline
```

No iniciar una auditoria completa salvo que la condicion impida garantizar integridad y se haya explicado al usuario.

## 4. Control y publicacion

- Verificar los meses/clientes afectados y ejecutar las pruebas incrementales, de identidad y sincronizacion pertinentes.
- Mantener la reconciliacion global automatica: es un control de segundos, no una reapertura de fuentes historicas.
- Solo despues de una carga local correcta, persistir el watermark:

```powershell
python scripts/drive_delta.py commit --snapshot outputs/drive_candidates.json
```

- Commit/push solo si hay cambios. Excluir `outputs/` y credenciales.
- Esperar Render y comparar tarjetas, rankings, total publicado y una ficha afectada. Si no hubo cambios, no generar commit/deploy vacio.
