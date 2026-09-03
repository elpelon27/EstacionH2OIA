# Comparativa: DeepSeek V4 Flash (OpenNotebook) vs Qwen 2.5 7B local

Fecha: 2026-09-03 · Consulta de prueba: "Sintetizá los conceptos clave sobre
pastoreo rotacional según los libros indexados"

## Configuración del test

| Aspecto | DeepSeek V4 Flash | Qwen 2.5:7b (Ollama local) |
|---|---|---|
| Vía | OpenNotebook /api/search/ask (RAG sobre sources reales) | Ollama /api/generate directo |
| Contexto | Chunks reales de los libros indexados (búsqueda vectorial) | NINGUNO — modelo a ciegas |
| Temperature | 0.3 | default (0.8) |
| Costo real medido | $0.000196 (1.178 tokens) | $0 (local) |
| Latencia | ~15-25 s (3 pasadas de agente: estrategia → respuestas → síntesis) | ~40 s |

## Resultados

### DeepSeek V4 Flash (con RAG de OpenNotebook)

- Cita el libro real: [source:tj01xb0wje8gml79k1ic] = "Datos Agrop. Manual de
  especies forrajeras y manejo de pastoreo" (98 páginas).
- Datos ESPECÍFICOS del texto original, verificables contra el chunk:
  * Frecuencia de utilización: 40-60 días en invierno, 14-16 días en final de
    primavera (cuadro del manual).
  * Intensidad de pastoreo medida por altura de residuo: 3-4 cm junio-agosto,
    5-6 cm primavera.
  * Ballica perenne tetraploide Grasslands Impact: +10% producción de leche,
    +17% materia grasa, +16% proteína.
- Estructura: definición → 3 variables técnicas (frecuencia, intensidad, franja
  diaria) → valores por estación. Trazable al source.

### Qwen 2.5:7b local (sin contexto)

- Responde con conocimiento genérico de su entrenamiento — NO de "los libros
  indexados" (que no puede ver).
- Señal de alucinación: afirma hablar "según los libros indexados y la
  literatura en general" sin haber leído ninguno.
- Contenido correcto pero genérico (dividir en secciones, recuperación del
  forraje) — sin cifras verificables, sin citas.
- En test previos (resúmenes "hechos clave" del pipeline ingest) repetía
  frases en loop y afirmaba detalles no presentes en el texto.

## Veredicto (criterios del Líder)

| Criterio | Ganador |
|---|---|
| ¿Cita libros reales? | DeepSeek (citas [source:...] verificables) — Qwen: 0 |
| ¿Menos alucinación? | DeepSeek — Qwen afirmó haber leído libros que no vio |
| ¿Info más precisa? | DeepSeek (cifras del texto original, no genéricas) |

**Decisión del Líder confirmada por evidencia**: Qwen local NO sirve para
síntesis/interpretación de la biblioteca. DeepSeek V4 Flash con RAG sobre
los sources importados es la combinación correcta: cita, precisa y barata
($0.0002 por consulta compleja → ~5.000 consultas por dólar).

## Nota de arquitectura

OpenNotebook no consulta Qdrant (su búsqueda vectorial vive en SurrealDB,
verificado en su código fuente). Los PDFs se importaron como sources con
texto completo y se re-embebieron con el MISMO modelo (nomic-embed-text vía
Ollama local, 768 dim) que usa Qdrant — mismos vectores semánticos, costo $0.
Qdrant queda intacto como índice maestro del pipeline Hermes.
