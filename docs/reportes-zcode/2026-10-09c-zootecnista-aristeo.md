# REPORTE TÉCNICO ZCode — 2026-10-09 (c) — Skill `zootecnista` (Aristeo)

## 1. Skill `zootecnista` — CREADO E INSTALADO (09-oct)

- `skills/zootecnista/` (SKILL.md + references/pensum-ufv-zot.md +
  references/mejoramiento-genetico.md + references/recursos-servidor.md),
  **v1.0.0**, validado con `SkillRegistry` (**15 skills cargados**, zootecnista OK,
  8.802 chars de instrucciones). Proyecto fuente autocontenido y AISLADO en
  `~/.zcode/workspace/default/ZOOTECNISTA/` (PERFIL, MAPA-PENSUM-UFV, pensum/,
  skill/, README, INSTALACION).
- **Perfil: Aristeo, el Zootecnista de la casa** (nombre a pedido del Líder, por
  la tradición mitológica del sistema). Formación base: UFV Viçosa, Zootecnia
  ZOT catálogo 2025 (pensum capturado del catálogo: 3.990 h, 10 períodos).
- Especialidad: **bovinos del trópico** — Bos indicus (**Nelore, Guzerat,
  Gir Leiteiro, Red Sindhi/"Sindi Nordestino"**) + Bos taurus tropical
  (**Jersey**); corazón en **mejoramiento genético** (h², DEP/ACC, índices,
  cruzamientos/heterosis, BLUP, consanguinidad — referencia propia
  `references/mejoramiento-genetico.md` con fórmulas y tablas) y nutrición de
  rumiantes. Carácter: proactivo, **con hambre de documentación** (bitácoras en
  `docs/zootecnista/aprendizajes.md` y `deudas-conocimiento.md`, crear al primer
  uso; caza autónoma con `descarga-libros`), honesto con los números (niveles
  A/B/C como el Agrónomo), de registros y ensayos con testigo.

## 2. Handoff bidireccional con `ingeniero-agronomo` — v1.0.0 → v1.0.1 (09-oct)

- La **fusión de alimentación bovina** es producto de dos: Agrónomo produce el
  pasto, Aristeo define qué come el animal. Reglas de reparto ya en las
  descripciones de AMBOS skills (señal de disparo):
  - pasto como CULTIVO (siembra, suelo, fertilidad) → `ingeniero-agronomo`
  - el ANIMAL (genética, razas, nutrición animal, reproducción) → `zootecnista`
  - dieta completa → ambos, trabajo conjunto.
- `ingeniero-agronomo` sincronizado y revalidado (**v1.0.1**, 7.186 chars,
  SkillRegistry OK). Cambios: regla de derivación en `description` + párrafo de
  dupla en el cuerpo. Nada más tocado.

## 3. Disparo del nuevo skill (para el dispatcher)

- La descripción de `zootecnista` reclama: bovinos, ganado, vacas, toros,
  terneros, razas (Nelore/Gir/Guzerat/Sindi/Jersey/Girolando), genética,
  mejoramiento, DEP, heredabilidad, heterosis, cruzamientos, consanguinidad,
  IATF, reproducción animal, leche, lechería, engorde, destete, hato, ración,
  suplementación, sal mineral, nutrición animal, rumiantes, crecimiento,
  canal/carne.
- Nota: `ingeniero-agronomo` sigue reclamando "bovinos/ovinos/pastoreo" en
  genérico; con la regla de derivación v1.0.1 el reparto queda explícito en
  ambos sentidos.

## 4. Deudas de conocimiento iniciales de Aristeo (previsibles)

- Biblioteca fuerte en pastoreo/lechería a pasto (Voisin, Zietsman) y forrajes
  nordestinos `nordeste_*`, pero **débil en genética animal y razas**: sumarios
  ABCZ vigentes, material de Sindi/Sindi Nordestino (Embrapa Semiárido), Gir
  Leiteiro/Girolando, Jersey tropical, requerimientos (NRC, BR-CORTE), IATF.
  Aristeo las registrará en `docs/zootecnista/deudas-conocimiento.md` y puede
  cazar material público él mismo con `descarga-libros`.

— técnico ZCode, 2026-10-09
