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
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def buscar(consulta: str, n: int = 6) -> list[dict]:
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(consulta)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        pagina = r.read().decode("utf-8", "replace")
    resultados = []
    # DDG html: <a rel="nofollow" class="result__a" href="...">titulo</a>
    # y snippets en <a class="result__snippet" ...>texto</a>
    items = re.findall(
        r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', pagina, re.S)
    snippets = re.findall(
        r'class="result__snippet"[^>]*>(.*?)</a>', pagina, re.S)
    for i, (href, titulo) in enumerate(items[:n]):
        # DDG envuelve con /l/?uddg=<url codificada>
        m = re.search(r"[?&]uddg=([^&]+)", href)
        real = urllib.parse.unquote(m.group(1)) if m else href
        snip = re.sub(r"<[^>]+>", "", snippets[i]) if i < len(snippets) else ""
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
