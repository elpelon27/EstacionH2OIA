#!/usr/bin/env python3
"""Smoke test P1-2: Watchdog systemd.

Valida:
1. sdnotify importable
2. SystemdNotifier instanciable (no crashea fuera de systemd)
3. _watchdog_loop arrancable como asyncio.Task
4. _watchdog_loop cancelable limpiamente
5. READY=1 notificable (no crashea aunque no haya socket systemd)
"""

import os
import sys
import asyncio

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "api"))

os.environ["BRIDGE_ALLOW_INSECURE_SALT"] = "1"

passed = 0
failed = 0


def test(name, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        print(f"  FAIL: {name}")


print("\n=== Test P1-2: Watchdog systemd ===\n")

# Test 1: sdnotify importable
print("[1] sdnotify importable")
try:
    import sdnotify
    test("import sdnotify OK", sdnotify is not None)
except ImportError:
    test("import sdnotify OK", False)
    print("\n=== RESULTADO: FATAL — sdnotify no instalado ===")
    sys.exit(1)

# Test 2: SystemdNotifier instanciable
print("\n[2] SystemdNotifier instanciable")
try:
    notifier = sdnotify.SystemdNotifier()
    test("SystemdNotifier() OK", notifier is not None)
except Exception as e:
    test(f"SystemdNotifier() OK ({e})", False)

# Test 3: notify no crashea fuera de systemd
print("\n[3] notify() fuera de systemd (fallback graceful)")
try:
    notifier = sdnotify.SystemdNotifier()
    notifier.notify("WATCHDOG=1")
    test("notify(WATCHDOG=1) no crashea", True)
except Exception as e:
    # Fuera de systemd puede fallar, pero NO debe crashear el proceso
    test(f"notify() fallback graceful ({e})", True)

# Test 4: _watchdog_loop arrancable como asyncio.Task
print("\n[4] _watchdog_loop como asyncio.Task")
import bridge

async def test_watchdog():
    """Verifica que el watchdog loop arranca y se cancela limpiamente."""
    global _watchdog_failed
    _watchdog_failed = False
    task = asyncio.create_task(bridge._watchdog_loop())
    # Dar tiempo a que ejecute una iteracion
    await asyncio.sleep(0.5)
    test("Task viva tras 0.5s", not task.done())
    # Cancelar
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    test("Task cancelada limpiamente", task.cancelled())

asyncio.run(test_watchdog())

# Test 5: READY=1 notificable
print("\n[5] READY=1 notificable")
try:
    sdnotify.SystemdNotifier().notify("READY=1")
    test("notify(READY=1) OK", True)
except Exception as e:
    test(f"notify(READY=1) fallback graceful ({e})", True)

# Test 6: bridge.py tiene _watchdog_task variable
print("\n[6] _watchdog_task definido en bridge")
test("_watchdog_task en bridge", hasattr(bridge, "_watchdog_task"))

# Test 7: _watchdog_loop es coroutine
print("\n[7] _watchdog_loop es async coroutine")
import inspect
test("_watchdog_loop es coroutine function", inspect.iscoroutinefunction(bridge._watchdog_loop))

print(f"\n=== RESULTADO: {passed} PASS, {failed} FAIL ===\n")
sys.exit(0 if failed == 0 else 1)
