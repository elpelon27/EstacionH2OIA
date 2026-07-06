# 📊 ANÁLISIS GOOGLE SHEETS — 10 PESTAÑAS EXISTENTES
## Estación H2O-Control (Spreadsheet ID: 1Bbp4Xqw5E7bb...)

**Análisis realizado**: 2026-07-06 (Día 14)
**Método**: VLM (glm-4.6v) sobre 10 capturas de pantalla
**Spreadsheet**: "Estacion H2O-Control"

---

## 🗂️ INVENTARIO COMPLETO DE PESTAÑAS

### 1. 📦 Pedidos (NUESTRA - creada por Prometeo)
**Filas con datos**: 1 (solo TEST, eliminar)
**Columnas (17)**:
```
Fecha | Hora | Cliente | Telefono | Producto | Cant Botellones | Cant Hielo |
Direccion | GPS | Monto EUR | Metodo Pago | Pagado | Frecuencia | Credito |
Estado | Phone Hash | Conversation ID
```
**Estado**: ✅ Operativa. Valentina escribe aquí automáticamente.

---

### 2. 💰 Pagos (EXISTENTE - 3 filas históricas)
**Filas con datos**: 3 (datos de abril/mayo 2026)
**Columnas (12)**:
```
Fecha | Cliente | Telefono | Monto EUROS | Tasa BCV | Monto Bs |
Pagado | Metodo | GPS | Frecuencia | Crédito | H
```
**Muestra real**:
- `24/4/2026 | Prueba Lider | (vacío) | (vacío) | (vacío) | Bs100.00 | sí | Efectivo | N/A | 3 días | Sí | Pe`
- `24/4/2026 | Prueba Financial | 4141234567 | €5.00 | Bs36.50 | Bs182.50 | PENDIENTE | N/A | N/A | Semanal | Sí`
- `2026-05-19 14:20 | Cliente 0000 | 584120000000 | €3.00 | (vacío) | (vacío) | PENDIENTE | Pago Móvil | https://maps.google.com/?q=10.6666,-71.6167`

**Hallazgos**:
- ✅ Ya usa formato GPS clicable (igual que nuestra implementación)
- ⚠️ Teléfono en texto plano (no hasheado) — PII concern
- ⚠️ Columna "H" sin nombre (¿incompleta?)
- 💡 Frecuencia: "3 días" / "Semanal" — coincide con agente fidelización planificado

---

### 3. 🔍 Validacion_Pagos (EXISTENTE - 3 filas)
**Filas con datos**: 3
**Columnas (4)**:
```
Referencia | Monto | Fecha_OCR | Cliente_Deteccion
```
**Muestra real**:
- `611432338363 | 2800 | 24/4/2026 | 23:45:59`

**Hallazgos**:
- 💡 Diseñada para OCR de comprobantes de pago (payment_skill con Qwen2.5-VL)
- "Referencia" = número de referencia del pago móvil
- "Monto" = en bolívares (2800 Bs)
- "Fecha_OCR" = fecha extraída del comprobante
- "Cliente_Deteccion" = parece ser hora, no cliente (¿mal mapeado?)

---

### 4. 🧠 Aprendizaje (EXISTENTE - 25 filas con datos REALES)
**Filas con datos**: 25 (mensajes reales de clientes abril-mayo 2026)
**Columnas (8)**:
```
Fecha y Hora | WhatsApp ID (Cliente) | Mensaje Original | Respuesta Propuesta |
Lógica de Decisión | status de Aprobación | G | H
```
**Muestra real (primeras filas)**:
- `28/4/2026 21:27 | 127818344198302 | "Repito están abiertos" | "Hola, gracias por contactar..." | "Modo aprendizaje activo" | EN_OBSERVACION`
- `29/4/2026 7:40 | 127818344198302 | "Hola, quiero pedir 3 botellones para hoy mismo." | PEDIDO | RECURRENTE | OK`
- `29/4/2026 7:41 | 127818344198302 | "El botellon que trajeron ayer estaba sucio" | RECLAMO | RECURRENTE | OK`
- `29/4/2026 7:43 | 127818344198302 | "Buenas, en que precio tienen el hielo ahora" | Cotización | RECURRENTE | OK`

**🚨 HALLAZGO CRÍTICO - PII EXPUESTA**:
- Los WhatsApp IDs están en texto plano: `127818344198302`, `584122560720`, `6013054918756`
- Esto viola PII_SAFE=true que implementamos
- Son datos históricos pre-Prometeo (abril-mayo 2026)
- **Acción**: hashear estos IDs o mover a hoja privada

**💡 ORO PARA ENTRENAMIENTO**:
- 25 ejemplos reales de mensajes → respuestas
- Lógica de decisión documentada (RECURRENTE, Cliente Nuevo, etc.)
- Categorización automática (PEDIDO, RECLAMO, Cotización, Consulta)
- Perfecto para mem0 + Qdrant (memoria de cliente)

---

### 5. 🏷️ Categoria_Cliente (EXISTENTE - solo headers)
**Filas con datos**: 1 (solo headers)
**Columnas (6)** — son categorías, no columnas tradicionales:
```
Residencial | Oficina | Laboratorio | Clínica | Comercio | Restaurante/Alimentos
```
**Hallazgos**:
- Estructura horizontal (categorías como columnas)
- Sin datos de clientes asignados aún
- 💡 Para agente fidelización: clasificar clientes por tipo

---

### 6. ⭐ Feedback_Clientes (EXISTENTE - solo headers)
**Filas con datos**: 3 (solo headers, sin datos)
**Columnas (6)**:
```
fecha | ID_pedido | Telefono_cliente | Puntuacion(1-5) | comentario | chofer
```
**Hallazgos**:
- Diseñada para NPS post-entrega
- "chofer" → conecta con dispatcher.py (Fase 2)
- Sin datos aún (esperando primeros pedidos reales)

---

### 7. 🤖 Feedback_Agentes (EXISTENTE - 1 fila con datos)
**Filas con datos**: 3 (1 con datos, 2 vacías)
**Columnas (5)**:
```
Fecha | Agente | Accion Realizada | Critica/Error | Sugerencia de Mejora
```
**Muestra real**:
- `29/4/2026 18:32 | Valentina | "Génesis" | "Proceso de expansión" | "Creando Agente Financiero para delegar control de caja."`

**Hallazgos**:
- Auto-log de decisiones de agentes
- Conecta con self_improve_skill.py (análisis nocturno)

---

### 8. 🗺️ Mapa_Calor (EXISTENTE - solo headers)
**Filas con datos**: 3 (solo headers)
**Columnas (7)**:
```
Sector | Calle/Avenida | Latitud | Longitud | Pasadas | Clientes_Potenciales | Ultima_Visita
```
**Hallazgos**:
- Para route_skill.py (Haversine + zonas Maracaibo)
- "Pasadas" = cuántas veces ha pasado el chofer por esa zona
- "Clientes_Potenciales" = prospección
- Sin datos aún — necesita carga inicial de sectores Maracaibo

---

### 9. 💵 Saldos_Clientes (EXISTENTE - solo headers)
**Filas con datos**: 2 (solo headers)
**Columnas (5)**:
```
ID_Cliente | Nombre | Saldo_Actual | Limite_Credito | Ultima_Actualizacion
```
**Hallazgos**:
- Para financial_agent (gestión de créditos)
- "Limite_Credito" → clientes pueden fiar hasta cierto monto
- Sin datos aún — se llena cuando clientes piden crédito

---

### 10. 📈 Ventas (EXISTENTE - 4 filas históricas)
**Filas con datos**: 4 (datos de abril 2026)
**Columnas (4)**:
```
Fecha | Teléfono | Producto | Monto Euro
```
**Muestra real**:
- `2026-04-18 | 584122560720 | Botellon 20L | 3.5`
- `2026-04-28 | 584122560720 | Botellon 20L | 3.5`
- `2026-04-29 | 127818344198302 | Botellon Prueba | 10`

**🚨 DISCREPANCIA CRÍTICA DE PRECIOS**:
- Ventas históricas: **Botellón 20L = €3.50**
- Prompt actual Valentina: **Botellón = €1.00**
- **¿Cambio el precio de €3.50 a €1.00? ¿O son productos diferentes?**

---

## 🎯 MAPA MULTI-AGENTE (Fase 2) — Actualizado con pestañas reales

```
┌─────────────────────────────────────────────────────────────┐
│  Valentina Bridge (producción)                              │
│  ESCRIBE EN: Pedidos (17 columnas)                         │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┬─────────────┐
        ▼              ▼              ▼             ▼
┌──────────────┐ ┌───────────┐ ┌──────────┐ ┌────────────┐
│ financial_   │ │ route_    │ │ analytics│ │ fidelizacion│
│ agent        │ │ skill     │ │ _skill   │ │ _agent     │
│              │ │           │ │          │ │            │
│ LEE: Pedidos │ │ LEE:      │ │ LEE:     │ │ LEE:       │
│   Saldos_    │ │  Mapa_    │ │  Ventas  │ │  Categoria │
│   Clientes   │ │  Calor    │ │  Pedidos │ │  _Cliente  │
│              │ │           │ │          │ │  Aprendizaje│
│ ESCRIBE:     │ │ ESCRIBE:  │ │ ESCRIBE: │ │ ESCRIBE:   │
│  Pagos       │ │  Mapa_    │ │  Ventas  │ │  Categoria │
│  Validacion_ │ │  Calor    │ │          │ │  Saldos_   │
│  Pagos       │ │           │ │          │ │  Clientes  │
│  Saldos_     │ │           │ │          │ │            │
│  Clientes    │ │           │ │          │ │            │
└──────────────┘ └───────────┘ └──────────┘ └────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  self_improve_skill (análisis nocturno 10pm)                │
│  LEE: Aprendizaje, Feedback_Agentes, Feedback_Clientes     │
│  ESCRIBE: Feedback_Agentes (sugerencias de mejora)         │
└─────────────────────────────────────────────────────────────┘
```

---

## ⚠️ ACCIONES URGENTES DETECTADAS

### 🚨 1. PII expuesta en Aprendizaje (prioridad ALTA)
Los WhatsApp IDs están en texto plano en 25 filas. Acción:
- Hashear los IDs existentes (script Python)
- O mover la hoja a un spreadsheet privado separado
- Documentar en ADR-008

### 🚨 2. Discrepancia de precios (necesita decisión del Líder)
- Ventas históricas: €3.50 por botellón 20L
- Prompt actual: €1.00 por botellón
- **Pregunta**: ¿El precio bajó a €1.00? ¿O son productos diferentes (20L vs recarga)?

### ⚠️ 3. Columna "H" sin nombre en Pagos
- Parece incompleta (solo "Pe" en una fila)
- Acción: eliminar o renombrar

### ⚠️ 4. Validacion_Pagos: "Cliente_Deteccion" parece hora
- La columna 4 tiene "23:45:59" en vez de un nombre de cliente
- Acción: renombrar a "Hora_Deteccion" o corregir mapeo OCR

---

## 💡 RECOMENDACIONES DE INGENIERÍA

### 1. Sincronizar Pedidos ↔ Pagos
Cuando financial_agent valide un pago, debe:
- Copiar la fila de `Pedidos` a `Pagos`
- Actualizar `Pagado` = "SÍ" en ambas hojas
- Calcular `Monto Bs` = `Monto EUR` × tasa BCV del día

### 2. Cargar Mapa_Calor con sectores Maracaibo
5 zonas sugeridas (basado en TXT histórico):
- Bella Vista (Av. 4)
- Las Delicias (Calle 72, Av. 15)
- La Limpia (Av. 28)
- Centro (Calle 90)
- Tierra Negra

### 3. Migrar Aprendizaje a mem0 + Qdrant
Las 25 filas con mensajes reales son oro de entrenamiento:
- Cargar en Qdrant como embeddings
- mem0 puede usarlas para clasificar nuevos mensajes
- Categorización automática: PEDIDO, RECLAMO, Cotización, Consulta

### 4. Automatizar Feedback_Clientes post-entrega
- Cuando Estado = "entregado" en Pedidos
- Esperar 2h
- Enviar mensaje: "¿Cómo califica su experiencia? (1-5)"
- Guardar en Feedback_Clientes

---

## 📊 ESTADÍSTICAS DEL SPREADSHEET

| Pestaña | Filas con datos | Estado |
|---------|----------------|--------|
| Pedidos | 1 (TEST) | ✅ Operativa (nuestra) |
| Pagos | 3 | 📊 Datos históricos |
| Validacion_Pagos | 3 | 📊 Datos históricos |
| Aprendizaje | 25 | 🧠 Oro de entrenamiento |
| Categoria_Cliente | 0 | ⏸️ Solo headers |
| Feedback_Clientes | 0 | ⏸️ Solo headers |
| Feedback_Agentes | 1 | 📊 1 entrada |
| Mapa_Calor | 0 | ⏸️ Solo headers |
| Saldos_Clientes | 0 | ⏸️ Solo headers |
| Ventas | 4 | 📊 Datos históricos |

**Total**: 10 pestañas, 37 filas con datos reales (la mayoría históricos de abril-mayo 2026)

---

## 🎯 PRÓXIMOS PASOS RECOMENDADOS

### Inmediato (mañana Lunes 8am - hora Caracas)
1. ✅ Esperar activación del guard de horario (Lunes 8am)
2. 🧪 Primer pedido real → verificar fila en Pedidos
3. 🧹 Eliminar fila TEST de Pedidos

### Semana 3 (Días 14-20)
1. Decisión del Líder: precio botellón (¿€1.00 o €3.50?)
2. Hashear PII en Aprendizaje
3. Cargar Mapa_Calor con 5 zonas Maracaibo
4. Invitar 5 clientes VIP

### Semana 4 (Días 21-27) - Skills Fase 2
1. `financial_agent` (lee Pedidos → escribe Pagos + Saldos)
2. `route_skill` (lee Mapa_Calor + GPS Pedidos)
3. `analytics_skill` (lee Ventas → reporte 7am Telegram)
4. `dispatcher.py` (lee Pedidos → reenvía a chofer Telegram)

---

**Análisis generado por Prometeo con VLM glm-4.6v**
