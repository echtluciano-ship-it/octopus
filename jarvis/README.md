# JARVIS / OCTOPUS Lab v0

Primer prototipo aislado del circuito:

```text
OCTOPUS TEST -> Coordinator -> Specialist -> Auditor -> Audit Log
```

## Limites actuales

- Solo usa datos sinteticos.
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

La aplicacion OCTOPUS/Render existente permanece fuera de este laboratorio.
