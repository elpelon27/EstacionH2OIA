# Validación noche 2026-10-10 + arranque 10-11 (guardián ZCode)

- Noche 10-10 ejecutada por qwen legacy: 4 "ok" SIN respaldo (sin apuntes/, hechos/, Qdrant). Costo API $0.
- Acciones correctivas (hechas hoy, hecho #45): migración exacta a lotes — mapas vivos creados para Tripólemo/Quirón/Empédocles; sus L1 degradados a [ ] (⚠ qwen sin investigación real); Aristeo L1 [x] conservado por decisión del Líder.
- Estado: cola agronomo→zootecnista→vet→quimico, sin desborde. Turno de esta noche: agronomo L1, zootecnista L2, vet L1, quimico L1.
- Ejecutor desde esta noche: Hermes Agent, tier research (deepseek-v4-flash → glm-5.3-flash). Presupuesto de referencia: $1.9/jornada × 4.

# Noche 2026-10-11 — RESULTADO (guardián ZCode)

**4/4 lotes completados con sustancia real** (primer noche con Hermes + OpenRouter):
- Tripólemo L1 (suelo vivo y fertilidad): 10 URLs verificadas, apuntes por asignatura.
- Aristeo L2 (razas Bos indicus + Jersey tropical): 8 URLs (Embrapa/ABCZ/SciELO).
- Quirón L1 (semiología y patología clínica — su poder): 8 URLs + apuntes.
- Empédocles L1 (balances y termodinámica): 8 URLs + apuntes con idea nuclear.
Outputs en harvest-bibliografica/lotes/2026-10-11-*.log de cada workspace.

**Reparaciones del guardián durante la noche:**
1. Prompt no autónomo → despachador v2: inyecta mapa + lote exacto + fuentes de la casa + entrega obligatoria (candidatos/apuntes/PDFs).
2. Plugin web de OpenRouter solo soportado por Gemini (deepseek/glm → 500) → primario research = google/gemini-3-flash-preview CON plugin web; respaldo deepseek-v4-flash.
3. .env actualizado; llm_client soporta plugins por tier.

**Costo de la noche:** ~4 jornadas Gemini-3-Flash+web ≈ $0.12-0.20 total (vs $7.6 presupuesto). Muy por debajo del 30% de desviación — sin alerta.

**Pendiente para la validación de mañana (22:00):** descargar los PDFs de las listas "PDFs a descargar" de cada lote → pdfs/inbox/ → ingest_pdf.py; ingestar apuntes consolidados (<hermano>_apuntes_lote<N>); actualizar secciones de mapa con referencias.

# Noche 2026-10-12 (transición ZCode→Hermes) — RESULTADO
- 4/4: Aristeo L3 (1ª pasada OK), Quirón L2, Empédocles L2 (LIOFILIZACIÓN), Tripólemo L2 (los 3 re-hechos tras fallo de grounding DDG).
- Ejecutor: glm-5.3-flash (abierto, $0.15/$0.50) con grounding OpenAlex/Crossref.
- Incidente y reparación: DDG rate-limiteó → 3 lotes salieron "NO VERIFICADA" (modelos honestos, anti-invento funcionó) → degradación + grounding re-arquitecturado a APIs científicas + re-ejecución exitosa.
- Entrega a Hermes completada: cronjob host activo desde 13-oct, guard de fecha, manual docs/MISION-NOCTURNA-ENTREGA-HERMES.md, ZCode → guardián 08:00.
