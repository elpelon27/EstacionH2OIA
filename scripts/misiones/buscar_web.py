#!/usr/bin/env python3
"""buscar_web.py — Grounding de referencias para las misiones nocturnas.
stdlib puro. Para una misión BIBLIOGRÁFICA el grounding correcto son las
APIs científicas (refs con DOI verificable por construcción), no el
scraping de buscadores (lección 12-oct: Bing/Mojeek/DDG sirven basura o
vacio sin JS desde esta IP).

Cadena: OpenAlex (500k req/día gratis) → Crossref (gratis).
Solo si ambas fallan → busca general DDG/lite (último recurso).

Uso:
  python3 buscar_web.py "consulta" [n]
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request

UA = {"User-Agent": "hermes-agent/1.0 (investigacion.bibliografica; mailto:hermes@estacion-h2o.local)"}


def _get_json(url: str, tries: int = 2) -> dict:
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception:  # noqa: BLE001 (reintento)
            if i == tries - 1:
                raise
            time.sleep(3)


def _openalex(q: str, n: int) -> list[dict]:
    url = ("https://api.openalex.org/works?search=" + urllib.parse.quote(q)
           + f"&per-page={min(n, 25)}&mailto=hermes@estacion-h2o.local"
             "&filter=is_oa:true")
    d = _get_json(url)
    out = []
    for w in d.get("results", []):
        doi = (w.get("doi") or "").replace("https://doi.org/", "")
        url_final = None
        for loc in (w.get("best_oa_location") or {}, w.get("primary_location") or {}):
            if loc.get("pdf_url"):
                url_final = loc["pdf_url"]
                break
            if loc.get("landing_page_url"):
                url_final = url_final or loc["landing_page_url"]
        if not url_final and doi:
            url_final = f"https://doi.org/{doi}"
        if not url_final:
            continue
        fuente = ((w.get("primary_location") or {}).get("source") or {}).get("display_name") or ""
        out.append({
            "titulo": re.sub(r"<[^>]+>", "", w.get("display_name") or "")[:200],
            "url": url_final,
            "snippet": (f"{w.get('publication_year')} · {fuente} · autores: "
                        + ", ".join(a["author"]["display_name"]
                                    for a in (w.get("authorships") or [])[:3])
                        + (f" · DOI:{doi}" if doi else "") + " · OA")[:280],
        })
        if len(out) >= n:
            break
    return out


def _crossref(q: str, n: int) -> list[dict]:
    url = ("https://api.crossref.org/works?query.bibliographic="
           + urllib.parse.quote(q) + f"&rows={n}&select=DOI,title,URL,issued,container-title")
    d = _get_json(url)
    out = []
    for it in d.get("message", {}).get("items", []):
        titulo = (it.get("title") or [""])[0]
        año = (it.get("issued", {}).get("date-parts") or [[None]])[0][0]
        rev = (it.get("container-title") or [""])[0]
        out.append({
            "titulo": titulo[:200],
            "url": f"https://doi.org/{it['DOI']}",
            "snippet": f"{año} · {rev} · DOI:{it['DOI']}"[:280],
        })
        if len(out) >= n:
            break
    return out


def _ddg_lite(q: str, n: int) -> list[dict]:
    req = urllib.request.Request(
        "https://lite.duckduckgo.com/lite/?q=" + urllib.parse.quote(q),
        headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/120.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        pagina = r.read().decode("utf-8", "replace")
    out = []
    for m in re.finditer(r'href="(https?://[^"]+)"[^>]*class="result-link"',
                         pagina):
        if "duckduckgo.com" not in m.group(1):
            out.append({"titulo": m.group(1)[:120], "url": m.group(1), "snippet": ""})
        if len(out) >= n:
            break
    return out


def buscar(consulta: str, n: int = 6) -> list[dict]:
    """OpenAlex → Crossref → DDG-lite. RuntimeError si todo falla (nada
    silencioso: el modelo deberá declarar NO VERIFICADA y el despachador
    lo registra)."""
    errores = []
    for motor in (_openalex, _crossref, _ddg_lite):
        try:
            r = motor(consulta, n)
            if r:
                return r
            errores.append(f"{motor.__name__}: 0")
        except Exception as e:  # noqa: BLE001 (fallback explícito)
            errores.append(f"{motor.__name__}: {type(e).__name__}")
        time.sleep(1)
    raise RuntimeError("grounding vacío: " + "; ".join(errores))


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
