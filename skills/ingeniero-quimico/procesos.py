#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""procesos.py — la calculadora de procesos de Empédocles (Ingeniero Químico).

Stdlib puro (patrón de la casa, como descarga-libros). Constantes documentadas
con su nivel de honestidad:
  (A) verificado en biblioteca/documento de la casa (se cita)
  (B) principio del pensum / valor típico de manual — VERIFICAR en la misión
      bibliográfica antes de usar en diseño final
  (C) hipótesis por ensayar (no se calcula aquí: se mide)

Regla de la casa: lo que este script no puede calcular, se marca (C) y se
diseña el ensayo — NUNCA se rellena con un número inventado.

Uso:
  python3 procesos.py --help
  python3 procesos.py cloro --volumen-l 1000 --dosis-mgl 2 --solucion-pct 5
  python3 procesos.py dureza --ca-mgl 60 --mg-mgl 24
  python3 procesos.py tds --conductividad-us 1200
  python3 procesos.py ro --tds-mgl 2500 --recuperacion-pct 50
  python3 procesos.py liofilizacion --masa-kg 15 --humedad-pct 90
  python3 procesos.py compost --componentes "estiércol:300" "rastrojo:100"
  python3 procesos.py ensilaje --componentes "pasto:900:25" "maíz:100:35"
  python3 procesos.py <cmd> ... --json      # salida JSON
"""

import argparse
import json
import sys

# ─── Constantes (nivel (B) salvo indicación) ────────────────────────────────

# 1 L de solución de hipoclorito al X% p/v aporta X gramos de NaOCl por litro;
# cloro "libre" entregado ≈ masa de NaOCl × (70.9/74.4) (peso molecular
# Cl2/NaOCl) — química general del pensum [0441 Química General].
NAOCL_A_CL2 = 70.9 / 74.4

# Dureza como CaCO3 (mg/L) = Ca(mg/L)×2.50 + Mg(mg/L)×4.12
# (pesos equivalentes CaCO3/Ca = 100/40.08, CaCO3/Mg = 100/24.31) [0447 Q.A.I.]
FACT_CA = 100.08 / 40.08   # ≈ 2.497
FACT_MG = 100.08 / 24.31   # ≈ 4.119

# TDS ≈ conductividad × factor 0.55-0.75 (típico 0.64 para aguas neutras)
# [5484 Potabilización, verificar por análisis iónico]
TDS_FACTOR_MIN, TDS_FACTOR_TYP, TDS_FACTOR_MAX = 0.55, 0.64, 0.75

# Presión osmótica aproximada para aguas dominadas por NaCl:
# π ≈ 0.77 bar por cada g/L de TDS (agua de mar 35 g/L ≈ 27 bar, consistente)
# [5311 Termodinámica del Equilibrio — van't Hoff, verificar con análisis real]
PI_BAR_PER_GL = 0.77

# Hielo: densidad 0.917 kg/L (sublimando, el volumen del condensador se cobra
# en litros de hielo). [5301 Mecánica de Fluidos]
HIELO_DENSIDAD = 0.917  # kg/L

# Calor latente de sublimación del hielo a condiciones de liofilización
# ≈ 2.840 kJ/kg (≈ 46,5 kJ/mol) [5302 Transferencia de Calor, (B) manual]
DH_SUBL = 2840.0  # kJ/kg

# C:N típicos (B) — manual de compostaje; VERIFICAR con análisis en la misión
# bibliográfica antes de diseñar. Clave = texto del componente.
CN_TABLA = {
    "estiercol": 18,        # estiércol bovino fresco ~15-25:1
    "estiercol-ovino": 16,  # ~13-20:1
    "rastrojo": 80,         # pajas/rastrojos secos 60-100:1
    "hojas": 40,
    "pasto": 20,            # pasto verde cortado 15-25:1
    "melaza": 100,          # carbono rápido ~100:1 (aprox.)
    "cachaza": 12,
    "cal compost": 0,       # no aplica
}
CN_DEFECTO = None  # si no está en tabla ni override → ERROR (no se inventa)


def _ok(nombre, resultado, notas):
    return {"comando": nombre, "estado": "ok", "resultado": resultado,
            "notas": notas}


def cmd_cloro(a):
    """Dosis de cloro por volumen: mg/L objetivo → mL de solución al X%."""
    if a.volumen_l <= 0 or a.dosis_mgl < 0 or not 0 < a.solucion_pct <= 100:
        sys.exit("ERROR: revisa volumen-l (>0), dosis-mgl (>=0) y solucion-pct (0-100].")
    g_cl2 = a.dosis_mgl * a.volumen_l / 1000.0          # mg/L × L → g Cl2
    g_naocl = g_cl2 / NAOCL_A_CL2
    g_por_litro_sol = a.solucion_pct * 10.0             # %p/v → g/100mL ×10
    ml_sol = g_naocl / g_por_litro_sol * 1000.0
    return _ok("cloro", {
        "volumen_L": a.volumen_l,
        "dosis_objetivo_mg_L_cl2": a.dosis_mgl,
        "cl2_puro_necesario_g": round(g_cl2, 2),
        "solucion_pct": a.solucion_pct,
        "solucion_necesaria_ml": round(ml_sol, 1),
    }, [
        "Química: NaOCl→Cl2 equivalente ×%.3f (B) [0441]." % NAOCL_A_CL2,
        "La DOSIS OBJETIVO debe salir de norma/criterio (p. ej. residual libre "
        "0,2-0,5 mg/L en agua envasada según norma aplicable) — NO la inventes; "
        "ajusta por demanda de cloro del agua (C, test de demanda).",
    ])


def cmd_dureza(a):
    """Ca y Mg (mg/L) → dureza como CaCO3 + clasificación (B)."""
    if a.ca_mgl < 0 or a.mg_mgl < 0:
        sys.exit("ERROR: ca-mgl y mg-mgl deben ser >= 0.")
    d = a.ca_mgl * FACT_CA + a.mg_mgl * FACT_MG
    if d < 60:
        clase = "blanda"
    elif d < 120:
        clase = "moderadamente dura"
    elif d < 180:
        clase = "dura"
    else:
        clase = "muy dura"
    return _ok("dureza", {
        "dureza_CaCO3_mg_L": round(d, 1),
        "aporte_Ca": round(a.ca_mgl * FACT_CA, 1),
        "aporte_Mg": round(a.mg_mgl * FACT_MG, 1),
        "clasificacion_B": clase,
    }, [
        "Equivalencias CaCO3/Ca=%.3f, CaCO3/Mg=%.3f (B) [0447]." % (FACT_CA, FACT_MG),
        "Umbrales de clasificación: típicos de manual (B) — verificar en la "
        "misión bibliográfica L6 (agua).",
    ])


def cmd_tds(a):
    """Conductividad (µS/cm) → TDS estimado por factor (B)."""
    if a.conductividad_us <= 0:
        sys.exit("ERROR: conductividad-us debe ser > 0.")
    return _ok("tds", {
        "conductividad_uS_cm": a.conductividad_us,
        "tds_mg_L_min": round(a.conductividad_us * TDS_FACTOR_MIN, 0),
        "tds_mg_L_tipico": round(a.conductividad_us * TDS_FACTOR_TYP, 0),
        "tds_mg_L_max": round(a.conductividad_us * TDS_FACTOR_MAX, 0),
    }, [
        "Estimación (B) [5484]: el factor 0,55-0,75 depende de la composición "
        "iónica — el análisis iónico real lo sustituye (deuda hasta tenerlo).",
    ])


def cmd_ro(a):
    """TDS de alimentación + recuperación % → concentrado y π (B, NaCl-like)."""
    if a.tds_mgl <= 0 or not 0 < a.recuperacion_pct < 100:
        sys.exit("ERROR: tds-mgl > 0 y recuperacion-pct en (0,100).")
    r = a.recuperacion_pct / 100.0
    tds_conc = a.tds_mgl / (1.0 - r)  # sin paso de sal (aprox. conservadora)
    pi_feed = a.tds_mgl / 1000.0 * PI_BAR_PER_GL
    pi_conc = tds_conc / 1000.0 * PI_BAR_PER_GL
    return _ok("ro", {
        "tds_alimentacion_mg_L": a.tds_mgl,
        "recuperacion_pct": a.recuperacion_pct,
        "tds_concentrado_mg_L": round(tds_conc, 0),
        "presion_osmotica_alim_bar": round(pi_feed, 2),
        "presion_osmotica_conc_bar": round(pi_conc, 2),
        "presion_bomba_minima_bar": round(pi_conc + 3.0, 1),
    }, [
        "π ≈ 0,77 bar por g/L TDS para aguas tipo NaCl (B) [5311/5484] — con "
        "análisis iónico real se recalcula.",
        "Presión de bomba ≈ π_concentrado + margen de permeación (~3 bar es "
        "orden de magnitud para espiral BW, (B)) — la especifica el fabricante "
        "de la membrana; NO cotizar bomba con este número solo.",
        "Energía específica: depende de bomba y recuperador — rango típico "
        "sistemas salobres pequeños 1-3 kWh/m³ (B, verificar L6/L8); medir en "
        "planta (C).",
    ])


def cmd_liofilizacion(a):
    """Masa del lote y humedad → carga de hielo y energía térmica de sublimación."""
    if a.masa_kg <= 0 or not 0 <= a.humedad_pct <= 100:
        sys.exit("ERROR: masa-kg > 0 y humedad-pct en [0,100].")
    agua = a.masa_kg * a.humedad_pct / 100.0
    energia_kj = agua * DH_SUBL
    return _ok("liofilizacion", {
        "masa_lote_kg": a.masa_kg,
        "humedad_pct": a.humedad_pct,
        "agua_a_sublimar_kg": round(agua, 2),
        "hielo_a_condensar_L": round(agua / HIELO_DENSIDAD, 2),
        "energia_termica_GJ": round(energia_kj / 1e6, 3),
        "energia_termica_kWh_t": round(energia_kj / 3600.0, 1),
    }, [
        "ΔH_sub ≈ 2.840 kJ/kg (B) [5302]; densidad hielo 0,917 kg/L (B).",
        "1 kg de hielo ≈ 1,09 L de capacidad de condensador — el dato "
        "'15-18 L hielo/lote' de la máquina recomendada (A, estudio "
        "liofilización v1.0) equivale a ~13,7-16,5 kg de agua por lote.",
        "La energía ELÉCTRICA real del lote depende del compresor/vacío y del "
        "tiempo (C): medir kW promedio × horas en la fase 0.",
    ])


def _sin_acentos(t):
    """Normaliza acentos para que 'Estiércol' matchee 'estiercol' en las tablas."""
    return (t.replace("á", "a").replace("é", "e").replace("í", "i")
             .replace("ó", "o").replace("ú", "u").replace("ñ", "n").lower())


def _parse_comp(s):
    """'nombre:masa[:cn|:dm_pct]' → (nombre, float, float|None)."""
    partes = [p.strip() for p in s.split(":")]
    if len(partes) < 2:
        sys.exit("ERROR: componente '%s' debe ser 'nombre:valor[:extra]'." % s)
    try:
        val = float(partes[1].replace(",", "."))
        extra = float(partes[2].replace(",", ".")) if len(partes) > 2 else None
    except ValueError:
        sys.exit("ERROR: valores numéricos inválidos en '%s'." % s)
    return _sin_acentos(partes[0]), val, extra


def cmd_compost(a):
    """Mezcla 'nombre:masa_kg[:CN_override]' → C:N ponderado aproximado."""
    if not a.componentes:
        sys.exit("ERROR: indica --componentes \"nombre:masa\" ...")
    total, suma = 0.0, 0.0
    detalle = []
    for s in a.componentes:
        nombre, masa, cn = _parse_comp(s)
        if masa <= 0:
            sys.exit("ERROR: masa > 0 en '%s'." % s)
        if cn is None:
            cn = CN_TABLA.get(nombre, CN_DEFECTO)
            if cn is None:
                sys.exit("ERROR: sin C:N conocido para '%s' — pásalo explícito "
                         "'%s:masa:CN' (no se inventa)." % (nombre, nombre))
            fuente = "tabla (B)"
        else:
            fuente = "override"
        total += masa
        suma += masa * cn
        detalle.append({"componente": nombre, "masa_kg": masa,
                        "C_N": cn, "fuente": fuente})
    cn_mezcla = suma / total
    if cn_mezcla < 20:
        aviso = "mezcla rica en N: riesgo de amoníaco/olor — subir carbono"
    elif cn_mezcla > 40:
        aviso = "mezcla rica en C: fermentación lenta — bajar carbono o esperar"
    else:
        aviso = "en rango objetivo ~25-30:1 (B) — compostaje vigoroso"
    return _ok("compost", {"C_N_mezcla": round(cn_mezcla, 1),
                           "masa_total_kg": total,
                           "diagnostico_B": aviso,
                           "componentes": detalle},
               ["Aproximación por masa (asume %C similar entre componentes) "
                "(B) — manual de compostaje; tabla típica verificable en "
                "biblioteca (Restrepo)."])


def cmd_ensilaje(a):
    """Mezcla 'forraje:kg:DM%' → MS de la mezcla + recordatorio de objetivo."""
    if not a.componentes:
        sys.exit("ERROR: indica --componentes \"forraje:kg:DM_pct\" ...")
    total = ms_total = 0.0
    detalle = []
    for s in a.componentes:
        nombre, kg, dm = _parse_comp(s)
        if kg <= 0 or dm is None or not 0 < dm <= 100:
            sys.exit("ERROR: componente '%s' exige masa>0 y DM_pct en (0,100].")
        total += kg
        ms_total += kg * dm / 100.0
        detalle.append({"forraje": nombre, "kg": kg, "DM_pct": dm,
                        "MS_kg": round(kg * dm / 100.0, 2)})
    dm_pct = ms_total / total * 100.0
    if dm_pct < 25:
        aviso = "MS<25%%: riesgo de efluentes y fermentación butírica (B)"
    elif dm_pct < 30:
        aviso = "MS %.0f%%: aceptable pero justo — apuntar a 30-35%% con pre-oreo (B)" % dm_pct
    elif dm_pct <= 40:
        aviso = "MS %.0f%%: en rango 30-35%% típico de buen silaje (B)" % dm_pct
    else:
        aviso = "MS>40%%: difícil compactar/sellar — riesgo de mohos (B)"
    return _ok("ensilaje", {"MS_pct_mezcla": round(dm_pct, 1),
                            "masa_total_kg": total,
                            "MS_total_kg": round(ms_total, 2),
                            "diagnostico_B": aviso,
                            "componentes": detalle},
               ["Objetivo de proceso: anaerobiosis en <48 h y pH final "
                "3,8-4,5 (B) [5313 Cinética + biblioteca de forrajes]."])


def construir_parser():
    p = argparse.ArgumentParser(
        prog="procesos.py",
        description="Calculadora de procesos de Empédocles (Estación H2O). "
                    "Constantes marcadas (A)/(B)/(C) según el SKILL.md.")
    p.add_argument("--json", action="store_true",
                   help="salida en JSON (para scripts/Hermes)")
    json_parent = argparse.ArgumentParser(add_help=False)
    json_parent.add_argument("--json", action="store_true",
                             help="salida en JSON (para scripts/Hermes)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def sp(name, help_):
        return sub.add_parser(name, help=help_, parents=[json_parent])

    s = sp("cloro", "dosis de cloro → mL de solución")
    s.add_argument("--volumen-l", type=float, required=True,
                   help="volumen a tratar (L)")
    s.add_argument("--dosis-mgl", type=float, required=True,
                   help="dosis objetivo de Cl2 (mg/L) — de norma/criterio")
    s.add_argument("--solucion-pct", type=float, default=5.0,
                   help="%% p/v de NaOCl de la solución (default 5)")
    s.set_defaults(fn=cmd_cloro)

    s = sp("dureza", "Ca+Mg → dureza como CaCO3")
    s.add_argument("--ca-mgl", type=float, required=True, help="calcio mg/L")
    s.add_argument("--mg-mgl", type=float, required=True, help="magnesio mg/L")
    s.set_defaults(fn=cmd_dureza)

    s = sp("tds", "conductividad → TDS estimado")
    s.add_argument("--conductividad-us", type=float, required=True,
                   help="conductividad (µS/cm)")
    s.set_defaults(fn=cmd_tds)

    s = sp("ro", "salobre: concentrado, π y presión de bomba")
    s.add_argument("--tds-mgl", type=float, required=True,
                   help="TDS del agua cruda (mg/L)")
    s.add_argument("--recuperacion-pct", type=float, required=True,
                   help="recuperación deseada (%%)")
    s.set_defaults(fn=cmd_ro)

    s = sp("liofilizacion",
           "lote: hielo a condensar y energía de sublimación")
    s.add_argument("--masa-kg", type=float, required=True,
                   help="masa del lote (kg)")
    s.add_argument("--humedad-pct", type=float, required=True,
                   help="humedad de la materia prima (%% p/p)")
    s.set_defaults(fn=cmd_liofilizacion)

    s = sp("compost", "mezcla → C:N ponderado")
    s.add_argument("--componentes", nargs="+", required=True,
                   help="'nombre:masa_kg[:CN]' — varios separados por espacio")
    s.set_defaults(fn=cmd_compost)

    s = sp("ensilaje", "mezcla → materia seca")
    s.add_argument("--componentes", nargs="+", required=True,
                   help="'forraje:kg:DM_pct' — varios separados por espacio")
    s.set_defaults(fn=cmd_ensilaje)
    return p


def main(argv=None):
    a = construir_parser().parse_args(argv)
    out = a.fn(a)
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
