# Traspaso vigente: OCTOPUS Tickets

Actualizado: 2026-10-23 (America/Buenos_Aires)

Este documento es el punto de entrada obligatorio para continuar Tickets en el
chat dedicado `Automatizacion de tickets`. Reemplaza cualquier instruccion
anterior de ese chat que indicara no comenzar a programar: la implementacion
TEST ya existe y debe continuarse, no reiniciarse.

## Propiedad y limites

- El chat dedicado es responsable exclusivo de OCTOPUS Tickets desde este
  traspaso.
- El trabajo vive en este worktree, rama `jarvis-v0`.
- OCTOPUS general vive en `app_octopus`, rama `main`, y no debe mezclarse con
  Tickets.
- No reinstalar ni reconstruir desde cero servicios que ya funcionan.
- No conectar grupos productivos, reaccionar en grupos reales, enviar a otros
  destinatarios ni desplegar Tickets en Render sin autorizacion expresa.
- Nunca exponer ni versionar `.env`, tokens OAuth, claves de Evolution, datos
  bancarios privados o credenciales de Gmail.

## Fuentes de verdad, en orden

1. Este archivo para el estado actual y las decisiones operativas vigentes.
2. Codigo, migraciones y pruebas de `tickets_test/` y `jarvis/tickets/`.
3. `tickets_test/README.md` para operacion del entorno TEST.
4. `jarvis/TICKETS_ARCHITECTURE.md` para arquitectura y principios.
5. La conversacion historica sirve como evidencia, pero no debe contradecir
   las reglas consolidadas aqui.

Si dos fuentes se contradicen, detener la entrega, verificar el codigo y pedir
confirmacion solo si la contradiccion no puede resolverse con evidencia.

## Estado tecnico verificado

- Evolution API 2.3.7/Baileys esta levantada en Docker.
- Instancia `octopus-tickets-test`: conectada, estado `open`.
- PostgreSQL, Redis, Tickets API y Tickets worker estan activos; API saludable.
- WhatsApp TEST ya fue vinculado. No hace falta volver al QR salvo perdida real
  de sesion.
- Las llamadas de WhatsApp ya no se rechazan: `rejectCall=false` tambien quedo
  persistido en `scripts/New-EvolutionInstance.ps1`.
- Gmail API usa OAuth oficial con alcance `gmail.send`; el unico destinatario
  permitido es `oficinaoctopus13@gmail.com`.
- Erika confirmo la recepcion de los correos de prueba.
- Las reacciones de WhatsApp continuan `BLOCKED_SHADOW` y no fueron enviadas.
- Snapshot de reconciliacion del 2026-10-23: 28 esperados, 28 originales
  almacenados, 18 procesados, 2 duplicados, 8 review, 0 errores, 0 faltantes,
  ecuacion balanceada.
- Pruebas verificadas en el traspaso: 32 del servicio Tickets + 26 de
  JARVIS/Tickets = 58 aprobadas.
- `node_modules/` y `tmp/` son locales/no versionados. No agregarlos a Git.

Comandos de verificacion:

```powershell
cd tickets_test
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/audit/reconciliation
docker compose exec -T tickets-api python -m unittest discover -s tests -v
cd ..
python -m unittest discover -s jarvis/tests -v
```

## Flujo implementado

```text
WhatsApp TEST / Evolution
  -> webhook e ingreso durable
  -> Postgres + original inmutable + SHA-256
  -> worker OCR/extraccion
  -> reglas deterministas, clasificacion y duplicados
  -> auditor/reconciliacion
  -> Excel editable por grupo, en orden de llegada
  -> delivery gate
  -> outbox Gmail TEST -> Erika
```

La IA/OCR interpreta; nunca garantiza la recepcion. Un fallo posterior al
webhook no puede borrar el evento ni el original.

## Reglas funcionales consolidadas

### Integridad y orden

- Ningun mensaje o comprobante puede desaparecer silenciosamente.
- Reconciliar siempre:
  `recibidos = procesados + duplicados + review + errores + en curso`.
- Conservar ID proveedor, grupo, remitente, timestamp, secuencia de llegada,
  original, hash, estados, resultado, observaciones y vinculo al mensaje.
- El orden de cada Excel es estrictamente el orden persistido de llegada en su
  grupo de WhatsApp. Nunca ordenar por fecha interna, monto, persona o banco.
- Para una tanda de dos grupos se generan dos Excel: uno por grupo. No mezclar
  ni reordenar los grupos.
- Si una tanda manual no permite demostrar el orden original, no declararla
  correcta: bloquear entrega y pedir confirmacion.

### Archivo que recibe Erika

- Formato `.xlsx` comun, editable, sin proteccion ni solo lectura.
- Un unico archivo por grupo para esa tanda.
- Columnas visibles, en este orden:
  1. `FECHA TICHET`
  2. `MONTO`
  3. `NRO COMPROBANTE`
  4. `NOMBRE Y APELLIDO`
  5. `CUIT`
  6. `BANCO`
  7. `OBSERVACIONES`
- No agregar trazabilidad tecnica al archivo de Erika; queda en la base y en
  los manifiestos internos.
- Los casos REVIEW se resaltan y explican en `OBSERVACIONES`.
- Correctos, duplicados y cuenta incorrecta tambien permanecen en la planilla.
- El `delivery_gate` debe bloquear el correo si falta una fila, existe un caso
  sin estado terminal, cambia el orden o no coincide el total recibido.

### Extraccion

- Registrar todo dato visible; nunca inventar uno que no aparece.
- Si un dato requerido no esta o no es legible, dejarlo vacio, explicar la
  ausencia en `OBSERVACIONES` y usar REVIEW cuando corresponda.
- Identificador, en prioridad estricta:
  1. numero de operacion;
  2. numero de comprobante;
  3. ID Coelsa.
- Extraer fecha, monto, identificador, nombre y apellido, CUIT/CUIL, banco,
  cuenta destino y tipo transferencia/deposito cuando sean visibles.
- En Cuenta DNI/Banco Provincia: priorizar CUIT/CUIL; si no aparece, usar el
  DNI explicitamente rotulado como respaldo en la columna `CUIT`.
- Aprendizaje de regresion: no omitir montos, Coelsa ni datos claramente
  visibles por una lectura OCR deficiente. Contrastar el resultado con el
  original antes de entregar.

### Transferencias y cuentas

- La cuenta se decide por el destino real visible. El monto nunca selecciona
  ni rechaza una cuenta.
- Principal: LOHAS / COBROS JMC SA 630, CUIT 30-71873171-9,
  CVU 0000155300000000005630, alias OGRO.PRENDA.CATRE.
- Secundaria Supervielle: DAD720 SRL, CUIT 30-71798500-8,
  CBU 0270100010059700620013, alias LIGA.DISPARAS.LUZ.
- D&G San Lorenzo: Servicio Electron De Pago SA, CUIT 30-65986378-9,
  CBU 0720999870000032126270.
- La regla anterior de umbral de $5.000.000 esta anulada.

### Depositos, cheques y cuentas incorrectas

- Depositos se separan de transferencias.
- Macro y Comafi tienen planillas propias; validar banco, numero de deposito y
  cuenta. Sus instrucciones fueron confirmadas como completas.
- Deposito de otro banco/cuenta: conservar, cargar y marcar REVIEW.
- Cheques quedan fuera del alcance inicial: conservar original y `CHECK_REVIEW`.
- Cuenta incorrecta: no descartar; cargar con observacion y, cuando las
  reacciones se habiliten, marcar el mensaje exacto con `❌`.

### Duplicados y reacciones

- La deteccion es global entre grupos, dias y todo el historico disponible.
- Reintento del mismo ID es idempotente. SHA-256 identico es evidencia fuerte.
- Monto, persona o fecha, solos o combinados sin identificador firme, no bastan
  para confirmar duplicado. La duda queda en REVIEW.
- Reacciones acordadas por Erika:
  - `❌`: no corresponde a nuestra cuenta;
  - `⛔️`: duplicado confirmado;
  - `❎`: ticket correcto.
- Son solo marcas en WhatsApp: todos los casos se siguen cargando en Excel.
- Permanecen bloqueadas en shadow mode hasta autorizacion expresa.

### Cierres

- Ventana normal semiabierta: dia habil anterior 15:00 a dia actual 15:00.
- Fin de semana: viernes 15:00 a lunes 15:00.
- Si el cierre cae en feriado, se extiende al siguiente dia habil a las 15:00.
- Persistir timestamps y limites para que no haya huecos ni doble inclusion.

## Dataset real de 20 comprobantes

- Los originales locales se conservaron en
  `tmp/pdfs/tickets_audit/OCTOPUS_TICKETS_PRUEBA_20_2026-10-22/Originales`.
- `tmp/` no se versiona; no mover ni borrar esos originales.
- La primera extraccion tuvo fallos visibles, entre ellos monto/Coelsa de
  comprobantes que no debian quedar incompletos. Se corrigieron y se agregaron
  pruebas generales, no reglas exclusivas para esos archivos.
- Se envio a Erika un solo Excel editable de 20 tickets. Erika confirmo que la
  revision final estaba correcta y luego agrego las reglas de orden, Cuenta DNI
  y reacciones consolidadas arriba.
- La carga original de Drive puede no conservar el orden de WhatsApp; por eso
  ese dataset valida extraccion, pero no demuestra por si solo el orden real.

## Correos de prueba y lecciones

- El primer envio con varias planillas confundio a Erika.
- La entrega correcta debe ser simple: un Excel editable por grupo, sin
  archivos internos ni columnas tecnicas.
- Gmail ya envio correctamente en TEST y Erika confirmo recepcion.
- Nunca reenviar automaticamente una accion `DELIVERY_UNCERTAIN`; verificarla
  para evitar correos duplicados.
- No enviar a nadie excepto Erika durante esta etapa.

## Shadow mode y criterio de avance

- Erika continua el proceso manual en paralelo.
- Comparar cada tanda fila por fila: total, orden, campos, tipo, cuenta,
  duplicados, incorrectas, REVIEW, errores y Excel.
- Cada diferencia debe producir una correccion general y una prueba de
  regresion.
- Exigir al menos tres tandas consecutivas limpias, con integridad total y
  orden exacto, antes de considerar grupos productivos o mayor autonomia.
- En produccion se debe fallar cerrado: si el control no pasa, no se envia una
  planilla como correcta.

## Proximo trabajo obligatorio

1. Inspeccionar este worktree y ejecutar las 58 pruebas; no confiar solo en
   este documento.
2. Verificar que el delivery gate produce exactamente un `.xlsx` editable por
   grupo, preserva la secuencia persistida y bloquea cualquier faltante,
   duplicacion artificial, reordenamiento o estado no terminal.
3. Verificar reconciliacion y salud de servicios.
4. Solo despues avisar textualmente a Luciano:
   `Luciano, manda la nueva tanda por los dos grupos TEST.`
5. Procesar esa tanda end-to-end y compararla con Erika.

No pedirle a Luciano que repita reglas ya incluidas aqui. Preguntar solo ante
una contradiccion real o una accion externa/irreversible que requiera su
intervencion.

## Commits relevantes

- `99268f5`: permitir llamadas en WhatsApp TEST.
- `2bca2cc`: bloquear entregas incompletas y generar Excel por grupo.
- `cc5b2c9`: reglas operativas de Erika y reacciones correctas.
- `b8d0ddb`: auditoria de correcciones humanas.
- `1afda3d`: planilla editable.
- `9134a42`: entrega simplificada para Erika.
- `e27a42f`: transporte TLS de Gmail.
- `9f176f6`: envio Gmail auditable.
- `3c725b9`: endurecimiento de validacion e ingreso aislado.
- `be261a5`: flujo WhatsApp TEST y revision trazable.

