# Control de sincronizacion - 18/09/2026

## Hallazgos antes de modificar datos

- Render y la base del commit 305de5a coincidian en julio, agosto y septiembre. Los 9 cuadros nuevos y Promored estaban incorporados.
- Drive Pendientes: 204 archivos, todos registrados; 0 archivos nuevos desde esa publicacion. Pagos: 125 archivos en julio, 184 en agosto y 63 en septiembre; se conserva como fuente de validacion.
- Facturacion Historica oficial: Drive ID 13LybCGEaAD6e6cn9VTdoXD3N_-kbBjeV, modificada 18/09/2026 13:53:09 UTC. La copia publicada tenia cargas hasta el 14/09; faltaban 8 registros fechados 15-17/09 por $120.196.765,08. Ademas se completo la fecha ECHEQ de una factura de agosto sin modificar su Neto.
- La cache de consultas solo dependia del SQL y parametros. Prueba aislada del codigo anterior: suma inicial 1, base actualizada a 3, consulta cacheada seguia devolviendo 1.
- monthly_metrics repetia 7 grupos canonicos de agosto por variantes del nombre y contaba pendientes como operaciones. Sus acumulados de agosto eran $3.237.094.654 / $199.859.029; los correctos son $3.126.596.931 / $192.354.429. Esta tabla interna no era la fuente de las tarjetas publicadas.
- Los rankings agrupaban tambien por nombre escrito, lo que separaba DAUMAS MOTOFLEX en agosto y Servicios Medicos Santa Julia en julio 2025 pese a compartir clave canonica.

## Correcciones

- XLSX oficial completo actualizado: 4.551 -> 4.559 registros, ultima Fecha Carga 17/09/2026. Se mantienen las exclusiones vigentes, incluida una fila de periodo futuro.
- Consultas cacheadas por version de SQLite/WAL; comprobacion de base/dia cada 30 segundos para actualizar sesiones abiertas.
- Tarjetas y rankings comparten consultas y corte de fecha. Rankings y tabla mensual agrupan por identidad canonica.
- La carga genera una base temporal completa, reconcilia todos los meses y la publica de una vez. data_sync_manifest.json identifica fuentes/base y conserva los resultados esperados.
- El despliegue ejecuta scripts/verify_sync.py y falla si las fuentes no corresponden a la base o no reconcilian sus indicadores.
- Skill octopus-update actualizada para revisar tambien Facturacion Historica y verificar valores publicados, no solo accesibilidad de Render.

## Controles al 18/09/2026

| Mes | Facturacion total | Registros | Facturacion con rentabilidad | Ganancia | Rentabilidad | Operaciones |
|---|---:|---:|---:|---:|---:|---:|
| Julio | 2.964.935.744,31 | 224 | 3.525.447.514 | 186.728.278 | 5,30% | 78 |
| Agosto | 4.316.074.799,38 | 320 | 3.126.596.931 | 192.354.429 | 6,15% | 82 |
| Septiembre hasta el 18 | 2.047.247.598,15 | 137 | 1.279.043.138 | 70.958.957 | 5,55% | 33 |

- 21 meses reconciliados, Top 5/10/20 comprobados y 74 clientes publicados.
- Septiembre tiene 7 operaciones validas con fecha posterior al 18/09. Siguen en el historial; no entran aun en el Inicio Ejecutivo ni en los rankings del mes abierto.
- Las 221 filas de rentabilidad, las 204 identidades documentales y las 145 decisiones de alias permanecen identicas a la base anterior. No se modificaron importes, fechas, formulas, exclusiones ni decisiones humanas.
- Se mantienen 3 revisiones anteriores: Comite Ejecutivo (periodo mayo-julio), Alimentos Viandas (fechas multiples agosto/septiembre) y LX-Espora (validacion pendiente).
