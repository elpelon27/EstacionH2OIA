#!/usr/bin/env python3
"""Verificador de embeddings de OpenNotebook (Estación H2O).

Detecta en silencio lo que antes fallaba en silencio:
  - fuentes sin ningún embedding en source_embedding
  - comandos embed_source fallidos recientes
  - estado del modelo de embedding por defecto

Uso:
  python opennotebook_verify_embeddings.py            # solo verificar
  python opennotebook_verify_embeddings.py --fix      # re-embbeber pendientes
                                                       # (ventana de 4, con reintentos)

Sale con código 1 si hay pendientes (útil para cron/monitor).
"""
import argparse
import base64
import json
import sys
import time
import urllib.request

SURREAL = "http://127.0.0.1:8002/sql"
API = "http://127.0.0.1:5055/api"
MAX_INFLIGHT = 4
POLL_SECS = 10
PER_JOB_TIMEOUT = 1800


def surreal(sql: str):
    req = urllib.request.Request(
        SURREAL,
        data=sql.encode(),
        headers={
            "Accept": "application/json",
            "Surreal-NS": "open_notebook",
            "Surreal-DB": "open_notebook",
            "Authorization": "Basic " + base64.b64encode(b"root:root").decode(),
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def api_post(path: str, payload: dict):
    req = urllib.request.Request(
        API + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def stats():
    total = len(surreal("SELECT VALUE id FROM source;")[0]["result"])
    embedded = set(
        surreal(
            "RETURN array::distinct((SELECT VALUE source FROM source_embedding WHERE source != NONE));"
        )[0]["result"]
    )
    failed = surreal(
        'SELECT args FROM command WHERE name = "embed_source" AND status = "failed";'
    )[0]["result"]
    default = surreal("SELECT default_embedding_model FROM open_notebook:default_models;")[0][
        "result"
    ]
    return total, embedded, failed, default[0].get("default_embedding_model")


def pending_sources():
    titles = {r["id"]: r["title"] for r in surreal("SELECT id, title FROM source;")[0]["result"]}
    inflight = {
        r["args"]["source_id"]
        for r in surreal(
            'SELECT args FROM command WHERE name = "embed_source" AND status IN ["pending", "running"];'
        )[0]["result"]
    }
    _, embedded, _, _ = stats()
    return [i for i in titles if i not in embedded and i not in inflight]


def fix(pending):
    print(f"Re-embeddiendo {len(pending)} fuentes (ventana de {MAX_INFLIGHT})...")
    queue = list(pending)
    inflight, done, failed = {}, 0, []
    while queue or inflight:
        while queue and len(inflight) < MAX_INFLIGHT:
            sid = queue.pop(0)
            try:
                resp = api_post(
                    "/embed", {"item_id": sid, "item_type": "source", "async_processing": True}
                )
                inflight[resp["command_id"]] = (sid, time.time())
            except Exception as e:
                print(f"  ERROR submit {sid}: {e}")
                failed.append(sid)
        time.sleep(POLL_SECS)
        if not inflight:
            continue
        ids = ", ".join(f"`{c}`" for c in inflight)
        rows = surreal(f"SELECT id, status FROM command WHERE id IN [{ids}];")[0]["result"]
        by_id = {r["id"]: r for r in rows}
        for cid, (sid, t0) in list(inflight.items()):
            st = by_id.get(cid, {}).get("status")
            if st == "completed":
                done += 1
                print(f"  ok {sid}")
                del inflight[cid]
            elif st == "failed" or time.time() - t0 > PER_JOB_TIMEOUT:
                failed.append(sid)
                del inflight[cid]
    # reintento serial
    for sid in failed:
        try:
            resp = api_post(
                "/embed", {"item_id": sid, "item_type": "source", "async_processing": True}
            )
            t0 = time.time()
            st = None
            while time.time() - t0 < PER_JOB_TIMEOUT:
                time.sleep(POLL_SECS)
                st = surreal(f"SELECT status FROM {resp['command_id']};")[0]["result"][0]["status"]
                if st in ("completed", "failed"):
                    break
            if st == "completed":
                done += 1
                failed.remove(sid)
                print(f"  ok (reintento) {sid}")
        except Exception as e:
            print(f"  error reintento {sid}: {e}")
    return done, failed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true", help="re-embeddir fuentes pendientes")
    args = ap.parse_args()

    total, embedded, failed_cmds, default_emb = stats()
    pending = [i for i in surreal("SELECT VALUE id FROM source;")[0]["result"] if i not in embedded]
    print(f"Fuentes totales:          {total}")
    print(f"Fuentes con embedding:    {len(embedded)}")
    print(f"Fuentes SIN embedding:    {len(pending)}")
    print(f"Comandos embed_source fallidos (histórico): {len(failed_cmds)}")
    print(f"Modelo de embedding por defecto: {default_emb or 'NO CONFIGURADO'}")

    if args.fix and pending:
        done, still = fix(pending)
        print(f"Re-parados: {done}; sin resolver: {len(still)}")
        _, embedded2, _, _ = stats()
        pending = [i for i in surreal("SELECT VALUE id FROM source;")[0]["result"] if i not in embedded2]

    if pending or not default_emb:
        print("ESTADO: ALERTA — hay fuentes sin embedding o falta modelo por defecto")
        sys.exit(1)
    print("ESTADO: OK")


if __name__ == "__main__":
    main()
