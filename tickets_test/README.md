# OCTOPUS Tickets TEST

Entorno aislado para el primer flujo real de Tickets. No comparte servicios,
credenciales ni bases con OCTOPUS/Render.

## Servicios

- Evolution API 2.3.7/Baileys: WhatsApp TEST y webhooks.
- PostgreSQL: eventos, mensajes, documentos, estados y auditoria.
- Volumen persistente privado: originales con escritura atomica y recuperables.
- Tickets API: confirma el webhook solo despues de persistir el ingreso.
- Tickets worker: OCR, reglas deterministicas, clasificacion y Excel.
- Redis: estado/cache de Evolution API.

Las reacciones (`❎` correcto, `❌` cuenta incorrecta y `⛔️` duplicado)
siguen como acciones `BLOCKED_SHADOW`. Son marcas del mensaje original y nunca
excluyen el comprobante de la planilla. El correo de prueba a
Erika usa una outbox separada, destinatario allowlisted, adjuntos verificados
por SHA-256 y OAuth oficial de Gmail con alcance limitado a envio.

## Arranque

```powershell
.\scripts\Initialize-Test.ps1
.\scripts\Start-Test.ps1
.\scripts\Test-EndToEnd.ps1
.\scripts\New-EvolutionInstance.ps1
```

El arranque conserva la verificacion TLS. Si AVG inspecciona HTTPS en esta PC,
exporta su certificado raiz publico a `runtime/certs/` y lo incorpora a las
imagenes Linux como autoridad local. El certificado no se guarda en Git.

El ultimo comando crea/recupera la instancia y abre
`runtime/whatsapp-test-qr-AAAAMMDD-HHMMSS.png`. El QR debe vincularse solamente con un numero
dedicado de prueba.

### Bloqueo de vinculacion vigente

Al 21/10/2026, WhatsApp puede aceptar la lectura del QR y rechazar el alta con
`No se pueden vincular nuevos dispositivos en este momento`. Coincide con el
problema abierto de Baileys `companion_reg_refresh`:

- https://github.com/WhiskeySockets/Baileys/issues/2737
- https://github.com/WhiskeySockets/Baileys/pull/2765

El arreglo propuesto todavia no esta incorporado. No insistir con el numero ni
instalar forks no auditados. Revalidar una version estable de Evolution/Baileys
antes de un nuevo intento de vinculacion.

## Controles

```powershell
.\scripts\Status-Test.ps1
```

La reconciliacion exige:

`documentos almacenados = procesados + duplicados + review + errores + en curso`

Si Evolution anuncia un archivo pero los bytes no llegan, el mensaje permanece
registrado como `ERROR_RETRYABLE`, la reconciliacion sigue balanceada y
Evolution recibe un error temporal para reintentar la entrega. Cuando el
original llega, ese error queda resuelto y el documento continua normalmente.

Los Excel editables quedan en `runtime/exports/`, siempre ordenados por secuencia
de llegada. Las reglas no confirmadas quedan como `PENDING_RULE` o `REVIEW`.
Cada lote genera un `TICKETS_ERIKA_<grupo>.xlsx` editable por cada grupo de
WhatsApp. Cada archivo conserva el orden persistido de llegada de ese grupo y
agrega observaciones para los casos no correctos. El `manifest.json` contiene
`delivery_gate`: el correo automatico debe permanecer bloqueado salvo que
`delivery_ready` sea verdadero, la suma de filas de todos los grupos coincida
con la cantidad recibida y cada grupo tenga `order_verified=true`. Los archivos
de control y por cuenta son internos y no se adjuntan al correo de Erika.

## Gmail TEST

El envio no reutiliza cookies del navegador ni guarda contrasenas. Requiere una
autorizacion OAuth inicial y despues renueva el acceso mediante el token local,
ignorado por Git.

1. Habilitar Gmail API en un proyecto de Google Cloud.
2. Crear un cliente OAuth `Desktop app` y guardar el JSON como
   `runtime/gmail/credentials.json`.
3. Ejecutar `scripts/Authorize-Gmail.ps1` y aceptar solamente `gmail.send`.
4. Ejecutar `scripts/Send-ErikaTest.ps1` para encolar y enviar el paquete.

La accion se identifica con una clave unica. Si el proceso se interrumpe durante
la llamada a Gmail queda `DELIVERY_UNCERTAIN` y no se reenvia automaticamente,
evitando duplicados silenciosos.
