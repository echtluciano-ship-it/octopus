---
name: octopus-update
description: Actualizar OCTOPUS desde Google Drive cuando el usuario pida "Actualiza OCTOPUS", "actualizar cuadros", "sincronizar Drive/base/Render" o una actualizacion operativa equivalente del proyecto OCTOPUS. No usar para agregar nuevas funcionalidades de interfaz o para analisis largos no relacionados con la actualizacion.
---

# OCTOPUS Update

Usar esta skill para mantener OCTOPUS actualizado desde la carpeta oficial de Google Drive hasta Render. El objetivo es ejecutar el flujo ya validado, sin pedirle al usuario que repita reglas permanentes y sin cambiar reglas de negocio.

## Antes de actuar

- Trabajar sobre el repo existente `app_octopus`; no crear una app nueva.
- Usar Google Drive como fuente oficial viva y revisar el estado mas reciente antes de procesar.
- Leer las reglas vigentes en [Reglas Operativas](references/reglas-operativas.md) y el procedimiento en [Flujo de Actualizacion](references/flujo-actualizacion.md).
- Si la actualizacion toca clientes, alias, cuadros dudosos o casos especiales, consultar tambien [Casos Validados](references/casos-validados.md).

## Principios

- Procesar todo lo que pueda resolverse con reglas ya validadas.
- No convertir casos dudosos en decisiones automaticas.
- Si un archivo necesita intervencion humana, clasificar solo ese archivo como `REVISION`, conservar la trazabilidad y continuar con el resto.
- Nunca inventar facturado, ganancia, cliente, canal ni fecha.
- No modificar la interfaz de Render salvo que el usuario lo pida explicitamente; en una actualizacion normal solo se actualizan datos/base.

## Cierre Esperado

Al terminar, responder con un resumen corto:

```text
Cuadros nuevos encontrados: X
Procesados: X
Duplicados: X
En revision: X
Clientes existentes actualizados: X
Clientes nuevos creados: X
Total publicado en Render: X
Sincronizacion Drive -> base -> Render: SI/NO
```

Si queda algo en revision, indicar exactamente archivo, cliente probable si existe, link/ID de Drive y el dato que falta.

