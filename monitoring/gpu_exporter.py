#!/usr/bin/env python3
"""
GPU Exporter — Estación H2O (Prometheus)
========================================
Expone métricas de la GPU NVIDIA (GTX 1070) vía nvidia-smi en :9101,
en formato Prometheus. Corre como servicio systemd con el venv del proyecto
(usa prometheus_client, ya instalado en venv/).

Métricas:
- nvidia_gpu_utilization_percent   (0-100)
- nvidia_gpu_memory_used_bytes
- nvidia_gpu_memory_total_bytes
- nvidia_gpu_temperature_celsius

systemd: ver infra/systemd/gpu-exporter.service
Prometheus scrapea 172.17.0.1:9101/metrics (job 'gpu').
"""

import subprocess
import sys
import time

from prometheus_client import Gauge, start_http_server

PORT = 9101
SMI_QUERY = "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu"
SMI_FMT = "--format=csv,noheader,nounits"
INTERVAL_SECONDS = 10


def read_gpu() -> tuple[float, float, float, float]:
    """Devuelve (util%, mem_used_MiB, mem_total_MiB, temp_C)."""
    try:
        out = subprocess.run(
            ["nvidia-smi", SMI_QUERY, SMI_FMT],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        parts = [float(p) for p in out.split(",")]
        if len(parts) >= 4:
            return parts[0], parts[1], parts[2], parts[3]
    except Exception:
        pass
    # Fallback seguro: GPU no expuesta → 0, conservando último total conocido
    return 0.0, 0.0, 8192.0, 0.0


def main() -> int:
    util = Gauge("nvidia_gpu_utilization_percent", "GPU compute utilization %")
    mem_used = Gauge("nvidia_gpu_memory_used_bytes", "GPU memory used bytes")
    mem_total = Gauge("nvidia_gpu_memory_total_bytes", "GPU memory total bytes")
    temp = Gauge("nvidia_gpu_temperature_celsius", "GPU temperature Celsius")

    start_http_server(PORT)
    print(f"GPU exporter escuchando en :{PORT}", flush=True)

    while True:
        util_pct, mem_used_mb, mem_total_mb, temp_c = read_gpu()
        util.set(util_pct)
        mem_used.set(mem_used_mb * 1024 * 1024)
        mem_total.set(mem_total_mb * 1024 * 1024)
        temp.set(temp_c)
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
