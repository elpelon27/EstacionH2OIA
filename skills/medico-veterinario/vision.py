#!/usr/bin/env python3
"""
============================================================================
vision.py — LOS OJOS DE QUIRÓN, el Médico Veterinario
============================================================================
Herramienta de observación clínica por imagen y video para Hermes.

  Cadena de visión (misma filosofía de la casa, API única primero):
    1. Tier API    → LLMClient task_type="video" (multimodal OpenRouter,
                     gemini-3-pro-preview por defecto; --modelo para cambiar,
                     p.ej. z-ai/glm-4.6v que acepta imagen+video).
    2. Respaldo    → Ollama local qwen2.5vl:3b (--local o caída automática
                     si no hay red/API). Lento en CPU pero offline.

  Protocolo: toda imagen/video se recorre en ORDEN SEMIOLÓGICO fijo
  (Semiología VET 9663) y produce hallazgos por región + diferenciales +
  triage + anamnesis + plan. NUNCA un diagnóstico suelto.

Uso:
  python3 vision.py imagen RUTA [-p "qué mirar"] [--especie bovino]
                                [--modelo z-ai/glm-4.6v] [--local] [--json]
                                [-o salida.md]
  python3 vision.py video RUTA [-p "..."] [--especie bovino] [--fps 0.5]
                               [--max-cuadros 16] [--local] [--json] [-o ...]

Dependencias: python3 (stdlib), ffmpeg/ffprobe en PATH. La parte API
reusa scripts/llm_client.py de hermes-agent (misma key, misma política).
============================================================================
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

HERMES_ROOT = Path("/mnt/ssd_trabajo/hermes-agent")
sys.path.insert(0, str(HERMES_ROOT / "scripts"))

MODELO_LOCAL = "qwen2.5vl:3b"          # respaldo offline (ver /api/tags)
MAX_BYTES_API = 8 * 1024 * 1024        # recorte defensivo por imagen hacia la API
MAX_IMAGENES_LOCAL = 6                 # videos en tier local: muestreo (ctx CPU)

# ---------------------------------------------------------------------------
# PROTOCOLO SEMIOLÓGICO — el corazón del poder de Visión de Quirón
# ---------------------------------------------------------------------------

PROTOCOLO = """Eres Quirón, médico veterinario formado en la UCV (Facultad de
Ciencias Veterinarias, Maracay), ejercicio en el trópico semiárido zuliano.
Recibes {"imagen"| "un video como secuencia de cuadros con timestamp"} de un
animal{especie_hint}. Aplícale EXACTAMENTE este protocolo semiológico, en orden,
y responde en español.

RECORRIDO OBLIGATORIO (lo que no se ve se declara "no evaluable", no se omite):
1. ESCENA: especie, raza aparente, edad/sexo aproximados si se infiere, entorno
   (potrero, establo, corral, traspatio), cuántos animales visibles, calidad de
   la imagen y ángulo.
2. EXAMEN A DISTANCIA: postura (de pie/esternal/lateral), actitud (alerta,
   deprimido, cabeza baja), marcha y coordinación (video: pasos, cojera,
   temblores), aislamiento del grupo, comportamiento anormal.
3. CONDICIÓN CORPORAL: score 1-5 (bovinos/ovinos) o condición (mascotas) según
   musculatura, huesos visibles (costillas, caderas, transversas).
4. CABEZA Y CUELLO: ojos (lagrimeo, opacidad, enoftalmos), orejas (caídas,
   descarga), fosas nasales (descarga: serosa/mucopurulenta/hemorrágica),
   mucosas si son visibles (rosada / pálida / ictérica / cianótica / congestiva),
   salivación, linfonódulos visibles, edema submandibular.
5. TÓRAX Y ABDOMEN: esfuerzo o frecuencia respiratoria aparente, tos, distensión
   abdominal (flanco izq. = rumen, der. = abomaso/útero), flancos hundidos
   (ayuno), arqueamiento dorsal.
6. PIEL Y APÉNDICES: pelaje (opaco, erizado, alopecia), ectoparásitos visibles
   (garrapatas, moscas, larvas de miasis), heridas, abscesos, dermatitis,
   pezuñas/unciones (cojera, sobrecrecimiento), ubre (edema, heridas en pezones,
   secreción visible).
7. REGIONES ESPECIALES: ombligo en crías (onfaloflebitis), periné/cola (manchas
   de diarrea, descarga vaginal, prolapso), genitales.
8. EL ENTORNO COMO PACIENTE: estado del pasto, agua, sombra, lodo, heces visibles
   (consistencia, color), camas, comederos.
9. NO EVALUABLE: lista explícita de regiones/funciones que esta imagen no
   permite valorar y qué se necesitaría (foto de mucosas, video de marcha,
   auscultación, laboratorio).

REGLAS DE HONESTIDAD (niveles de la casa):
- Describe SOLO lo visible. Separa siempre "VEO X" de "SOSPECHO Y".
- Marca cada afirmación: (A) dato objetivo visible en la imagen; (B) principio
  clínico aplicado con juicio [pensum: VET <asignatura>]; (C) hipótesis que
  exige confirmación (examen/laboratorio/anamnesis).
- NUNCA des dosis de fármacos; si mencionas un tratamiento, remítelo a
  "confirmar con formulario / médico presencial".
- Si ves signos compatibles con ZOONOSIS (rabia, carbón, lesiones sospechosas
  en animal que mordió) o riesgo para personas, decláralo PRIMERO y en rojo.

FORMATO DE SALIDA (markdown, sin adornos):
## Datos
especie/raza/edad-sexo aparente, entorno, nº animales.
## Hallazgos (por región, solo lo observado)
- ...
## Triage
ROJO (actuar hoy) / AMARILLO (estudiar esta semana) / VERDE (preventivo) —
con el fundamento en una línea. Sé explícito del nivel aunque sea verde.
## Diagnósticos diferenciales
2-4, cada uno con "apoya:" y "descuenta:" en una línea.
## Preguntas de anamnesis
Máximo 5, las que más cambien el rumbo.
## Plan inmediato en campo
Qué hacer HOY con lo que hay (sin dosis): separar, hidratar, sombra, no mover,
recoger muestra, llamar al MV presencial...
## No evaluable / siguiente toma
Qué foto o video pedir (encuadre, momento, región).
"""

ESPECIES_HINT = {
    "bovino": " bovino (hato del trópico: Bos indicus, cruces, Jersey)",
    "ovino": " ovino (línea de la casa: corderos BARF/lio)",
    "caprino": " caprino",
    "porcino": " porcino",
    "ave": " aviar (gallinas, aves de traspatio o producción)",
    "equino": " equino",
    "can": " canino",
    "felino": " felino",
    "mixto": "",
}


# ---------------------------------------------------------------------------
# Utilidades de media
# ---------------------------------------------------------------------------

def _mime_de(ruta: Path) -> str:
    m, _ = mimetypes.guess_type(str(ruta))
    if m in ("image/jpeg", "image/png", "image/webp", "image/gif"):
        return m
    raise SystemExit(f"[vision] formato no soportado como imagen: {m} ({ruta})")


def _b64(ruta: Path, limite: int = MAX_BYTES_API) -> str:
    data = ruta.read_bytes()
    return base64.b64encode(data).decode()


def _duracion_video(ruta: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(ruta)],
        capture_output=True, text=True, check=True).stdout
    return float(json.loads(out)["format"]["duration"])


def extraer_cuadros(ruta: Path, trabajo: Path, max_cuadros: int) -> list[dict]:
    """Muestreo adaptativo (patrón claude-watch): reparte los cuadros en toda
    la duración para no perderse el final del video."""
    dur = _duracion_video(ruta)
    intervalo = max(dur / max_cuadros, 0.5)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(ruta),
         "-vf", f"fps=1/{intervalo:.2f},scale='min(1024,iw)':-2",
         "-q:v", "4", str(trabajo / "cuadro_%03d.jpg")],
        check=True, capture_output=True)
    cuadros = []
    for f in sorted(trabajo.glob("cuadro_*.jpg")):
        t = (int(f.stem.split("_")[1]) - 1) * intervalo
        cuadros.append({"ruta": f, "t": t})
    return cuadros


# ---------------------------------------------------------------------------
# Tier 1 — API vía LLMClient (misma key y política de la casa)
# ---------------------------------------------------------------------------

def analizar_api(content: list[dict], modelo: str | None) -> dict:
    from llm_client import LLMClient  # scripts/llm_client.py de hermes-agent
    cliente = LLMClient()
    if modelo:  # el tier video es el único video_ok; se le parchea el modelo
        for tier in cliente.tier_chain:
            if tier.get("video_ok"):
                tier["model"] = modelo
    resp = cliente.complete([{"role": "user", "content": content}],
                            task_type="video", temperature=0.2, max_tokens=4096)
    if resp.get("error"):
        raise RuntimeError(f"LLM visión (API) falló: {resp['error']}")
    return {"texto": resp["content"].strip(),
            "tier": f"api:{resp.get('model', 'video-default')}"}


# ---------------------------------------------------------------------------
# Tier 2 — Ollama local qwen2.5vl (offline, lento en CPU)
# ---------------------------------------------------------------------------

def analizar_local(content: list[dict]) -> dict:
    texto = next((p["text"] for p in content if p["type"] == "text"), "")
    imagenes = [p["image_url"]["url"].split(",", 1)[1]
                for p in content if p["type"] == "image_url"]
    if len(imagenes) > MAX_IMAGENES_LOCAL:  # muestreo uniforme (ctx limitado)
        paso = len(imagenes) / MAX_IMAGENES_LOCAL
        imagenes = [imagenes[int(i * paso)]
                    for i in range(MAX_IMAGENES_LOCAL)]
        texto += (f"\n\n[Nota: se muestran {len(imagenes)} cuadros "
                  "representativos del video.]")
    payload = json.dumps({
        "model": MODELO_LOCAL, "stream": False,
        "messages": [{"role": "user",
                      "content": texto,
                      "images": imagenes}],
        "options": {"temperature": 0.2, "num_predict": 2048,
                    "num_ctx": 16384},
    }).encode()
    req = urllib.request.Request("http://localhost:11434/api/chat",
                                 data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        data = json.loads(r.read())
    return {"texto": data["message"]["content"].strip(),
            "tier": f"local:{MODELO_LOCAL}"}


# ---------------------------------------------------------------------------
# Comando principal
# ---------------------------------------------------------------------------

def analizar(tipo: str, ruta: Path, pregunta: str, especie: str,
             modelo: str | None, forzar_local: bool, max_cuadros: int) -> dict:
    if not ruta.exists():
        raise SystemExit(f"[vision] no existe: {ruta}")
    hint = ESPECIES_HINT.get(especie.lower(), "")
    protocolo = PROTOCOLO.replace('{"imagen"| "un video como secuencia de cuadros con timestamp"}',
                                  "una FOTO" if tipo == "imagen" else
                                  "un VIDEO (cuadros extraídos en orden cronológico, con su timestamp)")
    prompt = f"{protocolo}\n\nAtención especial pedida por el remitente: {pregunta or 'observación general'}"

    content: list[dict] = [{"type": "text", "text": prompt}]
    if tipo == "imagen":
        mime = _mime_de(ruta)
        content.append({"type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{_b64(ruta)}"}})
    else:
        with tempfile.TemporaryDirectory(prefix="vision_quiron_") as tmp:
            cuadros = extraer_cuadros(ruta, Path(tmp), max_cuadros)
            if not cuadros:
                raise SystemExit("[vision] ffmpeg no extrajo cuadros (¿video válido?)")
            for c in cuadros:
                content.append({"type": "text",
                                "text": f"\nFRAME t={c['t']:.0f}s"})
                content.append({"type": "image_url",
                                "image_url": {"url": "data:image/jpeg;base64,"
                                   + base64.b64encode(c["ruta"].read_bytes()).decode()}})

    resultado: dict | None = None
    errores: list[str] = []
    if not forzar_local:
        for intento in (1, 2):  # 2 intentos: el DNS del servidor es intermitente
            try:
                resultado = analizar_api(content, modelo)
                break
            except Exception as e:  # noqa: BLE001 — degradar a local es el diseño
                errores.append(f"api(intent {intento}): {e}")
                if intento == 1:
                    import time as _t
                    _t.sleep(6)
    if resultado is None:
        try:
            resultado = analizar_local(content)
        except Exception as e:  # noqa: BLE001
            errores.append(f"local: {e}")
            raise SystemExit("[vision] ambos tiers fallaron:\n  "
                             + "\n  ".join(errores))
    if errores:
        resultado["degradado_por"] = errores
    resultado["ruta"] = str(ruta)
    resultado["tipo"] = tipo
    resultado["especie"] = especie
    return resultado


def main() -> None:
    ap = argparse.ArgumentParser(description="Los ojos de Quirón — observación "
                                             "clínica veterinaria por imagen/video")
    ap.add_argument("tipo", choices=["imagen", "video"])
    ap.add_argument("ruta", type=Path)
    ap.add_argument("-p", "--pregunta", default="", help="qué mirar / atención especial")
    ap.add_argument("--especie", default="mixto", help="bovino|ovino|caprino|porcino|ave|equino|can|felino|mixto")
    ap.add_argument("--modelo", default=None, help="modelo multimodal OpenRouter (p.ej. z-ai/glm-4.6v)")
    ap.add_argument("--local", action="store_true", help="forzar tier Ollama local (offline)")
    ap.add_argument("--max-cuadros", type=int, default=16)
    ap.add_argument("--json", action="store_true", help="salida JSON (texto + metadatos)")
    ap.add_argument("-o", "--salida", type=Path, default=None, help="guardar informe en .md")
    a = ap.parse_args()

    r = analizar(a.tipo, a.ruta, a.pregunta, a.especie, a.modelo, a.local, a.max_cuadros)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print(r["texto"])
        print(f"\n---\n[tier: {r['tier']}]" +
              (f" · degradado: {'; '.join(r['degradado_por'])}" if r.get("degradado_por") else ""),
              file=sys.stderr)
    if a.salida:
        a.salida.parent.mkdir(parents=True, exist_ok=True)
        a.salida.write_text(f"# Visión Quirón — {a.ruta.name} ({a.tipo}, {a.especie})\n\n"
                            f"{r['texto']}\n\n---\ntier: {r['tier']}\n", encoding="utf-8")


if __name__ == "__main__":
    main()
