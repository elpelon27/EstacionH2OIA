# 📋 DEUDA TÉCNICA DÍA 15 — 4 BUGS DETECTADOS
## Estación H2O · Maracaibo, Venezuela
**Fecha**: 2026-07-07 (Día 15)
**Estado**: Pendientes de fix para Día 16

---

## 🐛 Bug 1: qwen2.5:7b no sigue regla de mínimo 3

**Síntoma**: Cliente pide 2 botellones, Valentina acepta en vez de rechazar con "mínimo 3"

**Causa raíz**: 
- Fix 2 (guard de mínimos en bridge) NO se aplicó correctamente
- El logger está en línea 1120 pero el script no lo encontró por formato multilinea
- El LLM (qwen2.5:7b) no cumple consistentemente la regla del prompt

**Fix Día 16**: 
1. Aplicar guard de mínimos en bridge.py línea 1120 correctamente
2. El bridge intercepta números < 3 ANTES de llamar a Dify
3. Mensaje cálido: "Claro, con gusto le atendemos. Le comento que el pedido mínimo es de 3 unidades. ¿Desea pedir 3 o más?"

**Prioridad**: ALTA — pérdida de ingresos si cliente pide menos

---

## 🐛 Bug 2: Cálculos matemáticos incorrectos

**Síntoma**: 
- 3 recargas cobra €6 (debería €3 = 3 × €1.00)
- 2 recargas cobra €4 (debería €2 = 2 × €1.00)

**Causa raíz**: 
- qwen2.5:7b confunde precios (¿está calculando €2/botellón?)
- El LLM hace cálculos matemáticos poco confiables
- El prompt dice "Botellón de agua: €1.00 c/u" pero el modelo puede estar malinterpretando

**Fix Día 16**: 
1. Verificar prompt tiene precio correcto (€1.00) explícito
2. **OPCIÓN DEFINITIVA**: Calcular total en bridge (no en LLM)
   - Bridge parsea cantidad del mensaje del cliente
   - Bridge calcula total = cantidad × precio
   - Bridge inyecta total en el mensaje que envía a Meta
3. Así el cálculo es determinístico, no depende del LLM

**Prioridad**: CRÍTICA — cobro incorrecto a clientes

---

## 🐛 Bug 3: Mensaje compuesto mal interpretado

**Síntoma**: 
- Cliente envía "buenas me envían 3 recargas"
- Valentina responde: "¿necesita hielo también?" en vez de procesar 3 botellones

**Causa raíz**: 
- qwen2.5:7b no detecta intención correctamente con el CASO B del prompt
- El LLM interpreta "recargas" como intención ambigua
- Falta ejemplos más claros en el prompt

**Fix Día 16**: 
1. Refinar prompt CASO B con ejemplos más específicos:
   - "buenas me envían 3 recargas" → opción 1 + cantidad 3
   - "hola, 2 bolsas de hielo" → opción 2 + cantidad 2
   - "buenas, vengan a recargar" → opción 1, sin cantidad
2. Considerar detección de intención en bridge (regex) como respaldo
3. Si bridge detecta "N recargas" → interpreta como opción 1 + cantidad N

**Prioridad**: MEDIA — UX deficiente pero no bloqueante

---

## 🐛 Bug 4: Botones de pago no aparecen

**Síntoma**: 
- Valentina responde "¿Cómo desea pagar? 1️⃣ Pago Móvil 2️⃣ Efectivo"
- Pero NO muestra botones interactivos Quick Reply
- Cliente debe tipiar "1" o "2" manualmente

**Causa raíz**: 
- Regex `_detect_message_type` no coincide con respuesta real de Dify
- El regex busca `"cómo desea pagar"` pero Dify puede responder con variaciones
- El body del mensaje incluye el total + pregunta de pago, el regex no lo detecta

**Fix Día 16**: 
1. Ajustar regex para detectar variaciones:
   - `"cómo desea pagar"` o `"como desea pagar"` o `"desea pagar"` o `"método de pago"`
2. Extraer solo la pregunta de pago como body del botón
3. Botones: "💳 Pago Móvil", "💵 Efectivo"
4. Probar con respuesta real de Dify

**Prioridad**: MEDIA — UX deficiente pero funcional

---

## ✅ ESTADO: TODOS RESUELTOS (verificado 2026-07-24)

**Bug 1 (minimo 3)**: RESUELTO — Guard en bridge.py intercepta cantidades < 3 con mensaje calido en multiples estados (awaiting_qty_agua, awaiting_qty_hielo, awaiting_qty_combo, custom_qty). Lineas 1264, 1281, 1297, 1523-1531, 1563, 1582-1593, 1621, 1651.

**Bug 2 (calculos incorrectos)**: RESUELTO — `_calc_total()` deterministico en bridge.py (linea 999). `_fix_total_in_response()` sobrescribe el total que el LLM dicta con el calculo correcto del bridge. Lineas 1734, 2036, 2761, 2774.

**Bug 3 (mensaje compuesto)**: RESUELTO — Regex en bridge.py linea 1254 detecta "N recargas/botellones/agua" e interpreta como opcion 1 + cantidad N. Ej: "buenas me envían 3 recargas" → agua + cantidad 3.

**Bug 4 (botones de pago)**: RESUELTO — `_detect_message_type()` detecta multiples variaciones: "cómo desea pagar", "como desea pagar", "desea pagar", "metodo de pago", "metodo de pago". Renderiza Quick Reply con botones. Lineas 705-725.

---

## 📋 Resumen original (Día 15)

| # | Bug | Prioridad | Tiempo estimado |
|---|-----|-----------|-----------------|
| 2 | Cálculos incorrectos | CRÍTICA | 30 min (bridge calc) |
| 1 | Mínimo 3 no se cumple | ALTA | 15 min (guard bridge) |
| 4 | Botones pago no aparecen | MEDIA | 15 min (regex fix) |
| 3 | Mensaje compuesto | MEDIA | 20 min (prompt + regex) |

**Total**: ~80 min de trabajo Día 16

---

## ✅ Lo que SÍ funciona (no tocar)

1. ✅ Menú principal con List Message (5 opciones)
2. ✅ Botones de cantidad (3, 4, ✍️ Otra)
3. ✅ Botón "✅ Ya pagué"
4. ✅ Google Sheets guarda pedidos con GPS
5. ✅ GPS coordenadas extraídas correctamente
6. ✅ Guard de horario determinístico
7. ✅ Watchdog URL Cloudflare activo
8. ✅ PII_SAFE=false (teléfonos reales en Sheets)
9. ✅ custom_qty manejado localmente por bridge
10. ✅ custom_combo manejado localmente por bridge

---

**Generado por Prometeo — Día 15 cierre nocturno**
