# Referencia — Protocolo de Visión de Quirón (imágenes y videos)

> El "poder avanzado" no es ver fotos: es recorrerlas con disciplina
> semiológica y convertirlas en decisión. Este documento es el manual de
> campo del ojo. El protocolo está INTEGRADO en `vision.py` (no hay que
> recordarlo: la herramienta lo aplica); esto es para verificar, afinar y
> consultar checklist.

## 1. La cadena de visión (arquitectura)

| Tier | Qué | Cuándo |
|---|---|---|
| 1. API | LLMClient `task_type="video"` → gemini-3.1-pro-preview vía OpenRouter (key única de la casa) | SIEMPRE primero (rápido y potente) |
| 1b. API alterno | `--modelo z-ai/glm-4.6v` (acepta imagen+video nativo) | si el Líder pide GLM o el default falle |
| 2. Local | Ollama `qwen2.5vl:3b` (3,2 GB, CPU) | sin internet o `--local` — LENTO (minutos/imágenes), respaldo |

- Videos: ffmpeg extrae hasta `--max-cuadros` (default 16) repartidos en toda
  la duración (patrón claude-watch), escala a ≤1024px, JPEG q4, con timestamp.
- Imágenes: acepta jpeg/png/webp/gif; si pesa >8 MB re-escalar antes.
- `--json` para salida estructurada (texto + tier + degradado_por).
- El informe guarda con `-o` → usar `docs/veterinario/casos/AAA-MM-DD-caso.md`.

## 2. El recorrido semiológico (orden FIJO)

1. **Escena**: especie, raza aparente, edad/sexo si se infiere, entorno
   (potrero/corral/galpón/traspatio), nº de animales, calidad y ángulo de la
   toma. Una foto que no permite identificar especie se declara.
2. **Examen a distancia**: postura (de pie/esternal/lateral), actitud
   (alerta/deprimido/cabeza baja), marcha y coordinación (video: cojera,
   temblor, arrastre), aislamiento del grupo, comportamiento anormal.
3. **Condición corporal**: bovinos/ovinos ECC 1-5 (costillas, tuberosidades
   coxales/isquiáticas, transversas); mascotas: BCS 1-9 → reportar equivalente.
4. **Cabeza y cuello**: ojos (lagrimeo, opacidad, enoftalmos), orejas (caídas,
   descarga), fosas nasales (serosa/mucopurulenta/hemorrágica), mucosas si son
   visibles (rosada/pálida/ictérica/cianótica/congestiva), salivación,
   linfonódulos, edema submandibular (¡fasciola/botriomicosis!).
5. **Tórax y abdomen**: esfuerzo/frecuencia respiratoria aparente, tos,
   distensión de flancos (izq=rumen, der=abomaso/útero), flancos hundidos
   (ayuno), arqueamiento dorsal (dolor).
6. **Piel y apéndices**: pelaje (opaco/erizado/alopecia), ectoparásitos
   (garrapatas — zonas predilectas: periné, ubre, axilas, orejas—, moscas,
   larvas de miasis), heridas, abscesos, dermatitis, pezuñas (cojera,
   sobrecrecimiento, undidades), ubre (edema, heridas en pezones).
7. **Regiones especiales**: ombligo en crías (onfaloflebitis), periné/cola
   (manchas de diarrea, descarga vaginal, prolapso), genitales.
8. **Entorno como paciente**: pasto (cantidad/estado), agua, sombra, lodo,
   heces visibles (consistencia/color), camas, comederos.
9. **No evaluable**: lista explícita + qué tomaría (foto de mucosas, video de
   marcha, auscultación, laboratorio).

**Cierre obligado**: Hallazgos → Diferenciales (apoya/descuenta) → Triage
(ROJO/AMARILLO/VERDE + fundamento) → Anamnesis (máx 5) → Plan inmediato (sin
dosis) → Siguiente toma.

## 3. Triage — qué significa cada color

- **ROJO (actuar hoy)**: animal caído que no se levanta, dificultad
  respiratoria severa, sangrado activo, prolapso, distensión abdominal aguda
  con dolor, sospecha de zoonosis (rabia — salivación + agresividad o
  parálisis; carbón — edema crepitante), parto prolongado, diarrea
  hemorrágica en brote. → plan inmediato + qué hacer mientras llega ayuda +
  proteger personas.
- **AMARILLO (estudiar esta semana)**: pérdida de condición progresiva,
  cojera leve-moderada, descargas crónicas, repeats de celo, carga visible de
  garrapatas sin anemia aparente, diarrea sin decaimiento. → anamnesis +
  muestras + monitoreo con fecha.
- **VERDE (preventivo)**: hallazgos dentro de lo normal del trópico o
  ambiente mejorable (sombra, agua, mineral). → calendario sanitario y
  registro.

## 4. Checklist por especie (región → qué buscar primero en el trópico)

**Bovinos (hato de la casa)**: garrapata *Rhipicephalus microplus*
(anaplasmosis/babesiosis → mucosas pálidas = AMARILLO→ROJO), mosca de los
cuernos, mastitis (ubre caliente/desequilibrada), cojeras (unciones, DD),
timpanismo (flanco izq. agudo = ROJO), abortos (brucelosis — zoonosis:
aviso), carbón sintomático (edema crepitante = ROJO), rabia paralítica
(muerte reciente de murciélagos/mordeduras = ROJO + personas).

**Ovinos (línea BARF de la casa)**: verminosis (submandibular edema =
"botella", pálidos, diarrea), sarna (alopecia costrosa), miíasis (larvas en
heridas/ombligo — verano), pododermatitis (lodo), enterotoxemia (muerte
súbita en engorde — preguntar cambio de dieta → con Aristeo).

**Caprinos**: igual ovinos + linfadenitis caseosa (absesos de linfonódulos),
neumonía por amontonamiento/lluvia.

**Aves de traspatio/producción**: postura caída (primer signo de TODO),
cresta/carioca pálida (anemia — ácaros), rales/estertores (viruela/newcastle
— zoonosis newcastle leve), diarrea blanca (pullorosis en crías), parásitos
externos, gusto y cama: ambiental primero.

**Porcinos**: diarrea (colibacilosis, disentería), tos (neumonía enzoótica),
sarna (prurito intenso, piel costrosa), erisipela (rhomboides cutáneos),
fiebre + postración en zona de montes (PESTE PORCINA CLÁSICA — reportable:
ROJO sanitario).

**Equinos**: cojeras (primera sospecha siempre: forúnculo/laminiris —
postura típica), aba (moquillo — linfonódulos submandibulares), colicos
(rodar, mirar el flanco — ROJO), anemia por garrapatas/tábanos, myiasis de
heridas.

**Caninos/Felinos (traspatio)**: heridas de pelea (abscesos), sarna
sarcoptes (orejas/codos, zoonosis leve), garrapatas (ehrlichiosis →
plaquetas: sangrados), TVT (tumor venereo — lesión cauliflower), rabia
(si hay mordedura de humano: ROJO sanitario inmediato).

## 5. Guía de TOMA (qué pedirle al Líder cuando la imagen no alcanza)

| Para evaluar | Pedir |
|---|---|
| Mucosas | foto del ojo (conjuntiva) o encía, con luz natural, sin flash directo |
| Condición corporal | foto desde atrás y de lado, animal en pie en la manga |
| Garrapatas | foto macro del periné/base de cola/axila/ubre |
| Marcha | video de 10-20 s caminando HACIA la cámara y alejándose |
| Respiración | video de costado, flanco descubierto, 15 s en reposo |
| Rumia | video de flanco izquierdo 30 s (ondas ruminales) |
| Heces | foto del montón con objeto de escala; del periné manchado |
| Ubre | foto de los cuatro cuartos, cámara a la altura |
| Piel/lesión | foto panorámica + macro con escala (moneda/mano) |

Reglas de toma: luz natural, enfocar la región, un animal por foto cuando sea
posible, sin filtros. Video horizontal caminando, no vertical rápido.

## 6. Límites de la Visión (decirlo sin rodeos)

- NO sustituye: palpación, auscultación, termometría (¡pedir temperatura
  siempre que se pueda!), examen rectal, ecografía, necropsia, laboratorio.
- El video compensa un poco (marcha, ritmo respiratorio) — pero la ausencia
  de signos en video no es ausencia de enfermedad.
- Fotografías de MUCOSAS pálidas son señal seria pero engañosa con mala luz:
  pedir re-toma con referencia antes de gritar anemia.
- Dosis: NUNCA en el informe de Visión. Principios activos candidatos +
  "confirmar con formulario/MV presencial". Periodo de retirada SIEMPRE en
  producción.
- Enfermedades reportables (rabia, brucelosis, TB, PPC, ISA): sospecha →
  orientar al laboratorio oficial; el informe lo dice primero.
