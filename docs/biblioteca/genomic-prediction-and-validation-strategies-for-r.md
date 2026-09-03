# Genomic-prediction-and-validation-strategies-for-r

- **Archivo:** `/mnt/ssd_trabajo/biblioteca/pdfs/inbox/Genomic-prediction-and-validation-strategies-for-r.pdf`
- **Páginas:** 19
- **OCR aplicado:** no
- **Paperless doc_id:** 3867bec9-dd55-4592-9ab9-4e15ab1b5fc1
- **Chunks Qdrant:** 46
- **Ingestado:** 2026-09-02T08:25:38+00:00

## Hechos clave (Qwen local)

- Los datos de phenótipos y la información de línea de parentesco se recopilaron en 47 granjas de leche Holstein ubicadas en Beijing (BJ) y Ningxia (NX).
- Se utilizaron registros de nacimiento, inseminación, parición y chequeo de embarazo para 194,574 animales.
- Los datos se dividieron en poblaciones de referencia y validación basadas en el año de nacimiento. La población de referencia incluyó a las vacas del año 2013 a 2020 en Ningxia (NX) y la población de validación al año 2010 a 2020 en Beijing (BJ).
- Se evaluaron tres características: intervalo entre la primera y última inseminación (IFL), tasa de concepción en la primera inseminación (CR_f) y número total de inseminaciones (NS).
- La CR_f se codificó como 1 si había un embarazo confirmado después de la primera inseminación, y 0 en caso contrario.
- El IFL fue registrado como 0 para las vacas que estaban embarazadas después de la primera insersión, y el número real de días entre la primera e última insersión en otro caso.
- Ningxia es más templada que Beijing (BJ), con condiciones climáticas diferentes.
- Se utilizaron datos genéticos de 12,731 vacas y 3,477 ganaderos domésticos para el análisis.
- Los datos genéticos se imputaron a un panel de SNP de mayor tamaño utilizando la herramienta Beagle v5.0.
- Se evaluó una mejora en la precisión del pronóstico genético al combinar datos de diferentes regiones, con aumentos que oscilan entre 2.74% y 93.81% para el área con menos datos disponibles.
- El método LR (regresión lineal) se utilizó para validar los pronósticos genéticos en diferentes entornos, lo cual permitió evaluar la precisión de los valores genéticos de breeding (EBV).
- Se observaron mejoras significativas en el pronóstico del IFL y NS cuando se consideraban factores de interacción entre genotipo y entorno.
- Los modelos RNM (norma continua del entorno) permiten evaluar la precisión del pronóstico para las características con interacciones G × E (genotipo x entorno).
- Se recomienda el uso de los modelos RNM para validar pronósticos genéticos en diferentes entornos y considerar factores de interacción entre genotipo y entorno.
- Los resultados indican que la precisión del pronóstico genético puede ser mejorada al combinar datos de diferentes regiones, especialmente para características con baja heritabilidad como las de reproducción.
