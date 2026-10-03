"""
Mapa de bancos de Venezuela + normalizador difuso.

Fuente ÚNICA de códigos: gist arodu/banks_venezuela.csv
https://gist.github.com/arodu/af242b5e3d7fc4e4fb2710c76ec41fae
(verificado 2026-10-03; comentario del gist también apunta al listado oficial
del BCV "Instituciones de Banca Activas en el SCC"). NO inventar códigos.

Uso:
    from scripts.banks_ve import normalize_bank
    normalize_bank("mercantil")   -> "0105"
    normalize_bank("0105")       -> "0105"
    normalize_bank("bnc")        -> "0191"
    normalize_bank("bancaribe")  -> "0114"
    normalize_bank("bnkCaribe")  -> "0114"  (fuzzy)
    normalize_bank("xyz")        -> None
"""

import difflib
import re

# (código, nombre oficial del gist) — NO editar sin fuente oficial.
BANCOS_VE: dict[str, str] = {
    "0102": "BANCO DE VENEZUELA",
    "0104": "BANCO VENEZOLANO DE CREDITO",
    "0105": "BANCO MERCANTIL",
    "0108": "BBVA PROVINCIAL",
    "0114": "BANCARIBE",
    "0115": "BANCO EXTERIOR",
    "0128": "BANCO CARONI",
    "0134": "BANESCO",
    "0137": "BANCO SOFITASA",
    "0138": "BANCO PLAZA",
    "0146": "BANGENTE",
    "0151": "BANCO FONDO COMUN",
    "0156": "100% BANCO",
    "0157": "DELSUR BANCO UNIVERSAL",
    "0163": "BANCO DEL TESORO",
    "0168": "BANCRECER",
    "0169": "R4 BANCO MICROFINANCIERO C.A.",
    "0171": "BANCO ACTIVO",
    "0172": "BANCAMIGA BANCO UNIVERSAL, C.A.",
    "0173": "BANCO INTERNACIONAL DE DESARROLLO",
    "0174": "BANPLUS",
    "0175": "BANCO DIGITAL DE LOS TRABAJADORES, BANCO UNIVERSAL",
    "0177": "BANFANB",
    "0178": "N58 BANCO DIGITAL BANCO MICROFINANCIERO S A",
    "0191": "BANCO NACIONAL DE CREDITO",
}

# Alias y acrónimos de uso común → código del gist.
# Cada alias mapea EXCLUSIVAMENTE a códigos presentes en BANCOS_VE.
ALIAS_VE: dict[str, str] = {
    "bdv": "0102",
    "banco de venezuela": "0102",
    "venezolano de credito": "0104",
    "bvc": "0104",
    "mercantil": "0105",
    "provincial": "0108",
    "bbva": "0108",
    "bbva provincial": "0108",
    "bancaribe": "0114",
    "exterior": "0115",
    "caroni": "0128",
    "banesco": "0134",
    "sofitasa": "0137",
    "plaza": "0138",
    "banco plaza": "0138",
    "bangente": "0146",
    "fondo comun": "0151",
    "banco fondo comun": "0151",
    "100% banco": "0156",
    "100 banco": "0156",
    "delsur": "0157",
    "tesoro": "0163",
    "banco del tesoro": "0163",
    "bancrecer": "0168",
    "r4": "0169",
    "r4 banco microfinanciero": "0169",
    "activo": "0171",
    "banco activo": "0171",
    "bancamiga": "0172",
    "bid": "0173",
    "internacional de desarrollo": "0173",
    "banplus": "0174",
    "bdt": "0175",
    "digital de los trabajadores": "0175",
    "banfanb": "0177",
    "n58": "0178",
    "bnc": "0191",
    "banco nacional de credito": "0191",
}

# Umbrales de matching difuso
_FUZZY_CUTOFF = 0.82

_STOPWORDS = {"banco", "de", "del", "la", "el", "ca", "s", "a", "universal", "c", "u"}


def _limpiar(texto: str) -> str:
    """Normaliza para comparación: minúsculas, sin tildes ni puntuación."""
    t = (texto or "").strip().lower()
    t = re.sub(r"[áàäâ]", "a", t)
    t = re.sub(r"[éèëê]", "e", t)
    t = re.sub(r"[íìïî]", "i", t)
    t = re.sub(r"[óòöô]", "o", t)
    t = re.sub(r"[úùüû]", "u", t)
    t = re.sub(r"[^a-z0-9% ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _quitar_stopwords(nombre: str) -> str:
    """Quita palabras genéricas para que 'banco mercantil' ~ 'mercantil'."""
    palabras = [p for p in nombre.split() if p not in _STOPWORDS]
    return " ".join(palabras) if palabras else nombre


def normalize_bank(user_input: str) -> str | None:
    """
    Reconoce un banco por código (4 dígitos), alias/acrónimo o nombre oficial.
    Búsqueda difusa tolerante a typos. Returns código "0105" o None.
    """
    if not user_input:
        return None

    limpio = _limpiar(user_input)

    # 1) Código directo (4 dígitos, con o sin ceros a la izquierda)
    if re.fullmatch(r"\d{1,4}", limpio):
        codigo = limpio.zfill(4)
        return codigo if codigo in BANCOS_VE else None

    # 2) Alias exacto (limpio o sin stopwords)
    if limpio in ALIAS_VE:
        return ALIAS_VE[limpio]
    sin_sw = _quitar_stopwords(limpio)
    if sin_sw in ALIAS_VE:
        return ALIAS_VE[sin_sw]

    # 3) Nombre oficial exacto
    for codigo, nombre in BANCOS_VE.items():
        if _limpiar(nombre) == limpio or _quitar_stopwords(_limpiar(nombre)) == sin_sw:
            return codigo

    # 4) Fuzzy: mejor match contra alias + nombres oficiales (sin stopwords)
    candidatos: dict[str, str] = {}
    candidatos.update(ALIAS_VE)
    for codigo, nombre in BANCOS_VE.items():
        candidatos[_limpiar(nombre)] = codigo
        candidatos[_quitar_stopwords(_limpiar(nombre))] = codigo

    nombres = list(candidatos.keys())
    matches = difflib.get_close_matches(sin_sw, nombres, n=1, cutoff=_FUZZY_CUTOFF)
    if not matches:
        matches = difflib.get_close_matches(limpio, nombres, n=1, cutoff=_FUZZY_CUTOFF)
    if matches:
        return candidatos[matches[0]]

    return None


def nombre_banco(codigo: str) -> str:
    """Nombre oficial del banco por código ('' si desconocido)."""
    return BANCOS_VE.get((codigo or "").strip().zfill(4), "")


if __name__ == "__main__":
    # Smoke test interactivo
    casos = [
        ("mercantil", "0105"),
        ("0105", "0105"),
        ("105", "0105"),
        ("bnc", "0191"),
        ("Bancaribe", "0114"),
        ("bankaribe", "0114"),  # typo → fuzzy
        ("bbva provincial", "0108"),
        ("banco nacional de credito", "0191"),
        ("100% Banco", "0156"),
        ("BANCO DIGITAL DE LOS TRABAJADORES", "0175"),
        ("xyz inventado", None),
        ("0199", None),
    ]
    fallos = 0
    for entrada, esperado in casos:
        resultado = normalize_bank(entrada)
        ok = resultado == esperado
        fallos += 0 if ok else 1
        print(f"{'OK ' if ok else 'FAIL'} {entrada!r} -> {resultado} (esperado {esperado})")
    print(f"\n{'TODO OK' if fallos == 0 else f'{fallos} FALLOS'}")
    raise SystemExit(1 if fallos else 0)
