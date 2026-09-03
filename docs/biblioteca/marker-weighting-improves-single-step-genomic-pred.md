# Marker-weighting-improves-single-step-genomic-pred

- **Archivo:** `/mnt/ssd_trabajo/biblioteca/pdfs/inbox/Marker-weighting-improves-single-step-genomic-pred.pdf`
- **Páginas:** 13
- **OCR aplicado:** no
- **Paperless doc_id:** 735b9b28-390c-4bea-97f1-3de2fc5aca05
- **Chunks Qdrant:** 38
- **Ingestado:** 2026-09-02T21:17:26+00:00

## Hechos clave (Qwen local)

- Los modelos de predicción genómica estandarizadas únicos asumen que todos los marcadores SNP explican igual cantidad de varianza genética, lo cual puede no ser verdadero.
- En la investigación se desarrollaron modelos multitrait estándar de predicción genómica única (ssGBLUP) basados en las evaluaciones randomizadas por tiempo para las características de salud del seno de vacas de leche de Noruega Roja (RDC) y Jersey (JER). Incluyen 4 marcadores de mastitis clínica (CM), 3 marcadores SCS test-day y los marcadores de conformación para el seno.
- Se investigó la efectividad de diferentes escenarios de ponderación de marcadores SNP en modelos de predicción genómica única, utilizando un modelo de ponderación lineal a mejor estimación unbiased predictiva (SNPBLUP) único.
- La mejora en la fiabilidad de predicción se midió mediante una validación forward, eliminando los últimos 4 años de datos para predecir valores de valor genético (VG) para candidatos de validación. Se examinaron también las tendencias genéticas de los valores VG basados en el pedigree y GEBV.
- Los conjuntos de datos para RDC y JER incluyen 6,900,000 y 1,200,000 animales respectivamente. Se midieron 5.6 millones y 0.9 millones de vacas con registros, respectivamente. El número de animales genotipados fue de 125,789 para RDC y 64,777 para JER.
- Se investigaron tres escenarios de ponderación de marcadores SNP: (1) un método no lineal similar al BayesA, (2) el uso del fórmula clásica 2pqû 2 que tiene en cuenta la heterocigosis de los alelos y el efecto del marcador, y (3) aplicar una ponderación promedio SNP basada en 2pqû 2 para cada 20 marcadores adjuntos.
- Se encontró que la tendencia genética favorable reciente en las características CM y SCS se aceleró desde la introducción de la selección genómica. La investigación también muestra que una mejora significativa en la fiabilidad de predicción, es decir, un aumento del 0.74 para RDC y 0.72 para JER respecto a los valores VG basados en el pedigree, se puede lograr con un modelo de predicción genómica única estándar comparado con un modelo de predicción basado en el pedigree.
- Se encontró que casi todos los escenarios con ponderación SNP mejoraron la fiabilidad de predicción entre el 0.5% y el 12.7%. El mayor aumento se logró al ponderar los marcadores SNP según la fórmula 2pqû 2.
- La ponderación de marcadores SNP mejora la fiabilidad de predicción en las características de salud del seno para poblaciones de vacas de leche de Noruega Roja y Jersey.
