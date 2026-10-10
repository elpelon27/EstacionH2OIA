# Referencia — Ingeniería del agua (protocolo, trenes y normativa)

> El agua es UN eje de cuatro del perfil — pero con protocolo propio porque
> es el producto que la casa vende y la corriente que todo proceso bebe.
> ⚠️ Los valores de norma citados aquí son (B) de memoria técnica hasta que el
> lote L6 de la misión bibliográfica los fije citados (OMS/COVENIN/EPA): cada
> uno se marca "(B, verificar)". NUNCA dictaminar cumplimiento sin la norma
> citada delante.

## §PROTOCOLO DEL AGUA (variante del protocolo de proceso)

Orden fijo en TODA consulta de agua:

1. **Uso**: ¿envasada (botellón), bebida animal, riego, proceso/limpieza? —
   la norma y el tren cambian con el uso.
2. **Fuente y diagnóstico**: pozo/superficie/municipio/salobre; parámetros:
   TDS/conductividad, dureza, pH, Fe/Mn, nitratos, turbidez, coliformes.
   Sin análisis → la primera entrega es "qué medir, con qué, cuánto cuesta".
3. **Tren de tratamiento** etapa por etapa, cada una con su propósito
   físico-químico (ver tabla abajo). Nada "porque sí".
4. **Control de calidad**: qué medir en rutina (p. ej. residual libre,
   turbidez, recuento), con qué equipo, cada cuánto, y dónde se registra.
5. **Costo + energía**: USD/m³ y kWh/m³ del tren (bombas, RO, ozonizador).
6. **Próximo paso**: el análisis o la medición que reduce la mayor
   incertidumbre.

## Trenes típicos (B — orden general, dimensionar por análisis)

| Problema de entrada | Etapas típicas | Propósito de cada etapa |
|---|---|---|
| Agua salobre de pozo (caso zuliano) | sedimentación/filtro multimedia → carbón activado → ablandamiento o AA (Fe/Mn) → **ósmosis inversa** → remineralización → desinfección final (UV/ozono) | quitar sólidos → quitar cloro/sabor → proteger membrana → quitar sal → equilibrar sabor/estabilidad → barrera sanitaria |
| Agua de red/superficie | coagulación-floculación-sedimentación → filtración → desinfección (cloro/UV) | precipitar coloides → pulir → barrera |
| Botellón (embotellado) | RO + ozono/UV + enjuague del envase con agua tratada | producto de sabor estable y segura microbiológicamente |

Reglas del oficio (B): la desinfección final NUNCA sustituye la limpieza; el
ozono da barrera + oxígeno disuelto que evita agua "plana"; el cloro residual
protege la red pero en envasado se juega con dosis baja o se prefiere
ozono/UV según norma de envasada. **Detalles y dosis: lote L6.**

## Parámetros y valores de referencia (B, verificar en L6 — NO dictaminar con esto)

| Parámetro | Referencia aproximada de memoria | Comentario |
|---|---|---|
| E. coli / coliformes | 0 en 100 mL (agua potable) | el parámetro sanitario rey |
| Turbidez | <5 NTU aceptable, ideal <1 | estética + eficacia de desinfección |
| TDS | buen gusto <600 mg/L; >1000 mg/L sabor pobre | OMS sin límite sanitario duro |
| Nitrato (NO₃⁻) | ~50 mg/L (OMS) / 10 mg/L-N (EPA) | bebés y animales: riesgo real |
| Arsénico | ~10 µg/L | tóxico crónico |
| Dureza | sin límite sanitario; estética/cal | incrustación en membranas y calentadores |
| pH | 6,5-8,5 orientativo | eficacia de cloro y corrosión |
| Cloro residual libre | ~0,2-0,5 mg/L en red (según norma) | depende de la norma aplicable |
| SAR (riego) | <10 bajo riesgo de sodificación | frontera con Tripólemo |

## Casos de la casa

- **Botellón H2O**: sin datos del tren actual = DEUDA GRANDE (ver
  `procesos-casa.md` §2). Primer entregable: mapa del tren + análisis
  completo + tabla de control de calidad rutinario.
- **Pozo salobre zuliano**: usar `procesos.py ro` para π y concentrado (con
  TDS medido); el análisis iónico real sustituye las aproximaciones (B).
- **Agua de bebida del hato**: calidad (TDS/sulfatos/nitratos) y consumo
  L/animal/día por especie y clima = lotes L3/L4 de la misión (NRC, BR-CORTE,
  FAO) — citar, no inventar.

## Saneamiento CIP del botellón (B, verificar en L6)

Lavado-desinfección del envase retornable: enjuague → solución detergente/
desinfectante → enjuague con agua tratada → inspección visual. La herramienta
`procesos.py cloro` calcula mL de solución por volumen y dosis OBJETIVO —
la dosis sale de norma/criterio, no del aire; ajustar por demanda de cloro
del agua (C, test de demanda).

## Recordatorios de frontera

- ¿Lluvia, riego, Keyline, suelo-agua, reservorios como RECURSO? → Tripólemo
  (`ingeniero-agronomo`) — su GRAN MISIÓN es "el agua no puede ser el límite".
- ¿El animal que bebe y produce menos / enfermedad hídrica? → Aristeo/Quirón.
- ¿El agua como FLUIDO, PROCESO, PRODUCTO, CALIDAD, NORMA, EFLUENTE? → tuya.
