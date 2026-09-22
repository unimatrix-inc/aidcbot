#!/usr/bin/env python3
"""Read-only Linux GPU telemetry agent for OpenNEXT capacity listings."""

import argparse
import csv
import json
import os
import random
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MIB = 1024 * 1024
GPU_QUERY = "index,uuid,name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw"


def number(value):
    value = str(value).strip()
    if not value or value.lower() in {"n/a", "[not supported]"}:
        return None
    try:
        result = float(value)
        return result if result == result and abs(result) != float("inf") else None
    except ValueError:
        return None


def cpu_times(path="/proc/stat"):
    fields = Path(path).read_text().splitlines()[0].split()
    if fields[0] != "cpu":
        raise ValueError("/proc/stat has no aggregate CPU row")
    values = [int(value) for value in fields[1:]]
    return sum(values), values[3] + (values[4] if len(values) > 4 else 0)


def cpu_percent(previous, current):
    total = current[0] - previous[0]
    idle = current[1] - previous[1]
    return round(max(0, min(100, 100 * (total - idle) / total)), 2) if total > 0 else None


def memory_stats(path="/proc/meminfo"):
    values = {}
    for line in Path(path).read_text().splitlines():
        key, _, raw = line.partition(":")
        if raw:
            values[key] = int(raw.strip().split()[0]) * 1024
    total = values["MemTotal"]
    available = values.get("MemAvailable", values.get("MemFree", 0))
    used = max(0, total - available)
    return {"totalBytes": total, "usedBytes": used, "utilizationPercent": round(100 * used / total, 2) if total else None}


def disk_stats(path="/"):
    usage = shutil.disk_usage(path)
    return {"mount": path, "totalBytes": usage.total, "usedBytes": usage.used,
            "utilizationPercent": round(100 * usage.used / usage.total, 2) if usage.total else None}


def gpu_stats():
    try:
        result = subprocess.run(["nvidia-smi", f"--query-gpu={GPU_QUERY}", "--format=csv,noheader,nounits"],
                                check=True, capture_output=True, text=True, timeout=8)
    except (FileNotFoundError, subprocess.SubprocessError):
        return []
    gpus = []
    for row in csv.reader(result.stdout.splitlines()):
        if len(row) != 8:
            continue
        index, uuid, name, utilization, used_mib, total_mib, temperature, power = [item.strip() for item in row]
        if not index.isdigit() or not uuid or not name:
            continue
        used, total = number(used_mib), number(total_mib)
        gpus.append({"index": int(index), "uuid": uuid, "name": name,
                     "utilizationPercent": number(utilization),
                     "memoryUsedBytes": int(used * MIB) if used is not None else None,
                     "memoryTotalBytes": int(total * MIB) if total is not None else None,
                     "temperatureC": number(temperature), "powerW": number(power)})
    return gpus


def collect(previous_cpu):
    current_cpu = cpu_times()
    try:
        load = list(os.getloadavg())
    except OSError:
        load = None
    return current_cpu, {"sampledAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                         "cpu": {"utilizationPercent": cpu_percent(previous_cpu, current_cpu), "loadAverage": load},
                         "memory": memory_stats(), "disk": disk_stats(), "gpus": gpu_stats()}


def send(api_url, capacity_id, token, payload, timeout=10):
    endpoint = f"{api_url.rstrip('/')}/api/v1/terminal/capacities/{capacity_id}/metrics"
    request = Request(endpoint, data=json.dumps(payload, separators=(",", ":")).encode(), method="POST",
                      headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return response.status


def main(argv=None):
    parser = argparse.ArgumentParser(description="OpenNEXT read-only GPU telemetry agent")
    parser.add_argument("--api-url", default=os.getenv("OPENNEXT_API_URL", "https://open-next.ai"))
    parser.add_argument("--capacity-id", default=os.getenv("OPENNEXT_CAPACITY_ID"))
    parser.add_argument("--token-file", default=os.getenv("OPENNEXT_TOKEN_FILE", "/etc/aidcbot/token"))
    parser.add_argument("--interval", type=int, default=int(os.getenv("OPENNEXT_INTERVAL_SECONDS", "30")))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    if not args.api_url.startswith("https://") or not args.capacity_id or not 10 <= args.interval <= 3600:
        parser.error("HTTPS API URL, capacity ID, and interval of 10–3600 seconds are required")
    token = Path(args.token_file).read_text().strip()
    if len(token) < 32:
        parser.error("token file is missing a valid capacity token")
    previous = cpu_times()
    failures = 0
    while True:
        time.sleep(args.interval if failures == 0 else min(300, args.interval * 2 ** min(failures, 4)) + random.uniform(0, 3))
        current, payload = collect(previous)
        previous = current
        try:
            send(args.api_url, args.capacity_id, token, payload)
            failures = 0
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            failures += 1
            print(f"telemetry delivery failed ({type(error).__name__}); retrying", file=sys.stderr, flush=True)
        if args.once:
            return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
