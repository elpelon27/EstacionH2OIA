#!/usr/bin/env python3
"""mision_nocturna.py — Investigación nocturna desatendida de los 4 hermanos
(Empédocles, Tripólemo, Aristeo, Quirón).

Cada noche (Lun-Vie 22:00 / Sáb 01:00 / Dom 21:00, vía crontab del host):
  1. GUARD DE CLI: si hay código corriendo en el CLI de ZCode (actividad
     reciente en su workspace), queda pendiente: poll cada 2 min, y al
     terminar VUELVE A PREGUNTAR antes de arrancar.
  2. CONSULTA TELEGRAM: pregunta si hay interrupción; sin respuesta en
     MIN_RESPUESTA_MIN arranca automáticamente (ley de primer contacto sin
     cold-start; nunca bloquea la noche esperando al humano).
  3. COLA: ejecuta un lote de misión por hermano, en orden de cola rotante.
     Éxito -> marca lote, historial, telegram, hermano pasa al final.
     Fallo -> reintenta al MISMO hermano (máx. REINTENTOS_MAX); el turno no
     avanza hasta completar (nadie se salta).
     Ventana cierra 06:00 -> el hermano que no alcanzó queda PRIMERO la
     noche siguiente (pendiente_desborde).
  4. CIERRE: rota la cola, bitácora append-only + telegram consolidado.

Estado maestro: estado_misiones.json (única fuente de verdad del turno).
Ejecutor: prometeo_nocturno (qwen local, sin costo de API).
Validación matutina: automatización ZCode 08:00 ("dos ojos ven mejor").

Uso:
  python3 mision_nocturna.py [--dry-run] [--force]
  --dry-run: simula la noche completa (no ejecuta modelos, no marca lotes).
  --force:  ignora la validación de día/hora de arranque (para pruebas).
"""
import argparse
import datetime as dt
import fcntl
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

BASE = "/mnt/ssd_trabajo/hermes-agent/scripts/misiones"
ESTADO = os.environ.get("MISION_ESTADO", os.path.join(BASE, "estado_misiones.json"))
DRY_GLOBAL = "--dry-run" in sys.argv
BITACORA = os.path.join(BASE, "bitacora-nocturna.log")
LOCK = os.path.join(BASE, ".mision_nocturna.lock")
ENV = "/mnt/ssd_trabajo/hermes-agent/config/.env"
WORKSPACE_ZCODE = "/home/skynet/.zcode/workspace"
INVOCAR = "/home/skynet/prometeo_nocturno/invocar_nocturno.py"
HECHOS = "/mnt/ssd_trabajo/hermes-agent/docs/memoria/hechos.json"

DEADLINE_HORA = 6          # la ventana nocturna cierra a las 06:00
MIN_RESPUESTA_MIN = 10     # ventana de respuesta por telegram
GUARD_POLL_SEG = 120       # poll del guard de CLI
GUARD_ACTIVIDAD_MIN = 10   # actividad reciente = archivos tocados hace <10 min
REINTENTOS_MAX = 2         # reintentos del mismo hermano por noche
LOTE_TIMEOUT_SEG = 90 * 60 # máximo por lote (35B en CPU es lento)

ABORT_PATRON = re.compile(r"\b(abort|stop|parar|espera|alto|no arranc|pause|pausa)\b", re.I)
GO_PATRON = re.compile(r"\b(arranca|si|sí|ok|dale|go|adelante)\b", re.I)


def ahora() -> dt.datetime:
    return dt.datetime.now()


def log(linea: str) -> None:
    ts = ahora().isoformat(timespec="seconds")
    with open(BITACORA, "a") as f:
        f.write(f"{ts} {linea}\n")


# ---------------------------------------------------------------- telegram --
def _env_telegram() -> tuple[str, str]:
    token = chat = None
    with open(ENV) as f:
        for line in f:
            if line.startswith("TELEGRAM_BOT_TOKEN_HERMES="):
                token = line.split("=", 1)[1].strip()
            elif line.startswith("TELEGRAM_CHAT_ID_HERMES="):
                chat = line.split("=", 1)[1].strip()
    if not token or not chat:
        raise RuntimeError("TELEGRAM_*_HERMES no encontrado en config/.env")
    return token, chat


def tg_enviar(texto: str) -> None:
    try:
        token, chat = _env_telegram()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=json.dumps({"chat_id": chat, "text": texto}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
    except Exception as e:
        log(f"WARN telegram enviar falló: {e} (la noche continúa — nada bloquea)")


def tg_preguntar_abort(texto: str, minutos: int) -> bool:
    """Pregunta por telegram; True = ABORTAR (el humano respondió que sí)."""
    try:
        token, _ = _env_telegram()
        tg_enviar(texto)
        offset_file = os.path.join(BASE, ".tg_offset")
        offset = 0
        if os.path.exists(offset_file):
            offset = int(open(offset_file).read().strip() or 0)
        limite = ahora() + dt.timedelta(minutes=minutos)
        while ahora() < limite:
            url = (f"https://api.telegram.org/bot{token}/getUpdates"
                   f"?timeout=30&offset={offset + 1}&allowed_updates=%5B%22message%22%5D")
            try:
                with urllib.request.urlopen(urllib.request.Request(url), timeout=40) as r:
                    ups = json.loads(r.read()).get("result", [])
            except Exception:
                continue
            for u in ups:
                offset = max(offset, u["update_id"])
                msg = (u.get("message") or {}).get("text", "") or ""
                if ABORT_PATRON.search(msg):
                    with open(offset_file, "w") as f:
                        f.write(str(offset))
                    return True
                if GO_PATRON.search(msg):
                    with open(offset_file, "w") as f:
                        f.write(str(offset))
                    return False  # confirmación explícita: arranca ya
            time.sleep(5)
        with open(offset_file, "w") as f:
            f.write(str(offset))
    except Exception as e:
        log(f"WARN telegram pregunta falló: {e} (sin respuesta = arranca)")
    return False


# ------------------------------------------------------------- guard de CLI --
def cli_ocupado() -> bool:
    """True si hay código corriendo en el CLI: actividad reciente en el
    workspace de ZCode (los procesos de la app viven siempre; la señal
    fiable es que una sesión activa está tocando archivos)."""
    limite = time.time() - GUARD_ACTIVIDAD_MIN * 60
    for raiz, dirs, files in os.walk(WORKSPACE_ZCODE):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for n in files:
            p = os.path.join(raiz, n)
            try:
                if os.path.getmtime(p) > limite:
                    return True
            except OSError:
                continue
    return False


def esperar_cli_libre(dry: bool) -> None:
    rondas = 0
    while cli_ocupado():
        rondas += 1
        log(f"GUARD: CLI ocupado (trabajo en vivo) — pendiente, poll {GUARD_POLL_SEG}s (ronda {rondas})")
        if rondas % 15 == 1:  # avisa cada ~30 min que sigue esperando
            tg_enviar("🌙 Misión nocturna en espera: hay código corriendo en el CLI. "
                      "Arranca automáticamente al terminar (y vuelve a preguntar).")
        time.sleep(0 if dry else GUARD_POLL_SEG)
        if dry and rondas >= 2:
            log("GUARD dry-run: simulo CLI liberado")
            break


# ------------------------------------------------------------------ estado --
def cargar_estado() -> dict:
    with open(ESTADO) as f:
        return json.load(f)


def guardar_estado(est: dict) -> None:
    if DRY_GLOBAL:
        return  # dry-run jamás persiste el turno
    tmp = ESTADO + ".tmp"
    with open(tmp, "w") as f:
        json.dump(est, f, ensure_ascii=False, indent=2)
    os.replace(tmp, ESTADO)


def registrar_hecho(est: dict, hermano: str, nombre: str, lote: str, ok: bool) -> None:
    try:
        with open(HECHOS) as f:
            hechos = json.load(f)
        hechos.append({
            "id": max((h.get("id", 0) for h in hechos), default=0) + 1,
            "tema": hermano,
            "hecho": (f"Misión nocturna desatendida {'OK' if ok else 'FALLO'} — {nombre}, "
                      f"{lote} ({ahora().date().isoformat()}). Ejecutor: prometeo_nocturno "
                      f"(qwen3.6:35b). Registro: scripts/misiones/estado_misiones.json."),
            "fecha": ahora().date().isoformat(),
        })
        tmp = HECHOS + ".tmp"
        with open(tmp, "w") as f:
            json.dump(hechos, f, ensure_ascii=False, indent=1)
        os.replace(tmp, HECHOS)
    except Exception as e:
        log(f"WARN hechos.json no actualizable: {e}")


# ------------------------------------------------------------------- lotes --
def extraer_prompt(mision_path: str) -> str:
    """Extrae el primer bloque de código tras un encabezado con 'PROMPT'."""
    texto = open(mision_path).read()
    m = re.search(r"^#+.*PROMPT.*$.*?```[a-z]*\n(.*?)```", texto, re.S | re.M | re.I)
    if not m:
        raise RuntimeError(f"No se encontró PROMPT en {mision_path}")
    return m.group(1).strip()


def proximo_lote(mapa_path: str | None) -> tuple[str | None, str]:
    """(número de lote pendiente, línea completa del mapa a marcar)."""
    if not mapa_path or not os.path.exists(mapa_path):
        return None, ""
    for line in open(mapa_path):
        m = re.match(r"^\|\s*(\d+)[^|]*\|[^|]*\|\s*\[ \]", line)
        if m:
            return m.group(1), line.rstrip("\n")
    return "COMPLETO", ""  # mapa existe y no queda ningún [ ]


def marcar_lote(mapa_path: str | None, linea: str) -> None:
    if not mapa_path or not linea:
        return
    fecha = ahora().date().isoformat()
    nueva = re.sub(r"\[ \][^|]*", f"[x] nocturna {fecha} ", linea, count=1)
    texto = open(mapa_path).read()
    open(mapa_path, "w").write(texto.replace(linea, nueva, 1))


def append_historial(workspace: str, linea: str) -> None:
    harvest = os.path.join(workspace, "harvest-bibliografica")
    os.makedirs(os.path.join(harvest, "lotes"), exist_ok=True)
    with open(os.path.join(harvest, "HISTORIAL-TRABAJO.md"), "a") as f:
        f.write(f"\n- {ahora().isoformat(timespec='minutes')} {linea}")


def ejecutar_lote(hermano: dict, prompt: str, dry: bool) -> bool:
    out_dir = os.path.join(hermano["workspace"], "harvest-bibliografica", "lotes")
    os.makedirs(out_dir, exist_ok=True)
    salida = os.path.join(out_dir, f"{ahora().date().isoformat()}-{hermano['nombre']}.log")
    if dry:
        log(f"DRY-RUN ejecutaría: invocar_nocturno.py con prompt {len(prompt)} chars -> {salida}")
        return True
    log(f"Ejecutando prometeo (timeout {LOTE_TIMEOUT_SEG}s) -> {salida}")
    try:
        with open(salida, "w") as out:
            p = subprocess.run(
                [sys.executable, INVOCAR, prompt],
                stdout=out, stderr=subprocess.STDOUT, timeout=LOTE_TIMEOUT_SEG)
    except subprocess.TimeoutExpired:
        log(f"ERROR timeout del lote de {hermano['nombre']}")
        return False
    if p.returncode != 0:
        log(f"ERROR invocar_nocturno rc={p.returncode} ({hermano['nombre']})")
        return False
    tam = os.path.getsize(salida)
    if tam < 500:  # salida vacía/trunca = fallo silencioso, no cuenta
        log(f"ERROR salida sospechosamente corta ({tam}b) de {hermano['nombre']}")
        return False
    return True


# --------------------------------------------------------------------- main --
def horario_valido() -> bool:
    d = ahora()
    return (d.weekday() < 5 and d.hour == 22) or (d.weekday() == 5 and d.hour == 1) \
        or (d.weekday() == 6 and d.hour == 21)


def deadline() -> dt.datetime:
    d = ahora() + dt.timedelta(days=1)
    return d.replace(hour=DEADLINE_HORA, minute=0, second=0, microsecond=0)


def noche_legacy(dry: bool, force: bool) -> int:
    """Modo antiguo auto-ejecutado con prometeo (qwen). DEPRECATO desde el
    11-10: qwen en un solo turno no puede investigar de verdad (no navega ni
    descarga). El ejecutor oficial es el CLI de ZCode; este modo queda solo
    como referencia y para --dry-run de diagnóstico."""
    lk = open(LOCK, "w")
    try:
        fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log("OTRA ejecución en curso — salgo sin tocar nada")
        return 0
    if not dry and not force and not horario_valido():
        log(f"Arranque fuera de horario ({ahora():%a %H:%M}) — ignoro (cron mal configurado?)")
        return 0

    log(f"=== NOCHE {ahora():%Y-%m-%d %a} {'[DRY-RUN] ' if dry else ''}===")
    est = cargar_estado()
    dl = deadline()
    log(f"Cola: {' -> '.join(est['cola'])} | desborde previo: {est['pendiente_desborde'] or '—'} | cierre {dl:%H:%M}")

    # 1. guard de CLI + 2. consulta telegram (en bucle: si el CLI se libera,
    #    se VUELVE A PREGUNTAR antes de arrancar)
    while True:
        esperar_cli_libre(dry)
        if tg_preguntar_abort(
                "🌙 Investigación nocturna lista para arrancar "
                f"({' -> '.join(est['cola'])}). ¿Interrupción? Responde en "
                f"{MIN_RESPUESTA_MIN} min para abortar; sin respuesta arranco solo.",
                0 if dry else MIN_RESPUESTA_MIN):
            log("ABORTADO por el humano vía telegram — salida limpia, turno intacto")
            tg_enviar("🌙 Misión nocturna abortada. El turno queda intacto para la próxima noche.")
            return 0
        if not cli_ocupado() or dry:
            break
        log("GUARD: CLI volvió a ocuparse durante la pregunta — repito ciclo")

    # 3. cola: desborde primero, luego el resto en orden
    orden = [h for h in est["pendiente_desborde"]] + \
            [h for h in est["cola"] if h not in est["pendiente_desborde"]]
    est["pendiente_desborde"] = []
    ejecutados, desbordados, fallidos = [], [], []

    for h in orden:
        if ahora() >= dl:
            desbordados.append(h)
            log(f"DES BORDE: ventana cerrada, {h} queda PRIMERO mañana")
            continue
        her = est["hermanos"][h]
        est["hermanos"][h]["reintentos"] = 0
        ok, linea, etiqueta = False, "", ""
        while est["hermanos"][h]["reintentos"] <= REINTENTOS_MAX and ahora() < dl:
            try:
                prompt = extraer_prompt(her["mision"])
                lote_num, linea = proximo_lote(her.get("mapa"))
                if lote_num == "COMPLETO":
                    log(f"{h}: mapa COMPLETO — misión cumplida, fuera de la rotación")
                    ok, etiqueta = True, "mapa-completo"
                    est["cola"] = [c for c in est["cola"] if c != h]
                    break
                if lote_num:
                    prompt = re.sub(r"LOTE N", f"LOTE {lote_num}", prompt)
                    etiqueta = f"lote {lote_num}"
                else:
                    her["jornada"] = her.get("jornada", 0) + 1
                    etiqueta = f"jornada {her['jornada']}"
                    prompt = f"JORNADA {her['jornada']} de la misión.\n\n{prompt}"
            except Exception as e:
                log(f"ERROR preparando {h}: {e}")
                break
            log(f"Turno de {her['nombre']} ({h}) — {etiqueta}")
            ok = ejecutar_lote(her, prompt, dry)
            if ok:
                break
            est["hermanos"][h]["reintentos"] += 1
            log(f"FALLO {h} intento {est['hermanos'][h]['reintentos']}/{REINTENTOS_MAX} — "
                f"reintento al MISMO hermano (el turno no avanza)")
            time.sleep(60)
        if ok:
            if not dry:
                marcar_lote(her.get("mapa"), linea if her.get("mapa") else "")
                append_historial(her["workspace"],
                                 f"**MISIÓN NOCTURNA** {etiqueta} ejecutado por prometeo "
                                 f"(qwen3.6:35b, desatendido). Log: lotes/{ahora():%Y-%m-%d}-{her['nombre']}.log")
                registrar_hecho(est, h, her["nombre"], etiqueta, True)
            est["historial"].append({"fecha": ahora().isoformat(timespec="minutes"),
                                     "hermano": h, "lote": etiqueta, "resultado": "ok"})
            ejecutados.append(f"{her['nombre']} ({etiqueta}) ✓")
            tg_enviar(f"✅ {her['nombre']}: {etiqueta} completado.")
        elif ahora() >= dl:
            desbordados.append(h)
        else:
            fallidos.append(f"{her['nombre']} (agotó reintentos — PRIMERO mañana)")
            est["pendiente_desborde"].append(h)
        guardar_estado(est)

    # 4. cierre: rotación (el primero pasa al final) + desborde/fallido primero
    if est["cola"]:
        primero = est["cola"][0]
        est["cola"] = est["cola"][1:] + [primero]
    for h in desbordados:
        if h not in est["pendiente_desborde"]:
            est["pendiente_desborde"].append(h)
    guardar_estado(est)

    resumen = (f"🌙 Cierre nocturno {ahora():%Y-%m-%d}: "
               f"ejecutados: {', '.join(ejecutados) or '—'}; "
               f"desborde: {', '.join(desbordados) or '—'}; "
               f"fallidos: {', '.join(fallidos) or '—'}. "
               f"Próxima cola: {' -> '.join(est['pendiente_desborde'] + est['cola'])}")
    log(f"CIERRE: {resumen}")
    tg_enviar(resumen)
    return 0


# ------------------------------------------------- subcomandos para el CLI --
def cmd_turno() -> int:
    """Imprime el plan de la noche en JSON para que el CLI de ZCode lo ejecute."""
    est = cargar_estado()
    orden = est["pendiente_desborde"] + [h for h in est["cola"]
                                         if h not in est["pendiente_desborde"]]
    plan = []
    for h in orden:
        her = est["hermanos"][h]
        lote_num, _ = proximo_lote(her.get("mapa"))
        plan.append({
            "hermano": h, "nombre": her["nombre"], "mision": her["mision"],
            "workspace": her["workspace"],
            "lote": lote_num if lote_num else f"jornada {her.get('jornada', 0) + 1}",
            "mapa": her.get("mapa"),
        })
    print(json.dumps({"orden": plan, "cierre_ventana": f"{DEADLINE_HORA:02d}:00"},
                     ensure_ascii=False, indent=1))
    return 0


def cmd_preguntar() -> int:
    """Consulta de aborto por telegram; rc 0 = arrancar, rc 3 = ABORTADO."""
    est = cargar_estado()
    abortado = tg_preguntar_abort(
        "🌙 Investigación nocturna (CLI ZCode) lista para arrancar "
        f"({' -> '.join(est['cola'])}). ¿Interrupción? Responde en "
        f"{MIN_RESPUESTA_MIN} min para abortar; sin respuesta arranco solo.",
        MIN_RESPUESTA_MIN)
    if abortado:
        log("ABORTADO por el humano vía telegram — turno intacto")
        tg_enviar("🌙 Misión nocturna abortada. El turno queda intacto para la próxima noche.")
        return 3
    log("Sin respuesta (o confirmación) — el CLI puede arrancar la noche")
    return 0


def cmd_registrar(hermano: str, exito: bool, nota: str) -> int:
    """Registra el resultado de un hermano ejecutado por el CLI de ZCode."""
    est = cargar_estado()
    her = est["hermanos"].get(hermano)
    if not her:
        print(f"ERROR: hermano desconocido {hermano}", file=sys.stderr)
        return 2
    lote_num, linea = proximo_lote(her.get("mapa"))
    if lote_num and lote_num != "COMPLETO":
        etiqueta = f"lote {lote_num}"
        if exito:
            marcar_lote(her.get("mapa"), linea)
    elif lote_num == "COMPLETO":
        etiqueta = "mapa-completo"
    else:
        her["jornada"] = her.get("jornada", 0) + 1
        etiqueta = f"jornada {her['jornada']}"
    append_historial(her["workspace"],
                     f"**MISIÓN NOCTURNA (CLI ZCode)** {etiqueta} "
                     f"{'COMPLETADO' if exito else 'FALLO'}. {nota}".rstrip())
    registrar_hecho(est, hermano, her["nombre"], etiqueta, exito)
    est["historial"].append({"fecha": ahora().isoformat(timespec="minutes"),
                             "hermano": hermano, "lote": etiqueta,
                             "resultado": "ok" if exito else "fallo", "nota": nota})
    if not exito and hermano not in est["pendiente_desborde"]:
        est["pendiente_desborde"].append(hermano)  # reintenta primero mañana
    guardar_estado(est)
    tg_enviar(f"{'✅' if exito else '❌'} {her['nombre']}: {etiqueta} "
              f"{'completado' if exito else 'falló — primero mañana'}.")
    log(f"REGISTRADO {hermano} {etiqueta} {'ok' if exito else 'fallo'}")
    return 0


def cmd_cierre() -> int:
    """Cierre de la noche: rota la cola y resume por telegram."""
    est = cargar_estado()
    if est["cola"]:
        primero = est["cola"][0]
        est["cola"] = est["cola"][1:] + [primero]
    guardar_estado(est)
    ult = {(h["hermano"]): h for h in est["historial"] if h["fecha"].startswith(str(ahora().date()))}
    resumen = (f"🌙 Cierre nocturno {ahora():%Y-%m-%d} (CLI ZCode): "
               + "; ".join(f"{v['lote']} {'✓' if v['resultado'] == 'ok' else '✗'}"
                           for v in ult.values()) or "sin registros")
    resumen += f". Próxima cola: {' -> '.join(est['pendiente_desborde'] + est['cola'])}"
    log(f"CIERRE: {resumen}")
    tg_enviar(resumen)
    return 0


def cmd_ejecutar(hermano: str) -> int:
    """HERMES AGENT ejecuta la misión del hermano con el tier research
    (OpenRouter: deepseek-v4-flash → glm-5.3-flash). El CLI de ZCode solo
    despacha y vigila. Salida completa a lotes/<fecha>-<nombre>.log."""
    sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent/scripts")
    from llm_client import LLMClient  # noqa: E402 (ruta fuera del paquete)

    est = cargar_estado()
    her = est["hermanos"].get(hermano)
    if not her:
        print(f"ERROR: hermano desconocido {hermano}", file=sys.stderr)
        return 2
    prompt = extraer_prompt(her["mision"])
    lote_num, linea = proximo_lote(her.get("mapa"))
    if lote_num and lote_num != "COMPLETO":
        prompt = re.sub(r"LOTE N", f"LOTE {lote_num}", prompt)
        # prompt AUTONOMO y autocontenido: el modelo no tiene archivos ni
        # humano al otro lado — se le inyecta el mapa y el lote exacto.
        mapa_txt = open(her["mapa"]).read() if os.path.exists(her.get("mapa") or "") else ""
        prompt += (f"\n\n[DESPACHADOR — LEE ESTO PRIMERO]\n"
                   f"Ejecuta el LOTE {lote_num} de esta noche. Trabajo AUTÓNOMO: "
                   f"no hay humano que responda preguntas y no tienes acceso a "
                   f"archivos — todo el contexto que necesitas está en este prompt "
                   f"(usa la búsqueda web de la que dispones para verificar).\n\n"
                   f"MAPA DE CAMPAÑA (estado de lotes):\n{mapa_txt}\n\n"
                   f"ENTREGA OBLIGATORIA en tu respuesta (markdown):\n"
                   f"1. ## Candidatos del lote {lote_num} — por asignatura: 2-4 "
                   f"referencias con AUTOR, AÑO, TÍTULO y URL viva (solo fuentes de "
                   f"la casa: scielo.br, embrapa.br, bdtd.ibict.br, lrrd.org, fao.org, "
                   f"iris.paho.org, who.int, PubMed Central, saber.ucv.ve, Merck Vet "
                   f"Manual, brcorte.com.br). REGLA ANTI-INVENTO: solo URLs que "
                   f"encontraste con la búsqueda; si no hay, decláralo.\n"
                   f"2. ## Apuntes de estudio por asignatura — con sección "
                   f"'Resultados cuantitativos que debo poder citar' (datos con "
                   f"fuente+página/URL de los documentos encontrados).\n"
                   f"3. ## PDFs a descargar mañana — lista con URL exacta para el "
                   f"técnico (las descargas e ingesta a Qdrant las hace el día "
                   f"siguiente la validación).")
        etiqueta = f"lote {lote_num}"
        # GROUNDING LOCAL: resultados web reales inyectados al prompt para
        # que los flash ABIERTOS citen sin inventar (plugin web = solo Gemini).
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from buscar_web import buscar  # noqa: E402
            dominio = linea.split("|")[2].strip() if linea.count("|") >= 3 else etiqueta
            dominio = re.sub(r"[⭐]", "", dominio).strip() or etiqueta
            contexto = []
            for q in (f"{dominio} pdf embrapa scielo",
                      f"{dominio} tesis bdtd ibict",
                      f"{dominio} fao who guia"):
                contexto += buscar(q, 4)
            if contexto:
                prompt += ("\n\n[RESULTADOS DE BÚSQUEDA WEB REALES de esta noche "
                           "— úsalos como punto de partida; cita solo lo que "
                           "verifiques aquí o conozcas con certeza]:\n"
                           + "\n".join(f"- {c['titulo']}\n  {c['url']}\n  {c['snippet']}"
                                       for c in contexto[:12]))
                log(f"GROUNDING {hermano}: {len(contexto[:12])} resultados inyectados")
        except Exception as e:
            log(f"WARN grounding {hermano}: {e} (sigo sin contexto web)")
    elif lote_num == "COMPLETO":
        log(f"{hermano}: mapa ya COMPLETO — nada que ejecutar")
        return 0
    else:
        her["jornada"] = her.get("jornada", 0) + 1
        etiqueta = f"jornada {her['jornada']}"
        prompt = f"JORNADA {her['jornada']} de la misión.\n\n{prompt}"
    guardar_estado(est)

    out_dir = os.path.join(her["workspace"], "harvest-bibliografica", "lotes")
    os.makedirs(out_dir, exist_ok=True)
    salida = os.path.join(out_dir, f"{ahora().date().isoformat()}-{her['nombre']}.log")
    log(f"EJECUTANDO via Hermes (tier research) {hermano} — {etiqueta} -> {salida}")
    cliente = LLMClient()
    try:
        r = cliente.complete(
            [{"role": "user", "content": prompt}],
            task_type="research", max_tokens=16000, temperature=0.4)
    except Exception as e:
        log(f"ERROR research {hermano}: {e}")
        return 1
    if r.get("error"):
        log(f"ERROR research {hermano}: {r['error']}")
        return 1
    with open(salida, "w") as f:
        f.write(f"<!-- tier={r.get('tier')} model={r.get('model')} "
                f"{etiqueta} {ahora().isoformat()} -->\n\n{r['content']}\n")
    tam = len(r.get("content", ""))
    log(f"OK research {hermano} {etiqueta}: tier={r.get('tier')} "
        f"caracteres={tam} -> {salida}")
    return 0 if tam > 2000 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--turno", action="store_true",
                    help="imprime el plan de la noche (JSON) para el CLI")
    ap.add_argument("--preguntar", action="store_true",
                    help="consulta de aborto por telegram (bloquea 10 min)")
    ap.add_argument("--registrar", metavar="HERMANO",
                    help="registra resultado del hermano")
    ap.add_argument("--fallo", action="store_true", help="con --registrar: resultado fallo")
    ap.add_argument("--nota", default="", help="nota para el registro")
    ap.add_argument("--cierre", action="store_true", help="rota cola y resume la noche")
    ap.add_argument("--ejecutar", metavar="HERMANO",
                    help="Hermes ejecuta la misión del hermano (tier research OpenRouter)")
    ap.add_argument("--legacy-run", action="store_true",
                    help="DEPRECADO: modo antiguo con qwen (solo diagnóstico)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if args.turno:
        return cmd_turno()
    if args.preguntar:
        return cmd_preguntar()
    if args.registrar:
        return cmd_registrar(args.registrar, not args.fallo, args.nota)
    if args.cierre:
        return cmd_cierre()
    if args.ejecutar:
        return cmd_ejecutar(args.ejecutar)
    if args.legacy_run:
        return noche_legacy(args.dry_run, args.force)
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())