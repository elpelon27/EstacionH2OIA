---
name: repair-valentina-llm-chain
description: Cuando Valentina responde con "dificultades técnicas" (fallback), Dify no responde, o contenedores docker no pueden alcanzar servicios del host (Ollama, etc.) después de un restart de docker o migración de runtime. Diagnóstico y fix completo de la cadena LLM: Ollama → plugin_daemon → Dify API → valentina-bridge → WAHA → WhatsApp.
---

# Repair Valentina LLM Chain

## Cuándo aplicar este skill

Aplicar cuando se presente CUALQUIERA de estos síntomas:

1. **Valentina manda "disculpe tengo dificultades técnicas"** por WhatsApp (fallback del bridge cuando la cadena LLM falla)
2. **skynet_27_bot reporta "Dify no responde"**
3. **Contenedores docker no pueden alcanzar servicios del host** (Ollama en 11434, etc.) después de:
   - `systemctl restart docker`
   - Migración de containerd root
   - Reinicio del servidor
   - Cualquier operación que recrea bridges docker
4. **Errores en logs Dify** del tipo:
   - `connect ECONNREFUSED 172.17.0.1:11434` (plugin_daemon → Ollama)
   - `fetch failed` / `EAI_AGAIN` en llamadas salientes
   - Timeouts hacia `http://172.17.0.1:11434` o `http://host.docker.internal:11434`
