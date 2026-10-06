# Threat Model inicial

## Activos

- Informacion financiera y comercial.
- Documentos de Drive y mensajes.
- Credenciales de proveedores.
- Base OCTOPUS y despliegue Render.
- Identidad y reputacion de la empresa.

## Amenazas prioritarias

- Prompt injection dentro de documentos, chats o emails.
- Escrituras accidentales o duplicadas.
- Exposicion de secretos en prompts o logs.
- Skill o plugin de terceros malicioso.
- Confusion entre TEST y produccion.
- Agentes con permisos acumulados.
- Resultados plausibles pero matematicamente incorrectos.

## Controles de V0

- Base cuyo nombre debe contener `test` y conexion `mode=ro`.
- Politica deny-by-default.
- Sin red, shell, filesystem write externo ni conectores.
- Herramientas parametrizadas; no SQL generado por el agente.
- Auditor independiente antes de responder.
- Estados dudosos terminan en REVIEW.
- Registro append-only y redaccion de secretos.
- Datos externos nunca se interpretan como instrucciones.

## Controles requeridos antes de produccion

- Aislamiento por usuario del sistema y sandbox.
- Gestor de secretos y credenciales separadas.
- PostgreSQL con roles read-only/write especializados.
- Idempotencia, cola de aprobaciones y rollback.
- Backups, health checks y alertas.
- Evaluaciones de modelos y pruebas de inyeccion.
