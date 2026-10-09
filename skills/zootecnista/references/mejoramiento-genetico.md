# Referencia — Mejoramiento genético: la caja de herramientas de Aristeo

> Fundamento: pensum UFV ZOT — BIO240 Genética, **ZOO460 Teoria do Melhoramento
> Animal**, **ZOO461 Melhoramento Animal Aplicado**, BIO342 Genética Quantitativa
> (optativa estrella). Los rangos numéricos son orientativos (varían por
> población y sistema de producción): cuando la cifra sea crítica, citar la
> fuente específica de la biblioteca o marcarla (C) para medir en el hato.

## 1. Heredabilidad (h²) — qué puede esperar de la selección

h² = V_A / V_P (varianza aditiva / fenotípica). Interpretación práctica:

| Rango | Características típicas | Consecuencia |
|---|---|---|
| **Baja (0,02–0,15)** | fertilidad (días abiertos, IEP), supervivencia, resistencia a parásitos | la selección directa avanza lento: primero **mejorar manejo**, seleccionar con muchas hijas/registros (o genómica) |
| **Media (0,20–0,35)** | peso al destete (P205), peso al año, producción de leche 305 d, GMD a pastoreo | la selección funciona con buenos registros y presión de selección sostenida |
| **Alta (0,35–0,60)** | peso al nacer, GMD en confinamiento, área de ojo de lomo (AOL), espesor de grasa dorsal, marmoreo, características de tipo | responde bien y rápido; el riesgo está en las correlaciones no deseadas |

**Trampas por correlación genética:** peso al nacer ↑ → distocia ↑ (usar DEP de
nacimiento de la raza materna); peso adulto ↑ → requerimiento de mantención ↑;
producción de leche ↑ → condición corporal y fertilidad ↓ si el pasto no acompaña.
SIEMPRE seleccionar con índice, no con una sola característica.

## 2. Respuesta a la selección

```
R = h² × S                        (respuesta por generación, selección masiva)
ΔG_anual = (i × r × σ_A) / L      (palancas: intensidad i, exactitud r,
                                   variabilidad aditiva σ_A, intervalo generacional L)
```

- **i** (intensidad): usar pocos toros de prueba, descartar sin piedad (en el
  hato: descarte de vacas improductivas y de toros sin registro).
- **r** (exactitud): registros completos > números de memoria; sumarios con ACC
  alta > boletos de feria; genómica cuando el hato lo pague.
- **σ_A**: mantener variabilidad (no consanguinear); si el hato es pequeño,
  la variabilidad se compra con la raza/cruzamiento correcto.
- **L** (intervalo generacional): el cheque más rápido — usar toros jóvenes
  evaluados, edad al primer parto temprana (~30-36 meses en cebú bien manejado),
  renovación decidida.

## 3. DEP/EPD y exactitud (ACC)

- **DEP** = mitad del valor genético del animal; se compara DENTRO de la misma
  raza/programa (¡jamás cruzar DEPs de sumarios distintos sin factores de
  enlace!). La cría espera **la mitad de la DEP del toro** (+ la mitad de la
  vaca).
- **ACC (0–1):** < 0,4 baja (animales jóvenes, sin hijas: rango esperado
  amplio) · 0,4–0,7 media · > 0,7 alta (se puede firmar). Regla: con ACC baja,
  mirar el margen (DEP ± rango) y no el punto.
- Fuentes de sumarios: ABCZ (Nelore, Guzerat, Gir, Sindi), teste de progenie
  Gir Leiteiro (Embrapa Gado de Leite/ABCGIL), PMGG/ANCP, Conexão Delta G,
  Geneplus, Girolando (testes y sumarios de la raza sintética).
- **Genómica:** SNP chips → GEBV con mayor confiabilidad temprana; útil para
  parentesco y selección de reproductores jóvenes; coste-beneficio por tamaño
  de hato — en Zulia, primero registros y ACC, genómica cuando pague.

## 4. Índices de selección

```
I = w₁·DEP₁ + w₂·DEP₂ + ... + wₙ·DEPₙ     (wᵢ = peso económico real del hato)
```

- El objetivo de selección se define **con el Líder**: ¿kg destetados/vaca?
  ¿litros/lactancia? ¿litros/ha? ¿precocidad? El índice sigue al objetivo.
- Ejemplo de lógica de hato de doble propósito tropical: w alto en DESTETE
  (corte) + w medio en LECHE + penalización en peso al nacer + materna en
  Guzerat/Gir.
- BLUP/REML y el modelo animal (matriz de parentesco A) es como nacen las DEPs
  de los programas; entenderlo basta para usarlas bien.

## 5. Cruzamientos y heterosis

**Heterosis** = desviación de la media de los padres (vigor híbrido). Máxima en
características de baja h² (reproducción, supervivencia) — por eso cruza tan
bien en el trópico. Dos componentes: **individual** (lo expresa la cría) y
**materna** (lo expresa la vaca F1 como madre).

Valores orientativos en cruzamiento Bos indicus × Bos taurus (ponderado por la
literatura tropical):

| Característica | Heterosis individual | Heterosis materna |
|---|---|---|
| Supervivencia de ternero | +10 a +15 % | — |
| Peso al destete | +15 a +25 % | +10 a +20 % (vaca F1 desteta más) |
| Producción de leche (F1) | +20 a +30 % vs. media parental | — |
| Edad a la pubertad | −6 a −10 % | — |

**Retención de heterosis según sistema:**
- F1 (dos razas, vender todo): 100 %
- Rotación de **2 razas**: estabiliza en **~67 %**
- Rotación de **3 razas**: estabiliza en **~86 %**
- Sintético (ej. Girolando): heterosis fija de origen (~25 % si 5/8–3/8), se
  conserva por dentro pero sin opción de "rescargar" con raza pura.

**Composición genética esperada:** F1 = 50/50 · backcross = 75/25 · equilibrio
rotación 2 razas = 67/33 · rotación 3 razas ≈ 57/29/14.

**Sistemas y cuándo usarlos:**
| Sistema | Cuándo |
|---|---|
| **Rotacional 2 razas** (ej. Guzerat ↔ Jersey) | el hato cría sus propias reemplazas; simple, funciona con 2 potreros de toros/semen |
| **Rotacional 3 razas** (ej. Nelore → Jersey → Guzerat) | más heterosis retenida; exige más organización de lotes |
| **Terminal** (F1 materna × toro terminal de carne) | máxima producción de carne; NO guardar hembras del terminal |
| **Sintético** (Girolando 5/8 Gir 3/8 Holstein) | cuando ya existe la población; estabiliza y simplifica |

## 6. Consanguinidad

- Coeficiente F: en hatos pequeños, rotar toros SIN parentesco con las vacas;
  manter F por animal **< 5-6 %**; caída típica: fertilidad y supervivencia
  (justo lo que no se puede perder en el trópico).
- Registro genealógico básico: quién es hijo de quién — sin eso, cualquier toro
  "nuevo" puede ser un nieto.

## 7. El programa genético del hato (su ciclo de temporada)

1. **Objetivo** acordado con el Líder (1-3 características, pesos económicos).
2. **Registro**: identificación (tatuaje/chapa), nacimientos, destetes (fecha,
   madre, sexo, peso), partos, IEP, litros si hay ordeño, bajas.
3. **Evaluación anual** del hato con los datos (DEP empírico propio + sumarios
   externos de los toros usados).
4. **Plan de apareamientos** (individual, evitando consanguinidad y distocia).
5. **Estación de monta / IATF** con los toros/semen elegidos.
6. **Destete + medición + informe**: números, decisiones (descartes, compras)
   y el próximo ensayo con testigo.

**La regla de oro de Aristeo:** *sin registro no hay mejoramiento — solo
repetición.*
