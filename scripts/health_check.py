#!/usr/bin/env python3
"""
Health check script for watchdog.
Returns 0 if all critical systems are healthy, non-zero otherwise.
Used by watchdog via test-binary directive.
"""
import os
import socket
import subprocess
import sys


def check_service_active(name: str) -> bool:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "--quiet", name],
            capture_output=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False

def check_port_listening(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except Exception:
        return False

def check_disk_space(path: str, min_percent: float = 5.0) -> bool:
    try:
        stat = os.statvfs(path)
        free_percent = (stat.f_bavail * stat.f_frsize) / (stat.f_blocks * stat.f_frsize) * 100
        return free_percent >= min_percent
    except Exception:
        return False

def check_sqlite_accessible(path: str) -> bool:
    try:
        import sqlite3
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=3)
        conn.execute("SELECT 1").fetchone()
        conn.close()
        return True
    except Exception:
        return False

def main():
    checks = []

    # 1. Servicios críticos
    critical_services = [
        "valentina-bridge",
        "dispatcher-bot",
        "telegram-bot",
        "cloudflared",
    ]

    for svc in critical_services:
        ok = check_service_active(svc)
        checks.append((f"service:{svc}", ok))
        if not ok:
            print(f"FAIL: service {svc} not active", file=sys.stderr)

    # 2. Puertos críticos
    critical_ports = [
        (8000, "valentina-bridge HTTP"),
    ]

    for port, desc in critical_ports:
        ok = check_port_listening(port)
        checks.append((f"port:{port}", ok))
        if not ok:
            print(f"FAIL: port {port} ({desc}) not listening", file=sys.stderr)

    # 3. Espacio en disco
    ok = check_disk_space("/mnt/ssd_trabajo", min_percent=5.0)
    checks.append(("disk:/mnt/ssd_trabajo", ok))
    if not ok:
        print("FAIL: disk space < 5%", file=sys.stderr)

    ok = check_disk_space("/", min_percent=5.0)
    checks.append(("disk:/", ok))
    if not ok:
        print("FAIL: root disk space < 5%", file=sys.stderr)

    # 4. SQLite accesible
    ok = check_sqlite_accessible("/mnt/ssd_trabajo/hermes-agent/data/conversations.db")
    checks.append(("sqlite:conversations.db", ok))
    if not ok:
        print("FAIL: conversations.db not accessible", file=sys.stderr)

    ok = check_sqlite_accessible("/mnt/ssd_trabajo/hermes-agent/data/dispatch.db")
    checks.append(("sqlite:dispatch.db", ok))
    if not ok:
        print("FAIL: dispatch.db not accessible", file=sys.stderr)

    # Resumen
    failed = [name for name, ok in checks if not ok]
    passed = [name for name, ok in checks if ok]

    print(f"Health check: {len(passed)}/{len(checks)} passed")
    if failed:
        print(f"FAILED: {', '.join(failed)}", file=sys.stderr)
        return 1

    print("All checks passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
