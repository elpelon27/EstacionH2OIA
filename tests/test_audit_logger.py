#!/usr/bin/env python3
"""Tests FASE 5: audit logger (eventos, no-geocerca, retención)."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "security"))
import audit_logger as al  # noqa: E402

PASS, FAIL = 0, 0


def check(name, cond):
    global PASS, FAIL
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if cond:
        PASS += 1
    else:
        FAIL += 1


def main():
    al.DB_PATH = Path("/tmp/security_test_audit.db")
    if al.DB_PATH.exists():
        al.DB_PATH.unlink()
    al.init_db()

    print("1) Cada evento se loguea correctamente")
    ids = {}
    for ev in ["mensaje_entrante", "cliente_bloqueado", "cliente_observacion",
               "ataque_coordinado_detectado", "operador_decision",
               "pago_confirmado", "intento_fallo_acceso"]:
        ids[ev] = al.log_event(ev, phone="+58 412-1234567",
                               ip_origin="156.255.155.24:54321",
                               details={"test": True}, action_taken="nada")
    check("7 tipos registrados con id", all(i > 0 for i in ids.values()))
    evs = al.get_events(limit=50)
    check("7 eventos en log", len(evs) >= 7)
    tipos = {e["event_type"] for e in evs}
    check("todos los tipos presentes", tipos >= al.EVENT_TYPES)

    print("2) Teléfono normalizado + detalles como JSON")
    e = al.get_events(event_type="mensaje_entrante", phone="+584121234567")[0]
    check("teléfono guardado en dígitos", e["phone"] == "584121234567")
    import json
    check("details_json parseable", json.loads(e["details_json"]) == {"test": True})

    print("3) cliente_fuera_geocerca NO se loguea (rechazado por diseño)")
    try:
        al.log_event("cliente_fuera_geocerca", phone="584121234567")
        check("fuera_geocerca rechazado", False)
    except ValueError:
        check("fuera_geocerca rechazado con ValueError", True)
    check("no quedó en el log", len(al.get_events(event_type="cliente_fuera_geocerca")) == 0)

    print("4) Tipo inválido rechazado")
    try:
        al.log_event("evento_inventado")
        check("tipo inválido rechazado", False)
    except ValueError:
        check("tipo inválido rechazado", True)

    print("5) Retención 3 años (no se borra antes)")
    # insertar evento con 2 años de antigüedad → NO debe purgarse
    c = al._conn()
    with c:
        c.execute("INSERT INTO security_audit_log(timestamp, event_type) VALUES(?,?)",
                  (time.time() - 2 * 365 * 24 * 3600, "mensaje_entrante"))
    c.close()
    # insertar evento con 4 años → DEBE purgarse
    c = al._conn()
    with c:
        c.execute("INSERT INTO security_audit_log(timestamp, event_type) VALUES(?,?)",
                  (time.time() - 4 * 365 * 24 * 3600, "mensaje_entrante"))
    c.close()
    purged = al.purge_expired()
    check("evento >3y purgado", purged == 1)
    v = al.verify_retention()
    check("evento 2y sobrevive", v["total"] >= 8)
    check("retención configurada a 3 años", v["retention_years"] == 3)

    print("6) Consulta por teléfono (historial para /cliente_info)")
    hist = al.get_events(phone="584121234567", limit=100)
    check("historial del teléfono existe", len(hist) >= 7)

    print(f"\nRESULTADO: {PASS} OK / {FAIL} FAIL")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
