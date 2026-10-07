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
- Shadow: snapshot local de la base real, solo lectura, reconciliado contra las
  consultas vigentes y sin efectos externos.
- Approval: propuestas de accion con autorizacion humana.
- Low-risk automation: tareas idempotentes y reversibles.
- Production: PostgreSQL, monitoreo, backups y canales controlados.

Tickets permanece fuera del alcance hasta documentar el proceso real.

## Aislamiento de Shadow

- La fuente OCTOPUS solo se abre con SQLite `mode=ro` y `query_only`.
- El agente consulta una copia con `shadow` en su nombre, nunca `octopus.db`.
- Se verifica SHA-256 de la fuente antes y despues de crear el snapshot.
- Snapshot, manifiesto y auditoria contienen datos locales y no entran a Git.
- GitHub, Render, Drive, WhatsApp, email, red y shell estan denegados por politica.
- Cada corrida integral audita todos los meses y clientes validos, conserva los
  casos REVIEW y declara explicitamente cero acciones externas.
- Los ciclos sucesivos informan solamente cambios reales por tabla, mes, cliente
  y cola REVIEW; el historial local es append-only.
