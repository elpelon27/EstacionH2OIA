# Validación 17-oct 08:00 (guardián ZCode) — doble noche

## Vie 22:00 (4/4 ejecutados, 2 válidos)
- Empédocles L4 ✓ (15 URLs), Aristeo L4 ✓ (6). Quirón L4 y Tripólemo L4 degradados [r]: grounding irrelevante.
- CAUSA RAÍZ encontrada y corregida: el extractor de dominio arrastraba "D7 —" y códigos "(9460...)" a las queries → basura. Limpieza añadida.
- Bug de rotación corregido: éxito no liquidaba pendiente_desborde (la cola quedaría congelada).

## Sáb 01:00 (4/4 ejecutados, 2 válidos)
- Aristeo L5 ✓ (12 URLs, hecho por DEEPSEEK tras vacío de glm — la caída automática FUNCIONÓ en producción), Empédocles L5 ✓ (17 URLs; los "no puedo" eran plantilla, validador afinado).
- Quirón L5 y Tripólemo L5 degradados [r] (0-1 URL).

## Mejoras
- Grounding: query EN pura (_en + "review") y query PT ("tese dissertacao pdf") añadidas.
- Validador de respaldo afinado (frases de plantilla ≠ descargo de verificación).

## Estado: desborde [Quirón (L4+L5), Tripólemo (L4+L5)] primeros el domingo 21:00. Apuntes Aristeo L5 archivados.
## Créditos: $13.34 ⚠️ acercándose a $10 — telegram enviado.
