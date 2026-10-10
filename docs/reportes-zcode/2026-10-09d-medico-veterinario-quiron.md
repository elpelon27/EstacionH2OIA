# REPORTE TÉCNICO ZCode — 2026-10-09 (d) — Skill `medico-veterinario` (Quirón)

## 1. Skill `medico-veterinario` — CREADO E INSTALADO (09-oct)

- `skills/medico-veterinario/` (SKILL.md + **vision.py** +
  references/pensum-ucv-vet.md + references/protocolo-vision.md +
  references/recursos-servidor.md), **v1.0.0**, validado con `SkillRegistry`
  (**16 skills cargados**, la nueva sin errores). Proyecto fuente
  autocontenido y AISLADO en `~/.zcode/workspace/default/MEDICO-VETERINARIO/`
  (PERFIL, MAPA-PENSUM-UCV-VET, pensum/ con PDF original del Líder, skill/,
  README, INSTALACION).
- **Perfil: Quirón, el Médico Veterinario de la casa** (nombre griego pedido
  por el Líder; elegido por ZCode entre Quirón/Argos Panoptes/Asclepio/Higía —
  Quirón el centauro sabio, maestro de Asclepio y médico de héroes y bestias:
  si el Líder prefiere otro, es un cambio de texto). Formación base: UCV,
  Facultad de Ciencias Veterinarias (Maracay), 5 años / 143 U/C, pensum
  transcrito del PDF entregado.
- **Poder de la VISIÓN** (lo que lo distingue): `vision.py` analiza FOTOS y
  VIDEOS de animales con **protocolo semiológico integrado** (orden fijo de
  regiones: escena → distancia → ECC → cabeza → tórax/abdomen → piel →
  especiales → entorno → no-evaluable; cierre con diferenciales, triage
  ROJO/AMARILLO/VERDE, anamnesis, plan SIN dosis, zoonosis primero). Cadena:
  **tier API multimodal** vía `scripts/llm_client.py` task_type="video"
  (gemini-3.1-pro-preview, `OPENROUTER_MODEL_VIDEO`, misma key única de la
  casa; `--modelo z-ai/glm-4.6v` disponible) → **respaldo local Ollama
  `qwen2.5vl:3b`** (instalado hoy, 3,2 GB; CPU: lento, solo offline) →
  videos por ffmpeg con cuadros equidistantes con timestamp (patrón
  claude-watch). Retry ×2 anti-DNS-intermitente en el tier API.
- **Validación E2E (09-oct)**: foto real de hato Nelore (Wikimedia) → informe
  semiológico completo y correcto (~1 min); **video de 11,8 s** (3 escenas de
  ganado) → lectura cronológica t=0-2s/t=6-11s, ECC por animal fundado, triage
  VERDE, diferenciales tropicales (parasitosis subclínica, deficiencia P/Cu/Zn)
  — el 1er intento falló por el DNS intermitente del servidor (ConnectError)
  y se resolvió con retry; tier local probado en imagen (funciona, ~4 min) y
  video (fix aplicado: muestreo de 6 cuadros + num_ctx 16384 porque 16 cuadros
  exceden el contexto por defecto de Ollama).

## 2. Handoff bidireccional con los hermanos — la trilogía completa

- `zootecnista` **v1.0.0 → v1.0.1**: regla de derivación a Quirón en
  description (animal ENFERMO/salud de hato → medico-veterinario), párrafo de
  trío en el cuerpo (anemia por déficit vs verminosis → Quirón firma con
  Aristeo), y la antigua "deriva a mérito veterinario" ahora apunta a Quirón.
- `ingeniero-agronomo` **v1.0.3 → v1.0.4**: misma regla en description +
  párrafo de trío (intoxicaciones por plantas/pastos y potrero como factor
  epidemiológico → Quirón con Tripólemo).
- Ambas sincronizadas (proyecto ↔ servidor) y revalidadas con SkillRegistry.

## 3. Disparo del nuevo skill (para el dispatcher)

- La description reclama: animal enfermo, enfermedad, salud animal, herida,
  lesión, cojera, diarrea, aborto, vaca caída, inapetencia, flaco, garrapata,
  parásito, miasis, sarna, mastitis, fiebre, anemia, mucosas, tos, neumonía,
  vacuna, calendario sanitario, desparasitación, cuarentena, zoonosis, rabia,
  brucelosis, TB, carbón, intoxicación, parto, retención de placenta,
  bienestar animal, higiene de alimentos, "mira esta foto/video", "¿qué
  tiene?".
- Ojo: `zootecnista` y `ingeniero-agronomo` siguen reclamando "bovinos" en
  genérico; las reglas de derivación en las TRES descriptions dejan el
  reparto explícito (sano-productivo → Aristeo; cultivo → Tripólemo;
  enfermo/salud → Quirón).

## 4. Deudas de conocimiento iniciales de Quirón (previsibles)

- Biblioteca fuerte en forrajes/pastoreo/suelos pero **sin clínica
  veterinaria**: medicina interna bovina tropical, parasitología clínica
  (garraticidas/resistencia), formularios de dosis, calendarios sanitarios
  venezolanos, ovinos, aves de traspatio, porcinos, mastitis, reproducción
  patológica, atlas de lesiones. Las registrará en
  `docs/veterinario/deudas-conocimiento.md` (crear al primer uso, junto a
  `aprendizajes.md` y `casos/`) y puede cazar material con `descarga-libros`.

## 5. Nota operativa

- El 400 del tier local en el primer test de video quedó explicado y
  corregido (tokens de visión > num_ctx 4096 por defecto): ahora muestrea
  máx. 6 cuadros y usa num_ctx 16384. `vision.py` usa `ffmpeg` (presente,
  6.1.1) y NO toca nada fuera de su skill + servicios de solo lectura.
- Rollback: borrar `skills/medico-veterinario/`, revertir versiones de los
  hermanos; `ollama rm qwen2.5vl:3b` libera 3,2 GB si se desea.

— técnico ZCode, 2026-10-09
