# Referencia — Los procesos de la casa (números verificados y deudas)

> El campo de práctica de Empédocles. Todo dato lleva su fuente y nivel (A)/(B)/(C).
> Lo que NO está aquí con (A) es DEUDA: medir, cotizar o cazar bibliografía.

## 1 · Liofilización BARF ovino (proyecto LIOFILIZACION, estudio v1.0 — 2026-10-08) ⭐

**Decisiones del estudio v1.0 (A, `LIOFILIZACION/` en el workspace ZCode):**

| Dato | Valor |
|---|---|
| Máquina recomendada | Escala B tipo Harvest Right Commercial |
| Precio máquina | USD 13.895 FOB (vía Miami) |
| Capacidad de condensador | **15-18 L de hielo por lote** (= 13,7-16,5 kg de agua) |
| Energía máquina | 120 V/60 Hz (verificar kW del modelo al cotizar) |
| CAPEX fase 1 | USD 31-47 k |
| Costo/kg producto | USD 13-25 (varios SUPUESTO) |
| Precio venta local | USD 28-50/kg (referencia internacional 70-110) |
| Payback | 16-30 meses |
| Producto estrella | Caldo de hueso liofilizado |
| Valorización integral del animal | +30-60 % de ingreso |
| Obligatorio en Zulia | Planta eléctrica de respaldo + sala climatizada |
| Roadmap | fase 0 validación USD 4-6 k → 1 piloto → 2 escala → 3 faena propia |

**Lo que Empédocles aporta AHORA (C — ensayos fase 0):**
kg de agua sublimada/h con producto real; kWh ELÉCTRICO por lote (compresor +
vacío) para dimensionar planta; isotermas/Aw del producto terminado → empaque
y vida útil; rendimiento kg producto/kg materia prima.

**Herramienta:** `python3 procesos.py liofilizacion --masa-kg 15 --humedad-pct 90`
→ hielo a condensar (14,7 L) y energía térmica de sublimación (10,7 kWh_t).

## 2 · Agua de la Estación H2O (el negocio de la casa) ⭐

**Lo verificado:** la casa produce y vende agua envasada (botellones) con
despacho diario a 359+ clientes (A, sistema Valentina/despacho). Cadena:
pedido → pago → despacho → POD (software de otros — no tocar).

**DEUDA INICIAL GRANDE (registrar al primer uso):** ¿fuente (pozo/municipio)?
¿tren de tratamiento actual (filtros/RO/ozono/UV/lamp?)? ¿último análisis
fisicoquímico y microbiológico? ¿norma con la que se juzga hoy? ¿costo por m³?
Sin eso, cualquier diagnóstico es (C). Plan: plano del tren + análisis
completo + muestreo semanal → `agua-procesos.md` y `preguntas-abiertas.md`.

## 3 · Fermentaciones de la finca

| Proceso | El reactor | Números de la casa |
|---|---|---|
| Silaje | batch anaerobio, sellar <48 h, pH meta 3,8-4,5 (B) | práctica difundida en biblioteca forrajes (Embrapa/nordeste) (A); ensayos propios = deuda |
| Biofermento (estiércol+melaza, 21 días) | batch, tambor 200 L (A, Restrepo) | receta en biblioteca: BIOFERTILIZANTE FERMENTADO POSTA VACA.pdf (A) |
| Compost | batch aerobio exotérmico, C:N ~25-30:1 (B) | material Restrepo (A); curva térmica propia = deuda |

**Herramienta:** `python3 procesos.py ensilaje --componentes ...` y
`python3 procesos.py compost --componentes ...`.

## 4 · El hato y su agua

Bovinos Bos indicus/Jersey (Aristeo) + ovinos Dorper/Santa Inés (línea BARF).
Agua de bebida: consumo por especie en clima cálido y calidad (TDS, sulfatos)
= DEUDA (lote L3 de la misión bibliográfica: NRC/BR-CORTE + FAO). Efecto de
TDS alto en consumo y producción: rangos a citar, no inventar.

## 5 · Energía off-grid (Zulia)

- Luz inestable: TODO proceso crítico (liofilizador, cadena de frío de
  vacunas/fármacos, bombeo de agua) lleva plan de contingencia (planta,
  prioridad de cargas, colchón térmico).
- DEUDA: inventario de cargas (kW) de la casa → tamaño de planta; horas/día
  reales de servicio eléctrico; costo USD/kWh de generar con planta vs. red.
- Candidatos de estudio (C): secado solar de forrajes, biogás de efluentes.

## 6 · Protocolo de trabajo con los hermanos (empalmes)

| Empalme | Firma el hermano | Firma Empédocles |
|---|---|---|
| Silaje | ración y animal (Aristeo) | fermentación, MS, sellado, aditivos |
| Agua de bebida | efectos en el animal (Aristeo/Quirón) | calidad, tratamiento, normativa |
| Fármaco/vacuna | prescripción y clínica (Quirón) | estabilidad, dilución, cadena de frío |
| Compost/biofermento | biología del suelo (Tripólemo) | reactor, C:N, curva térmica |
| Riego | recurso hídrico y cultivo (Tripólemo) | calidad/salinidad/SAR del agua |
| Liofilizado BARF | nutrición (Aristeo), inocuidad (Quirón) | proceso, Aw, empaque, costo |
