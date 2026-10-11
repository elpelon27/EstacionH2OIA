# Sistema de Investigación Nocturna Desatendida — Los 4 Hermanos

**Fecha:** 2026-10-10 · **Autor:** ZCode · **Estado:** INSTALADO Y PROBADO (E2E)

## Qué es
Cada noche (Lun–Vie 22:00 / Sáb 01:00 / Dom 21:00) un runner desatendido ejecuta
un lote de misión de investigación por cada hermano (Empédocles, Tripólemo,
Aristeo, Quirón) con cola rotante y registro persistente. Ejecutor:
prometeo_nocturno (qwen3.6:35b local, sin costo de API). ZCode valida la
integración cada mañana 08:00 ("dos ojos ven mejor").

## Componentes
- **Estado maestro:** `scripts/misiones/estado_misiones.json` (cola, misiones
  activas por hermano, pendiente_desborde, reintentos, historial).
- **Runner:** `scripts/misiones/mision_nocturna.py` (stdlib puro).
  1. Guard de CLI: si hay actividad reciente (<10 min) en el workspace de
     ZCode, espera (poll 2 min) y al liberarse VUELVE A PREGUNTAR por telegram.
  2. Consulta telegram (bot Hermes): 10 min para abortar; sin respuesta
     arranca solo. Abort/stop/parar → salida limpia, turno intacto.
  3. Cola: desborde/fallido primero; éxito marca lote `[x] nocturna <fecha>`
     en el mapa + HISTORIAL-TRABAJO.md + hechos.json; fallo reintenta al
     MISMO hermano (máx 2); ventana cierra 06:00 y el que no alcanzó queda
     primero. Mapa completo → hermano sale de la rotación.
  4. Cierre: rota cola (primero→último), bitácora + resumen telegram.
- **Crontab:** 3 entradas vía `cron_with_memory.sh` (registradas en
  hermes_memory.db) → log en `logs/mision_nocturna.log`.
- **Validación matutina:** automatización ZCode 08:00 (esta sesión, id
  automation-4a36ffdb): verifica respaldo real de cada lote marcado (apuntes/
  pdf/Qdrant), degrada marcas sin respaldo, repara causas (ollama/DNS),
  reporta a docs/reportes-zcode/.

## E2E verificado (3 vías, estado de prueba en /tmp)
1. **Éxito:** 4 hermanos ejecutados, prompts extraídos de los planes
   (LOTE N sustituido / jornadas contadas), cola rotó quimico→último.
2. **Fallo total:** 12 intentos (3/hermano, turno no avanza), los 4 quedan
   primeros al día siguiente, 0 marcados ok.
3. **Desborde:** 1 ejecutado antes de las 06:00, los otros 3 quedan primeros
   en orden.
Contaminación de pruebas en mapa/historiales/hechos.json revertida
(hechos 50→37, mapa Aristeo intacto).

## Limitaciones conocidas
- El guard de CLI usa actividad de archivos del workspace como proxy (los
  procesos de la app ZCode viven siempre; no son señal).
- Marcar `[x]` lo decide el exit code + tamaño de salida del modelo; la
  validación matutina de ZCode es el contrapeso (puede degradar marcas).
- Tripólemo/Quirón/Empédocles aún no tienen mapa bibliográfico: corren en
  modo "jornada N" hasta que exista el mapa (entonces pasan a modo lotes).
