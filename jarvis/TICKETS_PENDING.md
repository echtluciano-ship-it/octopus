# Tickets: relevamiento cerrado, integracion pendiente

El proceso funcional fue relevado con Erika el 21/10/2026. La arquitectura y
el alcance vigente estan en `TICKETS_ARCHITECTURE.md`.

Este modulo ya no esta bloqueado por reglas de negocio generales. Antes de
conectar una cuenta real siguen requiriendo autorizacion explicita:

- numero empresarial dedicado y acceso a los dos grupos;
- infraestructura TEST para Evolution API, Postgres, cola y almacenamiento;
- cuentas receptoras cargadas en configuracion segura;
- archivos de instrucciones de depositos Comafi y Macro;
- politica de retencion y acceso a comprobantes con datos personales;
- formato del Excel manual de cada cuenta secundaria y depositos;
- criterio de feriados para ventanas de cierre;
- autorizacion separada para reacciones, correo y cualquier escritura real.

Hasta entonces no se conecta WhatsApp, no se reacciona, no se envia correo y
no se toca OCTOPUS/Render.
