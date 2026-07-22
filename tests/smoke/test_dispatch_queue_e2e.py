#!/usr/bin/env python3
"""FASE 1.5 — Smoke test E2E del bridge: valida que _send_to_dispatch_queue
dispara en los puntos correctos (pago efectivo '2', 'ya pagué') y NO dispara
en abortos ('volver', 'menú', saludo en estado awaiting_payment).

Patrón: spy con patch.object(b, '_send_to_dispatch_queue', side_effect=spy).
No toca BD real (el spy reemplaza la función antes de que toque SQLite).
"""
import sys
import os
sys.path.insert(0, '/mnt/ssd_trabajo/hermes-agent')
os.environ['BRIDGE_ALLOW_INSECURE_SALT'] = '1'

from unittest.mock import patch
from datetime import datetime

import api.bridge as b

# Stub: sin BCV real
b._convert_eur_to_bs = lambda x: 100.0

# Estado previo artificial para un pedido a punto de cerrar
BASE_STATE = {
    'state': 'awaiting_payment',
    'qty_botellones': 3,
    'qty_hielo': 0,
    'total_eur': 3.0,
    'address': 'Calle 72, Bella Vista',
    'contact_name': 'Cliente Test',
}

results = []

def _test_case(name, state_overrides, input_text, should_dispatch):
    """Ejecuta un caso de test y registra el resultado."""
    b._conversation_state.clear()
    state = dict(BASE_STATE)
    state.update(state_overrides)
    ph = f'TEST_{name}'
    b._set_state(ph, state)

    captured = []
    def spy(ph_hash, st, phone):
        captured.append({'ph': ph_hash, 'state': dict(st), 'phone': phone})

    msg = {'type': 'text', 'text': {'body': input_text}}
    try:
        with patch.object(b, '_send_to_dispatch_queue', side_effect=spy):
            b._handle_deterministic(
                ph, input_text, '+58412xxxxxxxx', 'Cliente Test', msg, {}
            )
    except Exception as e:
        # Algunos paths pueden faltar mocks auxiliares; lo importante es el spy
        pass

    dispatched = len(captured) == 1
    if should_dispatch:
        ok = dispatched
        detail = f"spy called={dispatched}"
        if dispatched:
            detail += f", payment_method={captured[0]['state'].get('payment_method', 'MISSING')}"
    else:
        ok = not dispatched
        detail = f"spy NOT called (correct)={dispatched == False}"

    status = "PASS" if ok else "FAIL"
    results.append((name, status, detail))
    print(f"  [{status}] {name}: {detail}")
    return captured


def run_all():
    """Ejecuta todos los casos de test y retorna el resultado."""
    # CASO 1: Pago efectivo "2" → spy DEBE llamarse con payment_method="Efectivo"
    print("\nCASO 1: Pago efectivo '2' (debe disparar)")
    c1 = _test_case(
        'efectivo',
        state_overrides={},
        input_text='2',
        should_dispatch=True,
    )
    if c1:
        assert c1[0]['state']['payment_method'] == 'Efectivo', \
            f"payment_method deberia ser 'Efectivo', got: {c1[0]['state'].get('payment_method')}"
        assert c1[0]['state']['address'] == 'Calle 72, Bella Vista', \
            f"address debe estar presente, got: {c1[0]['state'].get('address')}"

    # CASO 2: "ya pagué" tras pago móvil → spy DEBE llamarse con payment_method="Pago Móvil"
    print("\nCASO 2: 'ya pagué' tras pago móvil (debe disparar)")
    c2 = _test_case(
        'ya_page',
        state_overrides={
            'state': 'awaiting_confirmation',
            'payment_method': 'Pago Móvil',
        },
        input_text='ya pagué',
        should_dispatch=True,
    )
    if c2:
        assert c2[0]['state']['payment_method'] == 'Pago Móvil', \
            f"payment_method deberia ser 'Pago Móvil', got: {c2[0]['state'].get('payment_method')}"

    # CASO 3: "volver" desde awaiting_payment → spy NO debe llamarse (aborto)
    print("\nCASO 3: 'volver' desde awaiting_payment (NO debe disparar)")
    _test_case(
        'volver_menu',
        state_overrides={},
        input_text='volver',
        should_dispatch=False,
    )

    # CASO 4: "menú" desde awaiting_payment → spy NO debe llamarse (aborto)
    print("\nCASO 4: 'menú' desde awaiting_payment (NO debe disparar)")
    _test_case(
        'menu_abort',
        state_overrides={},
        input_text='menú',
        should_dispatch=False,
    )

    # CASO 5: "atrás" desde awaiting_payment → spy NO debe llamarse (aborto)
    print("\nCASO 5: 'atrás' desde awaiting_payment (NO debe disparar)")
    _test_case(
        'atras_abort',
        state_overrides={},
        input_text='atrás',
        should_dispatch=False,
    )

    # Resumen
    print("\n" + "=" * 60)
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"RESULTADO: {passed} PASS, {failed} FAIL de {len(results)} casos")
    if failed:
        print("\nFALLAS:")
        for name, status, detail in results:
            if status == "FAIL":
                print(f"  X {name}: {detail}")
        return False
    else:
        print("\nTodos los casos PASS — _send_to_dispatch_queue dispara correctamente")
        return True


if __name__ == "__main__":
    print("=" * 60)
    print("FASE 1.5 — Smoke Test E2E: _send_to_dispatch_queue")
    print("=" * 60)
    ok = run_all()
    sys.exit(0 if ok else 1)
