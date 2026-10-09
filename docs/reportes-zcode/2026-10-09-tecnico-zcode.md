# REPORTE TÉCNICO ZCode — 2026-10-09

> Reporte del técnico ZCode (trabajos hechos directamente en el servidor).
> **Convención:** cada vez que ZCode toque este repo o la biblioteca, deja un
> reporte en `docs/reportes-zcode/AAAA-MM-DD-*.md` y registra los hechos clave
> en el grafo (`skills/memoria_hechos.py --add`). Leer el reporte más reciente
> al iniciar jornada si hay trabajo del técnico pendiente.

## 1. Skill `ingeniero-agronomo` — CREADO E INSTALADO (08-oct)

- `skills/ingeniero-agronomo/` (SKILL.md + references/pensum-ucv.md + references/recursos-servidor.md), v1.0.0, validado con `SkillRegistry` (14 skills cargados). Proyecto fuente autocontenido en `~/.zcode/workspace/default/INGENIERO-AGRONOMO/` (PERFIL, MAPA-PENSUM-UCV, copia del skill, misiones/).
- Perfil: Ingeniero Agrónomo UCV (Mención Agronomía, pensum jul-2023), enfoque eco-amigable/regenerativo Zulia; bitácoras en `docs/agronomo/aprendizajes.md` y `docs/agronomo/deudas-conocimiento.md` (crearlas al primer uso).
- Corrección post-instalación: en Qdrant `biblioteca_h2o` el payload trae `chunk` = **número de página** (no texto). El SKILL.md y la referencia lo documentan.

## 2. Biblioteca H2O — ingesta hecha por ZCode (08/09-oct)

- `Pensum_Ingenieria_Agronomica_UCV_2023.pdf` (19 chunks; Paperless doc_id 8e8e…625c). Hecho curado A MANO en `docs/biblioteca/pensum_ingenieria_agronomica_ucv_2023.md` porque Qwen no extrae tablas — **no sobrescribirlo con la pasada automática**.
- `nordeste_palma_forrageira_doc233.pdf` (Embrapa Doc 233, 48 págs, 43 chunks, Paperless 934d…08e4) — recuperación de la deuda doc/1037123 de la misión forrajes; hecho automático en `docs/biblioteca/nordeste_palma_forrageira_doc233.md`.
- Con las 16 de la misión: **17 documentos `nordeste_*`** citables (palma, xique-xique, leucena, sorgo, moringa, biofertilizantes, ILPF, agrossilvipastoril).

## 3. Misión forrajes — CIERRE verificado por ZCode (09-oct 06:55)

- Entregables verificados en `~/.zcode/workspace/default/INGENIERO-AGRONOMO/harvest/`: 18 hechos (136K, URL+pág), informe, HISTORIAL con entrada de CIERRE, 33 PDFs (16 ingeridos), nocturno 35b fuera de RAM.
- Nota: Hermes trabajó en `INGENIERO-AGRONOMO/harvest/` (no en la subcarpeta `mision-forrajes-semiarido/harvest/` del plan) — esa ruta vacía puede borrarse si se quiere orden.

## 4. Verificaciones útiles (medidas, no asumidas)

- `invocar_nocturno.py` (prometeo_nocturno): veloz 6.6 tok/s CPU, ~56 s ida y vuelta con carga. 35b carga en minutos: agrupar extracciones.
- Embrapa Infoteca responde **solo con `www`** (sin www: NXDOMAIN). SciELO, UFERSA (periodicos + repositorio) OK.

## Pendiente nuevo (no bloqueante)

- Misión "nutrición bibliográfica del pensum" planificada el 09-oct:
  `~/.zcode/workspace/default/INGENIERO-AGRONOMO/misiones/2026-10-09-mision-nutricion-bibliografica-pensum.md`.
  El Líder aún no entrega la API de Telegram para descarga de libros; el plan
  funciona sin ella (fuentes de acceso abierto primero).

— técnico ZCode, 2026-10-09
