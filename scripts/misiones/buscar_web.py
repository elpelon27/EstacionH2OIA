#!/usr/bin/env python3
"""buscar_web.py — Búsqueda web de grounding para las misiones nocturnas.
stdlib puro (urllib + regex). Devuelve resultados título+URL.

Por qué existe: el plugin web de OpenRouter solo lo soporta Gemini (cerrado).
Con esto, los flash ABIERTOS (GLM/DeepSeek/Qwen) reciben resultados reales
inyectados en el prompt — regla anti-invento preservada sin modelo cerrado.

Multi-buscador con fallback (lección 12-oct: DDG limita ráfagas por IP y
devuelve páginas vacías → nunca depender de un solo endpoint):
  Bing HTML → Mojeek → DDG (html/lite).

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


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Language": "es,pt,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "replace")


def _limpiar(t: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", t)).strip()


def _bing(q: str, n: int) -> list[dict]:
    pagina = _fetch("https://www.bing.com/search?q="
                    + urllib.parse.quote(q) + "&count=15")
    out = []
    for m in re.finditer(
            r'<h2><a href="(https?://[^"]+)"[^>]*>(.*?)</a></h2>', pagina, re.S):
        url, titulo = m.group(1), _limpiar(m.group(2))
        if "bing.com" in url or "microsoft" in url or not titulo:
            continue
        out.append({"titulo": titulo, "url": url, "snippet": ""})
        if len(out) >= n:
            break
    return out


def _mojeek(q: str, n: int) -> list[dict]:
    pagina = _fetch("https://www.mojeek.com/search?q=" + urllib.parse.quote(q))
    out = []
    for m in re.finditer(
            r'<a class="title[^"]*" href="(https?://[^"]+)"[^>]*>(.*?)</a>',
            pagina, re.S):
        out.append({"titulo": _limpiar(m.group(2)), "url": m.group(1), "snippet": ""})
        if len(out) >= n:
            break
    return out


def _ddg(q: str, n: int) -> list[dict]:
    out = []
    for endpoint in ("https://html.duckduckgo.com/html/?q=",
                     "https://lite.duckduckgo.com/lite/?q="):
        try:
            pagina = _fetch(endpoint + urllib.parse.quote(q))
        except Exception:  # noqa: BLE001 (fallback)
            continue
        items = re.findall(
            r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', pagina, re.S)
        for href, titulo in items[:n]:
            m = re.search(r"[?&]uddg=([^&]+)", href)
            real = urllib.parse.unquote(m.group(1)) if m else href
            if "duckduckgo.com" in real:
                continue
            out.append({"titulo": _limpiar(titulo), "url": real, "snippet": ""})
        if out:
            return out
    return out


def buscar(consulta: str, n: int = 6) -> list[dict]:
    """Bing → Mojeek → DDG. Lanza RuntimeError si todos fallan (nada
    silencioso: el despachador lo registra y el modelo declara NO VERIFICADA)."""
    errores = []
    for motor in (_bing, _mojeek, _ddg):
        try:
            r = motor(consulta, n)
            if r:
                return r
            errores.append(f"{motor.__name__}: 0 resultados")
        except Exception as e:  # noqa: BLE001 (fallback explícito)
            errores.append(f"{motor.__name__}: {type(e).__name__}")
        time.sleep(2)
    raise RuntimeError("búsqueda vacía en todos los motores: " + "; ".join(errores))


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    for r in buscar(sys.argv[1], n):
        print(f"- {r['titulo']}\n  {r['url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
