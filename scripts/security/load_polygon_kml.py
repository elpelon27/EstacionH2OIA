#!/usr/bin/env python3
"""Carga un polígono KML (Google Earth/Maps) a security.db vía geofence.set_polygon.

Uso:
    python3 scripts/security/load_polygon_kml.py <ruta.kml> "<nombre>" [--dry-run]

- KML guarda coordenadas como "lng,lat,alt" (longitud primero); GeoJSON también
  usa [lng, lat], así que NO hay que invertir el orden al armar el anillo.
- Si hay múltiples polígonos, usa el de mayor área (bbox) y lo reporta.
- NO modifica la lógica de geofence.py (ray casting); solo carga datos.
"""
import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

KML = "{http://www.opengis.net/kml/2.2}"


def parse_kml_rings(kml_path: str) -> list[tuple[str, list[tuple[float, float]]]]:
    """Devuelve [(placemark_name, ring[(lng,lat),...]), ...] de todos los LinearRing."""
    tree = ET.parse(kml_path)
    rings: list[tuple[str, list[tuple[float, float]]]] = []
    for pm in tree.iter(KML + "Placemark"):
        name = (pm.findtext(KML + "name") or "").strip()
        for lr in pm.iter(KML + "LinearRing"):
            coords = lr.findtext(KML + "coordinates")
            if not coords:
                continue
            ring: list[tuple[float, float]] = []
            for c in coords.strip().split():
                parts = c.split(",")
                ring.append((float(parts[0]), float(parts[1])))
            if len(ring) >= 3:
                rings.append((name, ring))
    return rings


def dedupe_rings(rings: list[tuple[str, list[tuple[float, float]]]]):
    """Google Earth duplica el mismo anillo en varios Placemarks; dedupe por primer punto."""
    seen: set[tuple] = set()
    out: list[tuple[str, list[tuple[float, float]]]] = []
    for name, ring in rings:
        key = (ring[0], ring[-1], len(ring))
        if key not in seen:
            seen.add(key)
            out.append((name, ring))
    return out


def bbox_area(ring: list[tuple[float, float]]) -> float:
    lngs = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    return (max(lngs) - min(lngs)) * (max(lats) - min(lats))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("kml")
    ap.add_argument("name")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rings = dedupe_rings(parse_kml_rings(args.kml))
    if not rings:
        print("ERROR: KML sin LinearRing válidos")
        return 1
    for n, r in rings:
        print(f"  anillo: name={n!r} vertices={len(r)}")
    name, ring = max(rings, key=lambda x: bbox_area(x[1]))
    if len(rings) > 1:
        print(f"  → elegido el más grande (bbox): {name!r}")

    geojson = {"type": "Polygon", "coordinates": [[list(p) for p in ring]]}
    if args.dry_run:
        print("DRY-RUN: no se escribe en security.db")
        return 0

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.security.geofence import set_polygon

    pid = set_polygon(args.name, geojson, activate=True)
    print(f"OK: polígono id={pid} name={args.name!r} activo ({len(ring)} vértices)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
