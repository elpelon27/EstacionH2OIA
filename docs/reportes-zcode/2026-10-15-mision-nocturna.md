# Validación 15-oct 08:00 (guardián ZCode) — incidente mayor reparado

## Hallazgo: las noches 13 y 14-oct murieron en silencio a mitad
- Síntoma: proceso noche_hermes desaparecía durante un research call, sin OK/registrar/cierre; cron_with_memory traga tracebacks por diseño (privacidad §6.6) → doble silencio.
- Causa raíz (forense): logs stub de 102 bytes = solo header. glm-5.3-flash (razonador) devolvió a veces content=None → `len(None)` TypeError NO capturado en cmd_ejecutar → muerte del orquestador.
- Noche 13: 3/4 (vet L3 ✓ 26 URLs, quimico L3 ✓ 16, agronomo L3 ✓ 23); Aristeo L4 perdido.
- Noche 14: 1/4 (vet L4 hecho pero con grounding irrelevante — medicina humana); quimico L4 perdido.

## Reparaciones (probadas)
1. cmd_ejecutar: content=None → rc=1 limpio (simulación E2E: rc=1, sin excepción).
2. noche_hermes: try/except alrededor de cada ejecución — NADA mata la noche en silencio.
3. Quirón L4 degradado [x]→[r]; proximo_lote y marcar_lote ahora entienden [r] reintentar.
4. Grounding mejorado: calificador científico EN por hermano en las queries (OpenAlex/Crossref indexan en inglés — causa del grounding irrelevante de Quirón).
5. Turnos recuperados: pendiente_desborde = [Aristeo L4, Quirón L4, Empédocles L4] — primero esta noche 15-oct.

## Consolidación del día: suspendida por reparación (se retoma mañana con los PDFs de los lotes 13/14).
## Créditos: $16.91 (>$10, sin alerta de umbral). Telegram de incidente enviado al Líder ✓.
