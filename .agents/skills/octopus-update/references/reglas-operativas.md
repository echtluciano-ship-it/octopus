# Reglas Operativas OCTOPUS

## Fuentes Oficiales

- Carpeta raiz oficial de Drive: `Octopus Base De Clientes`, ID `1VzjdYgBrXA1zpYDWULw1RNGN6uN3SQbL`.
- Usar `drive_sources.json` como mapa base de carpetas y archivos oficiales. Si aparece un mes nuevo en Drive que no esta en el JSON, descubrirlo desde Drive y registrar el hallazgo en la actualizacion correspondiente.
- Fuente principal para rentabilidad: `Cuadros Octopus > Pendientes Octopus`.
- `Pagos Octopus` sirve para validacion o contexto operativo; no mezclarlo con rentabilidad salvo que una regla o validacion puntual lo requiera.
- Facturacion Historica oficial: archivo registrado en `drive_sources.json`, actualmente `FACTURACION OCTOPUS.xlsx`.
- Alias oficiales: `client_aliases.csv` y las validaciones humanas persistidas en los archivos de control ya procesados.

## Fechas y Mes

- El mes operativo de un cuadro se imputa por la fecha real visible en el cuadro, principalmente fecha de ECHEQ o transferencia, no por la carpeta donde fue subido ni por la fecha del nombre del archivo.
- Si un archivo esta en una carpeta mensual incorrecta y la fecha real es clara, moverlo al mes correcto en Drive y conservar su ID/trazabilidad.
- Si el cuadro tiene multiples fechas o una fecha ilegible, clasificarlo como `REVISION` salvo que la regla ya haya sido validada para ese caso.
- Si la fecha del nombre del archivo contradice la fecha visible del cuadro, manda la fecha visible del cuadro.

## Duplicados

- Antes de incorporar un cuadro, comparar contra `manual_rentability_operations.csv`, `octopus.db` y los IDs/nombres/tamanos de Drive ya registrados.
- No contabilizar dos veces el mismo cuadro.
- Si el duplicado es confirmado, registrar `DUPLICADO` y conservar referencia al archivo duplicado.
- Si hay mismo nombre pero distinto tamano/contenido, revisar visualmente antes de marcar como duplicado.

## Clientes y Alias

- Antes de crear un cliente nuevo, normalizar el nombre y revisar `client_aliases.csv`.
- Las decisiones humanas de alias son definitivas hasta nueva instruccion del usuario.
- No unificar alias nuevos automaticamente. Si el parecido es dudoso, dejarlo para validacion.
- Mantener separados cliente + canal cuando corresponda: por ejemplo `Proteccion Inteligente - HYF` y `Proteccion Inteligente - Espora`.

## Rentabilidad

- Extraer como minimo: cliente, canal, fecha real, Facturacion Neta y Ganancia Octopus.
- Mantener separados los campos: ECHEQ/cheque o importe transferido, Facturacion Neta y Ganancia Octopus.
- Rentabilidad = `Ganancia Octopus / Facturacion Neta * 100`.
- Si el cuadro muestra ECHEQ y tambien `FC neta` / `Facturacion Neta`, usar siempre `FC neta` / `Facturacion Neta` como denominador. No usar ECHEQ para reemplazarla.
- Si el cliente/canal tiene varias operaciones, acumular Facturacion Neta y Ganancia Octopus; nunca promediar porcentajes individuales.
- Nunca convertir un dato faltante en cero.
- Render debe mostrar solo clientes con al menos una operacion valida con cliente, Facturacion Neta, ganancia y rentabilidad calculable.
- Operaciones incompletas quedan en la base interna, pero no alimentan indicadores publicados.

## Modalidades Especiales

- `OK_TRANSFERENCIA_1_2`: cuando el cuadro no muestra facturado porque los costos ya fueron pagados anteriormente y la Ganancia Octopus corresponde claramente al 1,20% del importe transferido. En ese caso la base para rentabilidad es el importe transferido visible.
- `OK_FC_NETA` / `OK_FC_HISTORICA` u operaciones con FC neta: usar solo cuando el cuadro, Facturacion Historica o una validacion previa habilita tomar ese importe como Facturacion Neta.
- Si falta Facturacion Neta visible, intentar cruce inequivoco contra Facturacion Historica antes de pedir revision.
- Si el cruce contra Facturacion Historica no es inequivoco, clasificar como `REVISION`.

## Trazabilidad

Cada operacion incorporada debe permitir responder:

- De que archivo salio.
- ID/link de Drive del archivo.
- En que carpeta estaba y, si se movio, por que.
- Cliente/canal detectado.
- Fecha utilizada.
- ECHEQ/cheque o transferencia visible cuando exista.
- Facturacion Neta usada como denominador.
- Ganancia Octopus utilizada.
- Estado: `OK`, `OK_TRANSFERENCIA_1_2`, `OK_FC_NETA`, `OK_FC_HISTORICA`, `REVISION`, `DUPLICADO` o `NO_PROCESAR`.

