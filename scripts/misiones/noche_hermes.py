#!/usr/bin/env python3
"""noche_hermes.py — Orquestador NOCTURNO AUTÓNOMO de HERMES AGENT.

PROPIEDAD: Hermes Agent (entrega formal del Líder + ZCode, 2026-10-12).
Desde el 13-oct-2026 Hermes es el EJECUTOR dueño de las noches de
investigación de los 4 hermanos (Empédocles, Tripólemo, Aristeo, Quirón),
disparado por el CRONJOB DEL HOST — sin depender de ninguna sesión ZCode.

Rutina de cada noche (Lun-Vie 22:00 · Sáb 01:00 · Dom 21:00, ventana 06:00):
  1. Pregunta por Telegram si hay interrupción (10 min; sin respuesta arranca).
  2. Lee el turno (estado_misiones.json: cola rotante + desborde primero).
  3. Por hermano: --ejecutar (grounding web local buscar_web.py + flash
     ABIERTOS glm-5.3-flash → qwen3.8-flash → deepseek-v4-flash; Gemini
     cerrado SOLO último recurso). Reintenta 1 vez si falla.
  4. Registra éxito/fallo (--registrar marca mapa, historial, hechos).
     Fallo => el hermano queda PRIMERO mañana (el turno no avanza).
  5. Cierre: rota la cola y resume por Telegram.

ZCode queda como GUARDIÁN externo (validación diaria 08:00, dos ojos):
docs/MISION-NOCTURNA-ENTREGA-HERMES.md es el manual completo.

Uso:
  python3 noche_hermes.py            # noche completa
  python3 noche_hermes.py --test     # 1 solo hermano, sin registrar cierre
"""
import datetime as dt
import subprocess
import sys

import mision_nocturna as mn

DEADLINE_H = 6
REINTENTOS = 1


def _en_ventana() -> bool:
    return dt.datetime.now().hour < DEADLINE_H or dt.datetime.now().hour >= 21


def main() -> int:
    test = "--test" in sys.argv
    est = mn.cargar_estado()
    orden = est["pendiente_desborde"] + [h for h in est["cola"]
                                         if h not in est["pendiente_desborde"]]
    if mn.tg_preguntar_abort(
            "🌙 [HERMES] Investigación nocturna lista para arrancar "
            f"({' -> '.join(orden)}). ¿Interrupción? Responde en "
            f"{mn.MIN_RESPUESTA_MIN} min para abortar; sin respuesta arranco solo.",
            mn.MIN_RESPUESTA_MIN):
        return 0
    resultados = []
    for h in orden:
        if not _en_ventana():
            mn.log(f"[HERMES] Ventana cerrada: {h} queda PRIMERO mañana")
            est = mn.cargar_estado()
            if h not in est["pendiente_desborde"]:
                est["pendiente_desborde"].append(h)
                mn.guardar_estado(est)
            continue
        if test and resultados:
            mn.log("[HERMES] modo --test: solo 1 hermano")
            break
        rc = 1
        for intento in range(REINTENTOS + 1):
            rc = mn.cmd_ejecutar(h)
            if rc == 0:
                break
            mn.log(f"[HERMES] fallo {h} intento {intento + 1}")
        nota = "autónomo Hermes (flash abierto + grounding local)"
        mn.cmd_registrar(h, rc == 0, nota if rc == 0 else "fallo tras reintentos")
        resultados.append((h, rc == 0))
    if not test:
        mn.cmd_cierre()
    return 0


if __name__ == "__main__":
    sys.exit(main())
