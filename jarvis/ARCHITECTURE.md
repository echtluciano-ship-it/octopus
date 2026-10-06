# Arquitectura JARVIS / OCTOPUS

## Principio central

Los agentes coordinan y explican. OCTOPUS Core conserva las reglas de negocio,
la identidad documental, los calculos y la autoridad sobre los datos.

## Capas previstas

1. Canales: interfaz local; WhatsApp y web mas adelante.
2. Gateway: OpenClaw opcional y reemplazable.
3. Coordinator: selecciona un objetivo y un especialista autorizado.
4. Specialists: documentos, validacion, comercial y publicacion.
5. Policy/Approval: permisos minimos e intervencion humana.
6. OCTOPUS Core: herramientas tipadas; nunca SQL libre desde un modelo.
7. Data: PostgreSQL futuro, Drive y fuentes oficiales.
8. Audit: eventos, evidencia, decisiones, costos y resultado.

## Etapas

- V0 Lab: datos sinteticos y solo lectura.
- Shadow: fuentes reales de solo lectura sin efectos externos.
- Approval: propuestas de accion con autorizacion humana.
- Low-risk automation: tareas idempotentes y reversibles.
- Production: PostgreSQL, monitoreo, backups y canales controlados.

Tickets permanece fuera del alcance hasta documentar el proceso real.
