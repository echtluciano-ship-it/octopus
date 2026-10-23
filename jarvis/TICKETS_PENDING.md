# Tickets: pendientes vigentes

Estado actualizado el 23/10/2026. El estado completo y las reglas consolidadas
estan en `../tickets_test/HANDOFF_CURRENT.md`.

## Resuelto en TEST

- infraestructura Docker con Evolution API, Postgres, Redis, API y worker;
- WhatsApp TEST vinculado y conectado;
- ingreso durable, originales, estados, reintentos y reconciliacion;
- OCR/extraccion, reglas, duplicados y revision humana;
- Excel `.xlsx` editable por grupo con delivery gate;
- Gmail OAuth con destinatario limitado a Erika y envios TEST confirmados;
- llamadas de WhatsApp permitidas (`rejectCall=false`).

## Pendiente antes de grupos productivos

- completar y aprobar al menos tres tandas consecutivas de shadow mode con
  integridad total, orden exacto y comparacion fila por fila con Erika;
- aprobar una politica de retencion y acceso a originales con datos personales;
- validar operativamente los formatos secundarios y de depositos en nuevas
  tandas reales;
- autorizar en forma explicita la conexion de los dos grupos productivos;
- autorizar por separado las reacciones `❌`, `⛔️` y `❎`;
- definir el umbral de autonomia y el procedimiento de contingencia.

## Limites actuales

- Reacciones de WhatsApp: `BLOCKED_SHADOW`.
- Grupos productivos: no conectados.
- Correos: solo TEST y solo `oficinaoctopus13@gmail.com`, tras superar el
  delivery gate.
- Tickets no se despliega en Render ni modifica OCTOPUS productivo.
