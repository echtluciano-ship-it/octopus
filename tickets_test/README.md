# OCTOPUS Tickets TEST

Entorno aislado para el primer flujo real de Tickets. No comparte servicios,
credenciales ni bases con OCTOPUS/Render.

## Servicios

- Evolution API 2.3.7/Baileys: WhatsApp TEST y webhooks.
- PostgreSQL: eventos, mensajes, documentos, estados y auditoria.
- MinIO: originales inmutables y recuperables.
- Tickets API: confirma el webhook solo despues de persistir el ingreso.
- Tickets worker: OCR, reglas deterministicas, clasificacion y Excel.
- Redis: estado/cache de Evolution API.

Las reacciones y los correos se guardan como acciones `BLOCKED_SHADOW`: este
entorno no escribe en WhatsApp ni envia correo.

## Arranque

```powershell
.\scripts\Initialize-Test.ps1
.\scripts\Start-Test.ps1
.\scripts\Test-EndToEnd.ps1
.\scripts\New-EvolutionInstance.ps1
```

El ultimo comando crea/recupera la instancia y abre
`runtime/whatsapp-test-qr.png`. El QR debe vincularse solamente con un numero
dedicado de prueba.

## Controles

```powershell
.\scripts\Status-Test.ps1
```

La reconciliacion exige:

`documentos almacenados = procesados + duplicados + review + errores + en curso`

Si Evolution anuncia un archivo pero los bytes no llegan, el mensaje permanece
registrado, la diferencia queda visible y Evolution recibe un error temporal
para reintentar la entrega.

Los Excel editables quedan en `runtime/exports/`, siempre ordenados por secuencia
de llegada. Las reglas no confirmadas quedan como `PENDING_RULE` o `REVIEW`.
