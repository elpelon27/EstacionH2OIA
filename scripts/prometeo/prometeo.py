#!/usr/bin/env python3
"""
============================================================================
Prometeo CLI — Asistente de desarrollo para Estación H2O
Powered by GLM 5.2 vía NVIDIA NIM
============================================================================

Uso:
   python3 prometeo.py

Comandos especiales:
   /context   - Recargar contexto del proyecto
   /clear     - Limpiar conversación
   /save      - Guardar conversación en memory/sessions/
   /exit      - Salir
"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# LLMClient vive en scripts/ (sin __init__.py) → shim de sys.path
_REPO_ROOT = Path("/mnt/ssd_trabajo/hermes-agent")
sys.path.insert(0, str(_REPO_ROOT / "scripts"))
from llm_client import LLMClient, detect_task_type  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler()],
)

# ============================================================================
# Configuración
# ============================================================================

# Cargar .env (NVIDIA_API_KEY debe estar en config/.env, NO hardcoded aquí)
_env_path = Path("/mnt/ssd_trabajo/hermes-agent/config/.env")
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

# Cadena de fallback LLM: glm-5.3-paid → glm-5.2-free → ollama-local (solo chat)
llm = LLMClient()

PROJECT_ROOT = Path("/mnt/ssd_trabajo/hermes-agent")
MEMORY_DIR = PROJECT_ROOT / "memory" / "sessions"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================================
# Contexto del proyecto (carga inicial)
# ============================================================================

SYSTEM_PROMPT = (
    "Eres Prometeo, ingeniero senior full-stack que asiste a "
    "Luis Martinez (@elpelon27) en el proyecto Estación H2O "
    "Maracaibo (distribución de agua y hielo).\n\n"
    "## Tu identidad\n"
    "- Tono: profesional pero amable, venezolano natural\n"
    "- Idioma: español de Venezuela exclusivamente\n"
    "- Firma: 💧 al final de mensajes importantes\n"
    '- Estilo: honesto técnico, si no sabes algo dices "no sé" y verificas\n\n'
    "## Proyecto\n"
    "- Ruta: /mnt/ssd_trabajo/hermes-agent\n"
    "- Stack: Python 3.12 + FastAPI + SQLite + Telegram Bot + WhatsApp Meta Cloud API\n"
    "- LLM: GLM 5.2 vía NVIDIA NIM (tú)\n"
    "- GitHub: https://github.com/elpelon27/EstacionH2OIA.git\n\n"
    "## Reglas de trabajo\n"
    "1. UN prompt, UN output, UN avance verificable\n"
    "2. Verificar con datos reales antes de asumir\n"
    "3. Honestidad técnica: si no sabes, pregunta\n"
    "4. Firmar mensajes importantes con 💧\n"
    "5. Usar /home/z/my-project/worklog.md para registro de trabajo entre sesiones\n\n"
    "## Componentes clave del proyecto\n"
    "- api/bridge.py: Bridge WhatsApp Meta Cloud API ↔ Dify/NIM\n"
    "- skills/dispatcher.py: Bot Telegram para choferes (@DespachoH2O_bot)\n"
    "- skills/dispatch/route_engine.py: OR-Tools VRP solver\n"
    "- skills/telegram_bot.py: Bot Líder (@Skynet_27_bot)\n"
    "- src/financial/: Financial Shield v2.0 (10 tablas)\n"
    "- data/conversations.db: orders, dispatch_queue, fs_pedidos\n"
    "- data/dispatch.db: clients, deliveries, vehicles, dispatch_sessions\n"
    "- config/.env: tokens y configuración\n"
    "- docs/SOUL.md: personalidad Valentina v5\n"
    "- docs/DISPATCHER_ARCHITECTURE.md: especificación dispatcher (921 líneas)\n\n"
    "## Servicios systemd activos\n"
    "- valentina-bridge.service: Bridge WhatsApp\n"
    "- cloudflared: Named Tunnel valentina.estacionh2o.com\n"
    "- dispatcher-bot.service: Bot choferes\n"
    "- telegram-bot.service: Bot Líder\n\n"
    "## Tarea actual: Dispatcher FASE 1\n"
    "Bug crítico: función _send_to_dispatch_queue (línea 796 bridge.py)\n"
    "DEFINIDA pero NUNCA LLAMADA. dispatch_queue vacía (0 registros).\n\n"
    "Plan:\n"
    "1. Fix bridge → dispatch_queue (1h)\n"
    "2. Crear clients automáticos en dispatch.db (1h)\n"
    "3. Cron 7:45am ruta automática (3h)\n"
    "4. Fix botones new_arr/new_del/new_no en dispatcher.py (30min)\n"
    "5. Test end-to-end (30min)"
)

# ============================================================================
# Cliente OpenAI compatible
# ============================================================================

# Historial de conversación
messages = [{"role": "system", "content": SYSTEM_PROMPT}]


def chat(user_input: str) -> str:
    """Envía mensaje a la cadena de fallback LLM y retorna respuesta."""
    task_type = detect_task_type(user_input)
    messages.append({"role": "user", "content": user_input})

    try:
        result = llm.complete(messages, task_type=task_type)
        if "error" in result:
            return (
                "❌ " + result.get("message", "Sin LLM pagado disponible")
                + "\n\n(Ollama local queda reservado SOLO para chat, "
                "no para tareas técnicas.) 💧"
            )
        response = result["content"]
        messages.append({"role": "assistant", "content": response})
        return response
    except Exception as e:
        return f"❌ Error: {e}"


def save_session() -> Path:
    """Guarda conversación actual en memory/sessions/."""
    filename = MEMORY_DIR / f"prometeo_{datetime.now().strftime('%Y-%m-%d_%H%M')}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(
            {"timestamp": datetime.now().isoformat(), "model": "llm-chain-3tiers", "messages": messages},
            f,
            ensure_ascii=False,
            indent=2,
        )
    return filename


# ============================================================================
# Loop principal
# ============================================================================


def main() -> None:
    print("=" * 60)
    print("  PROMETEO CLI — Cadena LLM 3 tiers (GLM 5.3 → GLM 5.2 free → Ollama)")
    print("  Asistente de desarrollo · Estación H2O")
    print("=" * 60)
    print()
    print("Comandos especiales:")
    print("  /context  - Recargar contexto del proyecto")
    print("  /clear    - Limpiar conversación")
    print("  /save     - Guardar conversación")
    print("  /exit     - Salir")
    print()
    print("-" * 60)
    print("Prometeo: ¡Buenas, Líder! Listo para seguir trabajando en el")
    print("Dispatcher. ¿Empezamos con el bug de _send_to_dispatch_queue? 💧")
    print("-" * 60)
    print()

    while True:
        try:
            user_input = input("Tú: ").strip()
            if not user_input:
                continue

            if user_input == "/exit":
                print("\nPrometeo: ¡Hasta pronto, Líder! 💧")
                break
            elif user_input == "/clear":
                messages.clear()
                messages.append({"role": "system", "content": SYSTEM_PROMPT})
                print("\nPrometeo: Conversación limpiada. Empezamos fresco. 💧\n")
                continue
            elif user_input == "/save":
                filename = save_session()
                print(f"\nPrometeo: ✅ Guardado en {filename}\n")
                continue
            elif user_input == "/context":
                print(f"\nPrometeo: Contexto cargado ({len(SYSTEM_PROMPT)} chars)")
                print(f"  Proyecto: {PROJECT_ROOT}")
                print("  LLM: glm-5.3-paid → glm-5.2-free → ollama-local (solo chat)")
                print(f"  Mensajes en historial: {len(messages)}\n")
                continue

            print("\nPrometeo: ", end="", flush=True)
            response = chat(user_input)
            print(response)
            print()

        except KeyboardInterrupt:
            print("\n\nPrometeo: ¿Salir? Usa /exit para cerrar correctamente. 💧\n")
            continue
        except EOFError:
            break


if __name__ == "__main__":
    main()
