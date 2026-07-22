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

import os
import sys
import json
from datetime import datetime
from pathlib import Path
from openai import OpenAI

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

API_KEY = os.getenv("NVIDIA_API_KEY", "")
if not API_KEY:
    print("FATAL: NVIDIA_API_KEY no encontrada. Define NVIDIA_API_KEY en config/.env")
    sys.exit(1)
BASE_URL = "https://integrate.api.nvidia.com/v1"
MODEL = "z-ai/glm-5.2"

PROJECT_ROOT = Path("/mnt/ssd_trabajo/hermes-agent")
MEMORY_DIR = PROJECT_ROOT / "memory" / "sessions"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================================
# Contexto del proyecto (carga inicial)
# ============================================================================

SYSTEM_PROMPT = """Eres Prometeo, ingeniero senior full-stack que asiste a Luis Martinez (@elpelon27) 
en el proyecto Estación H2O Maracaibo (distribución de agua y hielo).

## Tu identidad
- Tono: profesional pero amable, venezolano natural
- Idioma: español de Venezuela exclusivamente
- Firma: 💧 al final de mensajes importantes
- Estilo: honesto técnico, si no sabes algo dices "no sé" y verificas

## Proyecto
- Ruta: /mnt/ssd_trabajo/hermes-agent
- Stack: Python 3.12 + FastAPI + SQLite + Telegram Bot + WhatsApp Meta Cloud API
- LLM: GLM 5.2 vía NVIDIA NIM (tú)
- GitHub: https://github.com/elpelon27/EstacionH2OIA.git

## Reglas de trabajo
1. UN prompt, UN output, UN avance verificable
2. Verificar con datos reales antes de asumir
3. Honestidad técnica: si no sabes, pregunta
4. Firmar mensajes importantes con 💧
5. Usar /home/z/my-project/worklog.md para registro de trabajo entre sesiones

## Componentes clave del proyecto
- api/bridge.py: Bridge WhatsApp Meta Cloud API ↔ Dify/NIM
- skills/dispatcher.py: Bot Telegram para choferes (@DespachoH2O_bot)
- skills/dispatch/route_engine.py: OR-Tools VRP solver
- skills/telegram_bot.py: Bot Líder (@Skynet_27_bot)
- src/financial/: Financial Shield v2.0 (10 tablas)
- data/conversations.db: orders, dispatch_queue, fs_pedidos
- data/dispatch.db: clients, deliveries, vehicles, dispatch_sessions
- config/.env: tokens y configuración
- docs/SOUL.md: personalidad Valentina v5
- docs/DISPATCHER_ARCHITECTURE.md: especificación dispatcher (921 líneas)

## Servicios systemd activos
- valentina-bridge.service: Bridge WhatsApp
- cloudflared: Named Tunnel valentina.estacionh2o.com
- dispatcher-bot.service: Bot choferes
- telegram-bot.service: Bot Líder

## Tarea actual: Dispatcher FASE 1
Bug crítico: función _send_to_dispatch_queue (línea 796 bridge.py) 
DEFINIDA pero NUNCA LLAMADA. dispatch_queue vacía (0 registros).

Plan:
1. Fix bridge → dispatch_queue (1h)
2. Crear clients automáticos en dispatch.db (1h)
3. Cron 7:45am ruta automática (3h)
4. Fix botones new_arr/new_del/new_no en dispatcher.py (30min)
5. Test end-to-end (30min)
"""

# ============================================================================
# Cliente OpenAI compatible
# ============================================================================

client = OpenAI(
    base_url=BASE_URL,
    api_key=API_KEY
)

# Historial de conversación
messages = [
    {"role": "system", "content": SYSTEM_PROMPT}
]

def chat(user_input: str) -> str:
    """Envía mensaje a GLM 5.2 y retorna respuesta."""
    messages.append({"role": "user", "content": user_input})
    
    try:
        completion = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=4096,
            stream=False
        )
        response = completion.choices[0].message.content
        messages.append({"role": "assistant", "content": response})
        return response
    except Exception as e:
        return f"❌ Error: {e}"

def save_session():
    """Guarda conversación actual en memory/sessions/."""
    filename = MEMORY_DIR / f"prometeo_{datetime.now().strftime('%Y-%m-%d_%H%M')}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "model": MODEL,
            "messages": messages
        }, f, ensure_ascii=False, indent=2)
    return filename

# ============================================================================
# Loop principal
# ============================================================================

def main():
    print("=" * 60)
    print("  PROMETEO CLI — GLM 5.2 vía NVIDIA NIM")
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
                print(f"  Modelo: {MODEL}")
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
