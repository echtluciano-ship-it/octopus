# JARVIS / OCTOPUS Lab v0

Prototipo aislado del circuito:

```text
OCTOPUS TEST/SHADOW -> Coordinator -> Specialist -> Auditor -> Audit Log
```

## Limites actuales

- TEST usa datos sinteticos. SHADOW usa una copia local verificada de OCTOPUS.
- Solo permite consultas de lectura predefinidas.
- No usa Drive, WhatsApp, correo, GitHub ni Render.
- No ejecuta shell ni codigo proporcionado por documentos.
- No usa un modelo externo. Primero valida contratos, permisos y auditoria.

## Probar

Desde la raiz del repositorio:

```powershell
python -m jarvis.cli init-test
python -m jarvis.cli ask "Resumen de septiembre 2026"
python -m jarvis.cli ask "Ficha de Beta"
python -m jarvis.cli ask "Mostrar casos en revision"
```

## Shadow mode

Shadow nunca abre la base productiva como destino de escritura. Primero crea un
snapshot SQLite consistente, verifica el hash de la fuente antes y despues y
trabaja exclusivamente sobre esa copia ignorada por Git.

```powershell
python -m jarvis.cli init-shadow --source C:\ruta\a\octopus.db
python -m jarvis.cli reconcile-shadow --as-of 2026-10-06
python -m jarvis.cli observe-shadow --as-of 2026-10-06
python -m jarvis.cli ask --environment shadow "Resumen de septiembre 2026"
```

La reconciliacion compara los resultados de JARVIS con las consultas vigentes de
OCTOPUS. Una diferencia termina en error y no habilita ninguna accion externa.
La observacion integral vuelve a verificar el snapshot, audita todos los meses y
clientes con operaciones validas, registra los casos REVIEW y confirma que no se
ejecuto ninguna accion externa.

Cada respuesta muestra un ID que permite rastrear la ejecucion en
`jarvis/logs/jarvis_audit.db`.

## Componentes

- `core/coordinator.py`: coordina el flujo y nunca consulta la base directamente.
- `agents/specialist.py`: clasifica solo los tres casos aprobados.
- `tools/octopus_reader.py`: consultas parametrizadas y conexion SQLite read-only.
- `agents/auditor.py`: recalcula resultados desde filas independientes.
- `core/policy.py`: politica deny-by-default por agente.
- `core/audit_log.py`: registro append-only con redaccion basica de secretos.
- `scripts/build_test_db.py`: genera informacion sintetica reproducible.
- `scripts/create_shadow_snapshot.py`: copia coherente con hash e integridad.
- `scripts/shadow_reconcile.py`: compara SHADOW contra las metricas actuales.
- `scripts/shadow_observe.py`: ejecuta la bateria integral de observacion.
- `config/permissions.shadow.json`: permisos de lectura y denegaciones externas.

La aplicacion OCTOPUS/Render existente permanece fuera de este laboratorio.
