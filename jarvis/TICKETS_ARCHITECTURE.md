# Tickets OCTOPUS: arquitectura aprobable para TEST

## Decision recomendada

Usar Evolution API con conexion Baileys solo como adaptador de WhatsApp en
TEST/shadow, sobre un numero empresarial dedicado agregado a los dos grupos.
No usar el numero personal de Luciano. Baileys opera como WhatsApp Web y por
eso puede observar grupos existentes, pero es una integracion no oficial: la
sesion puede desconectarse y existe riesgo de bloqueo.

Evolution no sera la fuente de verdad. Cada evento debe pasar primero por el
servicio de ingesta OCTOPUS y quedar persistido en Postgres y almacenamiento
de objetos antes de entrar a OCR, IA, n8n o reglas de negocio.

La API oficial de Meta es preferible por estabilidad cuando el canal lo
permite, pero su Groups API no es un reemplazo directo para leer estos dos
grupos existentes. Si Meta amplia esa capacidad, el adaptador podra cambiarse
sin modificar el nucleo de Tickets.

## Alternativas evaluadas

| Alternativa | Grupos existentes | Archivos | Persistencia/eventos | Riesgo | Decision |
|---|---:|---:|---|---|---|
| Meta Cloud API / Groups API | No como acceso directo a estos grupos actuales | Si, en conversaciones admitidas | Webhooks oficiales | Bajo | No resuelve hoy la entrada requerida |
| Evolution API + Baileys | Si, como dispositivo vinculado | Si | Webhooks y colas; requiere ledger propio | Medio/alto por ser no oficial | Recomendada para TEST controlado |
| OpenClaw WhatsApp | Si, segun el proveedor WhatsApp Web | Si | No sustituye inbox durable | Medio/alto | No usar como capa de ingesta |
| WPPConnect/WAHA/whatsapp-web.js | Si | Si | Variable; mucho mantenimiento propio | Alto | Alternativa de contingencia, no primera opcion |
| Automatizacion visual de WhatsApp Web | Si | Si | Fragil y dificil de reconciliar | Muy alto | Descartada |
| Descarga o reenvio manual | Si | Si | Auditable pero manual | Bajo | Solo contingencia, no automatizacion |

## Arquitectura

```text
Numero empresarial dedicado
        |
Evolution API / Baileys (adaptador reemplazable)
        |
Webhook autenticado + cola durable
        |
Tickets Ingest Service
  |-- Postgres: mensaje, orden, estados, evidencia
  |-- S3/MinIO: original inmutable + SHA-256
  `-- Outbox: trabajos pendientes
        |
Procesador (OCR/vision/extraccion versionada)
        |
Reglas deterministas + Auditor
  |-- tipo: transferencia / deposito / cheque-review
  |-- cuenta receptora
  |-- duplicados globales
  `-- REVIEW ante ambiguedad
        |
Generador Excel por cuenta/tipo, en orden de llegada
        |
Comparador shadow: automatico vs Erika
        |
Acciones con aprobacion: correo y, mas adelante, reacciones
```

n8n puede orquestar notificaciones, cierres y aprobaciones, pero no debe ser
el unico registro de recepcion ni almacenar el unico original. Los binarios y
el ledger viven fuera de n8n.

## Identidad y orden

- Mensaje: `(provider, instance_id, group_id, provider_message_id)` unico.
- Documento: `(message_id, attachment_index)` unico.
- Contenido: SHA-256, tamano y hash visual opcional.
- Orden: secuencia monotona asignada al persistir el mensaje; desempate por
  indice de adjunto. Nunca se reordena por fecha interna, monto o banco.
- Enlace de origen: grupo, mensaje y remitente se conservan aunque falle el
  procesamiento.

## Estados

`RECEIVED -> ORIGINAL_STORED -> QUEUED -> PROCESSING -> EXTRACTED`

Desde `EXTRACTED`, cada documento debe quedar en uno de estos grupos:

- procesado: `READY_FOR_SHEET`, `SHEET_GENERATED`, `SHADOW_COMPARED`;
- duplicado: `DUPLICATE_CONFIRMED`;
- revision: `REVIEW`, `WRONG_ACCOUNT_REVIEW`, `CHECK_REVIEW`;
- error visible: `ERROR_RETRYABLE`, `ERROR_FINAL`;
- en curso: cualquier estado anterior.

Cada transicion genera un evento append-only con actor, motivo y evidencia.
No se elimina un estado anterior ni el original.

## Regla anti-perdida

En todo momento:

```text
documentos recibidos = procesados + duplicados + review + errores + en curso
```

El webhook se considera recibido solamente despues de persistir el evento. El
archivo se descarga a almacenamiento durable y se verifica su hash antes de
encolar interpretacion. Los reintentos usan claves idempotentes. Un reconciler
periodico compara eventos del adaptador, ledger, objetos y trabajos; cualquier
diferencia genera alerta y bloquea el cierre.

Como Baileys no ofrece una garantia oficial de completitud, TEST debe medir
ademas desconexiones y contrastar cada cierre contra WhatsApp/Erika. Una sesion
caida deja un intervalo explicito pendiente de recuperar, nunca un cierre OK.

## Duplicados

- Mismo ID de mensaje/adjunto: reintento tecnico, idempotente.
- Mismo SHA-256 y tamano: copia binaria exacta, duplicado confirmado.
- Imagen pixel a pixel identica: evidencia fuerte adicional.
- Identificador bancario coincidente: candidato fuerte, sujeto a reglas y
  evidencia de cuenta/tipo.
- Persona, monto o fecha aislados: nunca son prueba suficiente.
- Coincidencia parcial: `REVIEW`.

Las reacciones se generan mediante outbox y deben vincularse al mensaje
original correcto: `❌` para cuenta incorrecta, `⛔️` para duplicado confirmado
y `❎` para ticket correcto. La reaccion es solo una marca en WhatsApp: ningun
comprobante se descarta ni se omite de la planilla por ese motivo.

## Datos extraidos

Transferencias conservan fecha ticket, monto, identificador con prioridad
numero de operacion > numero de comprobante > ID Coelsa, nombre, CUIT, banco de
origen y cuenta receptora. En comprobantes de Cuenta DNI/Banco Provincia, si el
CUIT/CUIL del emisor no aparece pero existe un DNI explicitamente rotulado, se
usa el DNI como respaldo en la columna CUIT; un CUIT/CUIL visible siempre tiene
prioridad. Se genera un Excel editable por cuenta receptora.

Depositos conservan fecha, importe, numero de comprobante y banco en un libro
separado. Cheques se preservan y pasan a `CHECK_REVIEW`.

Las cuentas reales se cargan desde configuracion segura fuera de Git. Nunca se
incorporan secretos o datos bancarios completos al codigo.

La cuenta se identifica por CBU/CVU, alias, CUIT o titular visibles. El monto
no determina la cuenta receptora ni se usa para aceptar o rechazar una
transferencia. Si el destino real no puede identificarse, el caso queda en
REVIEW aunque el importe coincida con operaciones anteriores.

## Ventanas de cierre

Las ventanas son semiabiertas `[inicio, fin)` para impedir huecos o doble
conteo. Un cierre normal cubre 15:00 del dia habil anterior a 15:00 del dia
actual. Fines de semana y feriados extienden la ventana hasta el proximo dia
habil a las 15:00; no se ejecuta un cierre sobre un dia no habil.

## Shadow mode

Durante shadow, Erika mantiene el proceso manual. Por cada cierre se comparan:

1. total y secuencia de mensajes/documentos;
2. tipo y cuenta receptora;
3. cada campo extraido;
4. duplicados, cuenta incorrecta, cheques, REVIEW y errores;
5. cantidad y orden de filas por Excel;
6. diferencias campo por campo y su causa.

No se habilitan reacciones ni emails reales. La salida es un paquete local de
comparacion. El paso a aprobacion requiere varios cierres consecutivos con
100% de integridad y umbrales de exactitud acordados con Erika.

## Etapas

1. Nucleo local: esquema, estados, idempotencia, reconciliacion y Excel.
2. Fixtures: comprobantes anonimizados representativos y evaluacion OCR.
3. Infra TEST: Postgres, S3/MinIO, cola y observabilidad.
4. Evolution TEST: numero dedicado, grupos de prueba, solo lectura.
5. Shadow real: dos grupos reales, sin reacciones ni email automatico.
6. Aprobacion: Erika recibe borradores; acciones siguen requiriendo permiso.
7. Automatizacion de bajo riesgo: Excel/email a Erika con outbox idempotente.
8. Produccion gradual: reacciones y pasos posteriores solo tras nueva aprobacion.

## Primer bloque implementado

- ledger idempotente de mensajes y documentos;
- originales referenciados por URI y SHA-256;
- historial append-only de estados;
- evidencia de duplicados y outbox de acciones;
- lotes de cierre y comparacion shadow;
- ventanas horarias;
- reconciliacion anti-perdida;
- Excel editable compatible con las columnas del ejemplo de Erika;
- pruebas sinteticas sin datos productivos ni conectores externos.
