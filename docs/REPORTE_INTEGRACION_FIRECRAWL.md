# 📡 REPORTE — Integración Firecrawl (backend web)

**Fecha:** 2026-08-15
**Sistema:** Hermes Agent / Estación H2O (Prometeo)
**Estado global:** CONFIGURADO Y VERIFICADO (end-to-end real)

---

## 1) Qué se integró

Firecrawl como **backend de búsqueda y extracción web** de Hermes, en sustitución/deselección del
extractor por defecto (que solo servía búsqueda vía DDGS). Esto desbloquea la lectura de páginas
que requieren rendering JS, gestionan bloqueos anti-bot (WAF), o son PDFs — el caso que motivó la
integración (publicación de Reddit bloqueada por WAF).

Se eligió Firecrawl sobre Tavily por criterio técnico: motor de scraping/rendering real (Playwright),
mejor rendimiento en recuperación de contenido profundo (benchmark AIMultiple 2026), y — clave —
resuelve el caso real de extracción de páginas bloqueadas que Tavily (search-to-answer) no cubre.

## 2) Configuración aplicada (HERMES_HOME=/home/skynet/hermes-unified)

En `config.yaml` (vía `hermes config set`, respetando invariantes):
```yaml
web:
  backend: firecrawl
  search_backend: firecrawl
  extract_backend: firecrawl
```

En `.env` (secreto, dentro del HERMES_HOME correcto):
```
FIRECRAWL_API_KEY=fc-…(redactado)
```

## 3) Dependencia

SDK `firecrawl 4.35.1` instalado en el venv del runtime (`/home/skynet/.hermes/hermes-agent/venv`).
El provider de Hermes (`plugins/web/firecrawl/provider.py`) importa y resuelve correctamente.

## 4) Verificación (DoO — comprobado, no asumido)

| Ítem | Métrica | Resultado |
|------|---------|-----------|
| API key | `POST /v1/scrape` (curl) | http=200, `success:true` |
| Cuenta activa | `get_credit_usage()` | **1124 créditos** (plan 1000/mes + bono) |
| Provider de Hermes | `_get_firecrawl_client()` | importa OK, tipo `Firecrawl` |
| Scrape end-to-end | `c.scrape("https://example.com")` | ✓ markdown real + título correcto |

## 5) Nota de despliegue

El cambio de `web.backend` toma efecto en una **sesión nueva** de Hermes (no en la activa), por la
disciplina de prompt-caching del framework — no es un fallo. Tras abrir sesión nueva, `web_extract`
debería rutear por Firecrawl.

## 6) Coste

Proveedor freemium: **1,000 créditos/mes gratis, sin tarjeta**. No aplica coste extra por el volumen
de lectura puntual del agente. Sin Docker adicional en el hogar (se evitó self-hosting: 7+ servicios
habrían sido sobre-dimensionados para un servidor de producción ya cargado).

---

**Veredicto:** integración completa y funcional, verificada con una extracción real. 💧
