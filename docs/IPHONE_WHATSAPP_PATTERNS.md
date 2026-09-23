# Patrones de conversación WhatsApp — Extracción iPhone (one-shot)

**Fecha:** 2026-09-22 · **Origen:** backup iTunes cifrado iPhone "Estacion h2o" (iOS 16.7.16, 2026-09-15)
**Propósito:** enseñar a Valentina cómo hablan los clientes. Proceso único (no continuo).

## Resumen

| Métrica | Valor |
|---|---|
| Chats totales | 480 |
| Chats con texto | 275 |
| Mensajes totales | 36.641 |
| Mensajes de texto | 20.136 |
| Mensajes de clientes (texto) | 10.442 |
| Patrones extraídos | 219 (indexados en Qdrant `whatsapp_patterns`) |

**Reglas cumplidas:** no se guardan mensajes completos (solo patrones/frases top), teléfonos hasheados (sha256+salt), contraseña del backup solo en `config/.env`.

## Pipeline técnico (para reproducibilidad)

1. `whatsapp-chat-exporter` 0.13.0 (binario: `whatsapp-chat-exporter`, no `wbc`) + `iphone_backup_decrypt` 0.8.0 (requerido para iOS cifrado; NO viene con wbc).
2. **Bug upstream parcheado en el venv:** para iOS cifrado, wbc ignora `-k` y fuerza `getpass()` interactivo. Parche: `ios_media_handler.py` acepta `password` + `__main__.py` pasa `args.key`. (Reportar upstream eventualmente.)
3. **Requisito clave:** el WhatsApp es **Business (SMB)** → flag `--business` obligatorio (identificadores `group.net.whatsapp.WhatsAppSMB.shared`). Sin él: "Essential WhatsApp files are missing".
4. Comando exitoso:
   ```
   venv/bin/whatsapp-chat-exporter -i -b <backup_dir> -k "$PASSWORD" --business \
     -t json -j .../output/result.json --no-html
   ```
5. Extracción: 480 contactos, 36.643 mensajes, 35.871 media, 122 vCards → `output/result.json` (15 MB).
6. `scripts/whatsscan/pattern_extractor.py` → `patterns/patterns.json` (regex + counters; NO LLM para parsing — regla del Líder).
7. Qdrant: colección `whatsapp_patterns` (768-dim, Cosine) creada; 219 patrones vectorizados con `nomic-embed-text` (Ollama). IDs uuid5 deterministas (re-ejecución idempotente). Verificado: points_count=219, búsqueda semántica OK (ej. "hola buenos días quiero pedir agua" → 0.786 "Hola buenos días").

## Categorías de patrones (frecuencia de mensajes que matchean)

| Categoría | Matches |
|---|---|
| greeting | 1.169 |
| order_request | 293 |
| ask_price | 218 |
| ask_delivery | 122 |
| payment_confirm | 91 |
| complaint | 19 |

### Top por categoría

**Saludos (greeting):** "Buenos días" (170), "Buenas tardes" (135), "Hola" (68), "Hola buenos días" (68), "Hola buenas tardes" (63).

**Pedidos (order_request):** "Necesito agua" (9), "Necesito 2 recargas" (7), "Por favor envíame recarga a Monterrey" (4), "quisiera solicitar para mañana 3 bolsas de hielo y 3 botellones" (4).

**Precios (ask_price):** "Buenas que precio la recarga?", "necesito agua 2 botellas cuánto es por favor para pasarte el pago movil" — típicamente embebido en el mismo mensaje del pedido.

**Entrega (ask_delivery):** "por favor pasar por los botellones y los entregas mañana a 1era hora" (5), solicitudes de delivery/retiro de botellones.

**Pago (payment_confirm):** comprobantes "App BNC Pago Móvil" pegados, "cuánto es por fa para pasarte el pago movil", "verifique los datos".

**Quejas (complaint):** pocas (19) — "no ha llegado", "se demora mucho", disculpas del cliente por demoras propias.

### Palabras clave (top, de mensajes de clientes)

buenos (1045), gracias (969), hola (882), días (865), favor (790), buenas (693), **botellones (646)**, agua (582), **recargas (453)**, andreina (392 — la operadora), hoy (342), pago (332), recarga (251), mañana (244), necesito (218), **hielo (217)**, pendiente (191), amiga (182).

→ Vocabulario del negocio: **botellones/recargas de agua, hielo, bolsas**. "Recarga" = botellón lleno (no recarga telefónica).

### Horarios (mensajes/hora)

Pico matutino: 8-11h (2.456-3.189/hora, pico 9h). Tarde sostenida 12-16h (~1.600/hora). Caída fuerte después de 17h. Casi nada antes de 7h. → Valentina debe estar plenamente operativa 8:00-17:00.

## Recomendaciones para Valentina

1. **Detección de intención combinada:** los clientes piden+cotizan+pagan en UN mensaje ("necesito agua 2 botellas cuánto es para pasarte el pago movil"). El router de intención debe extraer múltiples slots de una sola frase.
2. **Tono:** trato cercano ("mi reina", "amiga", emoji). Respuestas deben ser cálidas pero concretas.
3. **Slots críticos por mensaje:** cantidad + producto (botellón/hielo/bolsa), dirección/zona (ej. "Monterrey"), medio de pago (Pago Móvil BNC frecuente).
4. **Confirmación de pago:** los clientes pegan comprobantes BNC Pago Móvil — Valentina debe reconocer y pedir/reconocer referencia.
5. **Entregas:** "mañana a 1era hora" es frase recurrente — soportar programación de entrega para el día siguiente temprano.
6. **Horario:** responder con prioridad 8:00-17:00; fuera de ese rango responder diferido.
7. **Botellón ≠ recarga telefónica:** el modelo debe mapear "recarga" al producto agua en este dominio.
