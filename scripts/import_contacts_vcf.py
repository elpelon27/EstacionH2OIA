#!/usr/bin/env python3
"""
Importador de contactos vCard (.vcf) para Estación H2O.

Lee data/whatsapp_exports/contacts.vcf, parsea cada vCard, extrae:
  - Nombre (FN o N)
  - Teléfono (TEL, item1.TEL)
  - Email (EMAIL)
  - Notas (NOTE)
  - Organización (ORG)

Filtra solo contactos con teléfono venezolano (+58 o formato 04xx/02xx).
Normaliza teléfonos: quita espacios/guiones, asegura +58.

Genera:
  a) docs/clientes-activos/<slug>.json   (un JSON por cliente)
  b) docs/clientes-activos/_index.md     (resumen consolidado)
  c) docs/clientes-activos/_odoo_import.csv (CSV para res.partner Odoo)

Idempotente: si se re-ejecuta, sobrescribe sin duplicar.
"""

from __future__ import annotations

import csv
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

# ─── Config ────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
VCF_PATH = PROJECT_ROOT / "data" / "whatsapp_exports" / "contacts.vcf"
OUTPUT_DIR = PROJECT_ROOT / "docs" / "clientes-activos"
INDEX_MD = OUTPUT_DIR / "_index.md"
ODOO_CSV = OUTPUT_DIR / "_odoo_import.csv"

# ─── Helpers ───────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    """Convierte texto a slug seguro para nombre de archivo."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:60] if text else "sin-nombre"


def normalize_phone(raw: str) -> str | None:
    """
    Normaliza un teléfono venezolano:
      - Quita espacios, guiones, paréntesis
      - Convierte 0412xxxxxxxx → +58412xxxxxxxx
      - Convierte 0424xxxxxxxx → +58424xxxxxxxx
      - Convierte +58xxxxxxxxxx → +58xxxxxxxxxx (sin cambios)
      - Rechaza números con asteriscos (privacidad Google)
      - Rechaza números que no sean venezolanos
    """
    if not raw:
        return None
    # Limpiar
    phone = re.sub(r"[\s\-\(\)\.]", "", raw.strip())
    # Quitar prefijos tipo "tel:" o "item1."
    phone = re.sub(r"^(tel:|item1\.)", "", phone, flags=re.IGNORECASE)

    # Rechazar si tiene asteriscos (número enmascarado por Google Contacts)
    if "*" in phone:
        return None

    # Ya tiene +58
    if phone.startswith("+58"):
        rest = phone[3:]
        if len(rest) == 10 and rest[0] in ("4", "2"):
            return f"+58{rest}"
        return None

    # Formato 058 (algunos contactos lo traen)
    if phone.startswith("058"):
        rest = phone[3:]
        if len(rest) == 10 and rest[0] in ("4", "2"):
            return f"+58{rest}"
        return None

    # Formato 04xx o 02xx (sin prefijo internacional)
    if len(phone) == 11 and phone[0] == "0" and phone[1] in ("4", "2"):
        return f"+58{phone[1:]}"

    # Formato 4xx o 2xx (10 dígitos sin el 0)
    if len(phone) == 10 and phone[0] in ("4", "2"):
        return f"+58{phone}"

    # No coincide con patrón venezolano
    return None


def parse_vcf_line_prefix(line: str) -> str:
    """Extrae el valor después de los dos puntos de una línea vCard."""
    # Separar en la primera aparición de ':' (no codificada)
    if ":" not in line:
        return ""
    return line.split(":", 1)[1].strip()


def parse_vcf(content: str) -> list[dict[str, str | None]]:
    """
    Parsea el contenido completo de un .vcf y retorna lista de contactos.
    Cada contacto es un dict con keys: name, phone, email, note, org.
    """
    contacts: list[dict[str, str | None]] = []
    current: dict[str, str | None] | None = None

    for raw_line in content.splitlines():
        line = raw_line.strip().rstrip("\r")
        if not line:
            continue

        if line.upper().startswith("BEGIN:VCARD"):
            current = {"name": None, "phone": None, "email": None, "note": None, "org": None}
            continue

        if line.upper().startswith("END:VCARD"):
            if current is not None:
                # Solo guardar si tiene al menos un teléfono o nombre
                if current.get("name") or current.get("phone"):
                    contacts.append(current)
                current = None
            continue

        if current is None:
            continue

        # FN: (Full Name) — nombre completo
        if line.upper().startswith("FN:") or line.upper().startswith("FN;"):
            current["name"] = parse_vcf_line_prefix(line) or current["name"]

        # N: (Structured Name) — apellido;nombre;;;
        elif line.upper().startswith("N:") or line.upper().startswith("N;"):
            n_val = parse_vcf_line_prefix(line)
            if n_val and not current.get("name"):
                parts = n_val.split(";")
                if len(parts) >= 2:
                    last = parts[0].strip()
                    first = parts[1].strip()
                    current["name"] = f"{first} {last}".strip() or n_val
                else:
                    current["name"] = n_val

        # TEL (todos los formatos: TEL, TEL;TYPE=CELL, TEL;TYPE=WORK, item1.TEL)
        elif line.upper().startswith("TEL") or line.upper().startswith("ITEM1.TEL"):
            tel_val = parse_vcf_line_prefix(line)
            if tel_val and not current.get("phone"):
                current["phone"] = tel_val
            elif tel_val and current.get("phone"):
                # Si ya hay phone, guardar como secundario si el primero no era válido
                pass

        # EMAIL
        elif line.upper().startswith("EMAIL") or line.upper().startswith("ITEM1.EMAIL"):
            current["email"] = parse_vcf_line_prefix(line) or current["email"]

        # NOTE
        elif line.upper().startswith("NOTE") or line.upper().startswith("ITEM1.NOTE"):
            current["note"] = parse_vcf_line_prefix(line) or current["note"]

        # ORG
        elif line.upper().startswith("ORG:") or line.upper().startswith("ORG;"):
            current["org"] = parse_vcf_line_prefix(line) or current["org"]

    return contacts


# ─── Main ──────────────────────────────────────────────────────────────

def main() -> int:
    if not VCF_PATH.exists():
        print(f"ERROR: No existe {VCF_PATH}")
        return 1

    print(f"Leyendo: {VCF_PATH}")
    content = VCF_PATH.read_text(encoding="utf-8", errors="replace")
    raw_contacts = parse_vcf(content)
    print(f"Contactos vCard parseados: {len(raw_contacts)}")

    # Filtrar + normalizar teléfonos venezolanos
    ve_contacts: list[dict[str, str | None]] = []
    skipped_no_phone = 0
    skipped_masked = 0
    skipped_not_ve = 0

    for c in raw_contacts:
        raw_phone = c.get("phone")
        if not raw_phone:
            skipped_no_phone += 1
            continue

        norm = normalize_phone(raw_phone)
        if norm is None:
            if "*" in (raw_phone or ""):
                skipped_masked += 1
            else:
                skipped_not_ve += 1
            continue

        c["phone"] = norm  # Reemplazar con normalizado
        ve_contacts.append(c)

    print(f"Contactos con teléfono venezolano (+58): {len(ve_contacts)}")
    print(f"  - Sin teléfono: {skipped_no_phone}")
    print(f"  - Enmascarados (****): {skipped_masked}")
    print(f"  - No venezolanos: {skipped_not_ve}")

    # Crear directorio de salida
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Limpiar JSONs anteriores (idempotente)
    for old in OUTPUT_DIR.glob("*.json"):
        old.unlink()

    # a) Generar un JSON por cliente
    for c in ve_contacts:
        name = c.get("name") or "Sin Nombre"
        slug = slugify(name)
        out_path = OUTPUT_DIR / f"{slug}.json"
        data = {
            "nombre": name,
            "telefono": c.get("phone"),
            "email": c.get("email"),
            "notas": c.get("note"),
            "organizacion": c.get("org"),
            "importe_date": datetime.now().strftime("%Y-%m-%d"),
            "source": "contacts.vcf",
        }
        out_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # b) Generar _index.md (resumen consolidado)
    lines_md = [
        "# Clientes Activos — Estación H2O",
        "",
        f"**Fecha de importación**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Archivo fuente**: `data/whatsapp_exports/contacts.vcf`",
        f"**Total contactos vCard**: {len(raw_contacts)}",
        f"**Contactos con teléfono venezolano (+58)**: {len(ve_contacts)}",
        f"  - Sin teléfono: {skipped_no_phone}",
        f"  - Enmascarados (****): {skipped_masked}",
        f"  - No venezolanos: {skipped_not_ve}",
        "",
        "## Listado de Clientes",
        "",
        "| # | Nombre | Teléfono | Email | Organización |",
        "|---|--------|-----------|-------|--------------|",
    ]
    for i, c in enumerate(sorted(ve_contacts, key=lambda x: (x.get("name") or "").lower()), 1):
        name = c.get("name") or "Sin Nombre"
        phone = c.get("phone") or ""
        email = c.get("email") or "—"
        org = c.get("org") or "—"
        lines_md.append(f"| {i} | {name} | {phone} | {email} | {org} |")
    lines_md.append("")
    INDEX_MD.write_text("\n".join(lines_md), encoding="utf-8")

    # c) Generar CSV para Odoo (res.partner)
    with open(ODOO_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "name",
                "phone",
                "mobile",
                "email",
                "comment",
                "is_company",
                "customer_rank",
            ],
        )
        writer.writeheader()
        for c in sorted(ve_contacts, key=lambda x: (x.get("name") or "").lower()):
            name = c.get("name") or "Sin Nombre"
            phone = c.get("phone") or ""
            email = c.get("email") or ""
            note = c.get("note") or ""
            org = c.get("org") or ""
            comment_parts = []
            if org:
                comment_parts.append(f"ORG: {org}")
            if note:
                comment_parts.append(f"NOTA: {note}")
            comment = " | ".join(comment_parts) if comment_parts else ""
            writer.writerow({
                "name": name,
                "phone": phone,
                "mobile": phone,  # Móvil = mismo número en Venezuela
                "email": email,
                "comment": comment,
                "is_company": "1" if org else "0",
                "customer_rank": "1",
            })

    print(f"\nArchivos generados:")
    print(f"  JSONs individuales: {len(ve_contacts)} archivos en {OUTPUT_DIR}/")
    print(f"  Resumen: {INDEX_MD}")
    print(f"  CSV Odoo: {ODOO_CSV}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
