#!/usr/bin/env python3
"""Driver Tarea A: reprocesa PDFs fallidos en lotes de 5 con ingest_pdf.py --once."""

import json
import shutil
import subprocess
from pathlib import Path

BIB = Path("/mnt/ssd_trabajo/biblioteca/pdfs")
FAILED, INBOX = BIB / "failed", BIB / "inbox"
REPO = Path("/mnt/ssd_trabajo/hermes-agent")
PY = str(REPO / "venv/bin/python")
SCRIPT = str(REPO / "scripts/ingest_pdf.py")
STATE = REPO / "tarea_a_state.json"

integrity = json.loads((REPO / "tarea_a_integrity.json").read_text())
queue = [FAILED / n for n in integrity["ok"]]
state = {"done": [], "errors": [], "remaining": len(queue)}
STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1))
print(f"Cola: {len(queue)} PDFs", flush=True)


def run_pass(model=None):
    cmd = [PY, SCRIPT, "--once"] + (["--model", model] if model else [])
    r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=14400)
    try:
        results = json.loads(r.stdout)
    except Exception:
        results = [{"status": "error", "error": "no-parse", "stderr": r.stderr[-2000:]}]
    return results


while queue:
    batch, queue = queue[:5], queue[5:]
    for p in batch:
        target = INBOX / p.name
        if target.exists():
            target = INBOX / f"{p.stem}_r{p.suffix}"
        shutil.move(str(p), str(target))
    print(f"\n=== LOTE: {[p.name for p in batch]}", flush=True)
    results = run_pass()
    for res in results:
        name = Path(res.get("file", "?")).name
        if res.get("status") == "ok":
            state["done"].append(name)
            print(f"OK {name}", flush=True)
        else:
            state["errors"].append(
                {"file": name, "error": str(res.get("error"))[:300], "model": "qwen2.5:3b"}
            )
            print(f"ERR {name}: {str(res.get('error'))[:150]}", flush=True)
    state["remaining"] = len(queue)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1))

# Reintento con qwen2.5:7b para los que fallaron por timeout
retry = []
for e in list(state["errors"]):
    src = FAILED / e["file"]
    if "timed out" in e["error"] or "11434" in e["error"]:
        if src.exists():
            retry.append(src)
print(f"\n=== REINTENTO qwen2.5:7b: {len(retry)} PDFs", flush=True)
for p in retry:
    shutil.move(str(p), INBOX / p.name)
    results = run_pass(model="qwen2.5:7b")
    for res in results:
        name = Path(res.get("file", "?")).name
        if res.get("status") == "ok":
            state["done"].append(name)
            state["errors"] = [e for e in state["errors"] if e["file"] != name]
            print(f"OK-7b {name}", flush=True)
        else:
            state["errors"] = [e for e in state["errors"] if e["file"] != name] + [
                {"file": name, "error": str(res.get("error"))[:300], "model": "qwen2.5:7b"}
            ]
            print(f"ERR-7b {name}: {str(res.get('error'))[:150]}", flush=True)
    state["remaining"] = 0
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1))

print("\n=== FIN driver", flush=True)
print(
    json.dumps(
        {"procesados_ok": len(state["done"]), "errores": state["errors"]},
        ensure_ascii=False,
        indent=1,
    ),
    flush=True,
)
test hook post-commit 1788471332
