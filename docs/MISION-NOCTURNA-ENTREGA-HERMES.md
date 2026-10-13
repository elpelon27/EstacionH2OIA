# ENTREGA FORMAL — SISTEMA DE INVESTIGACIÓN NOCTURNA DE LOS 4 HERMANOS
## Documento de traspaso a HERMES AGENT (dueño y ejecutor desde el 2026-10-13)

**Entregan:** el Líder (decisión) + ZCode (diseño, código, migración, validación).
**Recibe:** HERMES AGENT. **Rol restante de ZCode:** GUARDIÁN externo (validación
diaria, reparaciones, evolución del diseño). "Dos ojos ven mejor que uno."

---

## 1. ANTECEDENTES (por qué existe esto)

- Los 4 perfiles-hermano (Empédocles IQ, Tripólemo Agronomía, Aristeo Zootecnia,
  Quirón Medicina Veterinaria) necesitan **fundamentos bibliográficos citables**
  de sus pensum (regla anti-invento: constante sin fuente no existe).
- Las misiones nacieron prompt-driven: el Líder pegaba un prompt cada noche —
  no escalaba y la secuencia se perdía.
- **10-oct:** ZCode instala el sistema con qwen local → **falla probada**: un
  modelo de un turno no investiga (pidió el tema conversacionalmente).
- **11-oct:** ejecutor pasa a API OpenRouter (tier research de tu llm_client).
  Primera noche real 4/4 con sustancia (Gemini+plugin web). Costo ~$0.15.
- **12-oct (hoy):** rectificación del Líder — (a) preferencia por flash
  **ABIERTOS** (GLM/DeepSeek/Qwen) sobre cerrados; (b) **entrega de la
  propiedad ejecutiva a Hermes** con cronjob propio desde el 13-oct.

## 2. ARQUITECTURA (qué es cada pieza y dónde vive)

```
CRONJOB DEL HOST (Lun-Vie 22:00 · Sáb 01:00 · Dom 21:00)
  └─ scripts/misiones/noche_hermes.py        ← EJECUTOR AUTÓNOMO DE HERMES
       ├─ 1. Telegram: pregunta aborto (10 min; sin respuesta arranca)
       ├─ 2. Turno: estado_misiones.json (cola rotante + desborde primero)
       ├─ 3. Por hermano: mision_nocturna.py --ejecutar <id>
       │      ├─ Prompt autónomo autocontenido (mapa + lote exacto + fuentes
       │      │  de la casa + formato de entrega obligatorio)
       │      ├─ GROUNDING: buscar_web.py — APIs científicas
       │      │  OpenAlex → Crossref (refs con DOI/PDF verificables por
       │      │  construcción; gratis y estables). Último recurso DDG-lite.
       │      │  (Lección 12-oct: los buscadores HTML sirven basura sin JS
       │      │  y DDG rate-limitea — las APIs son el grounding correcto
       │      │  para una misión bibliográfica.)
       │      └─ llm_client.py task_type="research":
       │           glm-5.3-flash → qwen3.8-flash → deepseek-v4-flash
       │           → (último recurso cerrado) gemini-3-flash-preview+web
       ├─ 4. --registrar <id> [--fallo]: marca mapa [x], HISTORIAL-TRABAJO.md,
       │      hechos.json, telegram ✓/✗. Fallo => hermano PRIMERO mañana
       └─ 5. --cierre: rota la cola + resumen Telegram
GUARDIÁN ZCode (08:00, sesión ZCode): valida respaldo real de la noche,
descarga PDFs de las listas, ingesta a Qdrant, repara, reporta.
```

- **Fuente de verdad del turno:** `scripts/misiones/estado_misiones.json`
  (cola, pendiente_desborde, reintentos, historial). Bitácora append-only:
  `scripts/misiones/bitacora-nocturna.log`.
- **Cronogramas por hermano:** sus mapas vivos (`harvest-bibliografica/
  mapa-bibliografico-*.md` de cada workspace; 4 creados, lotes = planes .md).
- **Modelos:** variables en `config/.env` (OPENROUTER_MODEL_RESEARCH*).
  Costo semanal estimado 28 jornadas: ~$2.4-4.7 (flash abiertos, carga media).

## 3. RUTINA DIARIA (así se trabaja cada noche)

1. **Telegram pregunta** (si el Líder responde abort → noche intacta, sale limpio).
2. **Orden de la cola:** desbordados/fallidos primero, luego rotación (el que
   abrió pasa al final — nadie abre ni cierra siempre). 4 hermanos por noche.
3. **Cada hermano:** 1 lote de su mapa (el primero sin [x]). Entrega obligatoria:
   candidatos por asignatura (2-4 refs con URL viva de fuentes de la casa),
   apuntes de estudio con sección "Resultados cuantitativos que debo poder
   citar", lista de PDFs a descargar. Ventana hasta 06:00.
4. **Fallo:** reintenta 1 vez; si persiste, registra fallo y el hermano queda
   primero mañana — **el turno nunca se salta a nadie**.
5. **Cierre:** resumen Telegram + rotación.

## 4. PLANIFICACIÓN DE INVESTIGACIÓN — ESTADO Y ORDEN (al 12-oct)

| Hermano | Misión (workspace/misiones/) | Mapa | Próximo | Total lotes |
|---|---|---|---|---|
| Empédocles | INGENIERO-QUIMICO/2026-10-10-mision-bibliografica-empedocles.md | mapa-...-pensum-iq.md | L2 (transferencia+SECADO/LIOFILIZACIÓN ⭐ casa) | 8 (L6 agua ⭐) |
| Tripólemo | INGENIERO-AGRONOMO/2026-10-09-mision-nutricion-bibliografica-pensum.md | mapa-...-pensum.md | L2 (microbiología aplicada ⭐) | 8 |
| Aristeo | ZOOTECNISTA/2026-10-09-mision-investigacion-nocturna-pensum-zot.md | mapa-...-pensum-zot.md | L3 (nutrición de rumiantes ⭐) | 9 (L1 ✓ 11-oct, L2 ✓ 12-oct*) |
| Quirón | MEDICO-VETERINARIO/2026-10-09-mision-bibliografia-veterinaria.md | mapa-...-veterinario.md | L2 (agentes tropicales ⭐) | 8+bonus |

*L1 de Tripólemo/Quirón/Empédocles ✓ noche 11-oct (gemini); L1 Aristeo quedó [x]
por decisión del Líder (noche qwen, sin investigación real — recuperar si la
validación lo pide). ⭐ = lotes prioritarios de la casa (L2 Empédocles = LIOFILIZACIÓN).

**Orden de esta semana (cola actual):** zootecnista → medico-veterinario →
ingeniero-quimico → ingeniero-agronomo (rota cada noche).

## 5. REGLAS INVARIABLES (ley de oro del sistema)

1. Un estado, un dueño: `estado_misiones.json` manda; no marcar lotes a mano.
2. Nadie se salta: fallo → primero mañana. Desborde → primero mañana.
3. Nada falla en silencio: bitácora + hechos + Telegram en cada paso.
4. Regla anti-invento sobre todo: solo citas con URL de la búsqueda real.
5. Flash abiertos primero; cerrados solo último recurso.
6. ZCode repara/diseña/guía; Hermes ejecuta y registra; el Líder decide.

## 6. MANTENIMIENTO (para el guardián)

- Cambiar prioridad de un lote → editar su mapa (columna Dominio/orden).
- Cambiar orden de hermanos → `cola` en estado_misiones.json.
- Cambiar modelo research → OPENROUTER_MODEL_RESEARCH* en config/.env.
- Diagnóstico: `logs/mision_nocturna.log`, `scripts/misiones/bitacora-nocturna.log`,
  `cron_with_memory.sh` registra cada ejecución en hermes_memory.db.
- ⚠️ Créditos OpenRouter ~$17 al 12-oct: recargar.

**Posesión efectiva: 2026-10-13 (martes) 22:00. Guard de fecha incluido en
noche_hermes.py; la noche del 12-oct la cierra ZCode como transición.**
