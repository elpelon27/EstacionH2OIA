#!/usr/bin/env python3
"""buscar_web.py — Búsqueda web de grounding para las misiones nocturnas.
stdlib puro (urllib + regex). Devuelve resultados título+URL+snippet.

Por qué existe: el plugin web de OpenRouter solo lo soporta Gemini (cerrado).
Con esto, los flash ABIERTOS (GLM/DeepSeek/Qwen) reciben resultados reales
inyectados en el prompt — regla anti-invento preservada sin modelo cerrado.

Uso:
  python3 buscar_web.py "consulta" [n]
"""
import html
import re
import sys
import time
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def buscar(consulta: str, n: int = 6) -> list[dict]:
    """DDG html con fallback a lite y reintento con backoff (la lección del
    12-oct: DDG limita ráfagas → resultados vacíos silenciosos)."""
    ultima_ex: Exception | None = None
    for intento in range(3):
        endpoint = ("https://html.duckduckgo.com/html/?q="
                    if intento % 2 == 0 else
                    "https://lite.duckduckgo.com/lite/?q=") + urllib.parse.quote(consulta)
        try:
            req = urllib.request.Request(endpoint, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as r:
                pagina = r.read().decode("utf-8", "replace")
            resultados = _parsear(pagina, n)
            if resultados:
                return resultados
        except Exception as e:  # noqa: BLE001 (reintento explícito)
            ultima_ex = e
        time.sleep(4 + intento * 4)  # backoff: DDG castiga las ráfagas
    if ultima_ex:
        raise ultima_ex
    return []


def _parsear(pagina: str, n: int) -> list[dict]:
    resultados = []
    # html.duckduckgo.com: <a class="result__a" href>titulo</a> + snippet
    items = re.findall(
        r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', pagina, re.S)
    snippets = re.findall(
        r'class="result__snippet"[^>]*>(.*?)</a>', pagina, re.S)
    if not items:
        # lite.duckduckgo.com: <a rel="nofollow" href="url" class="result-link">
        items = re.findall(
            r'href="(https?://[^"]+)"[^>]*class="result-link"[^>]*>(.*?)</a>',
            pagina, re.S) or re.findall(
            r'class="result-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', pagina, re.S)
        snippets = re.findall(
            r'class="result-snippet">(.*?)</td>', pagina, re.S)
    for i, (href, titulo) in enumerate(items[:n]):
        m = re.search(r"[?&]uddg=([^&]+)", href)
        real = urllib.parse.unquote(m.group(1)) if m else href
        snip = re.sub(r"<[^>]+>", "", snippets[i]) if i < len(snippets) else ""
        if "duckduckgo.com" in real:
            continue
        resultados.append({
            "titulo": html.unescape(re.sub(r"<[^>]+>", "", titulo)).strip(),
            "url": real,
            "snippet": html.unescape(snip).strip()[:280],
        })
    return resultados


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    for r in buscar(sys.argv[1], n):
        print(f"- {r['titulo']}\n  {r['url']}\n  {r['snippet']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
