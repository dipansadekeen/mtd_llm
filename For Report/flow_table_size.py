#!/usr/bin/env python3
import time, csv, requests
from datetime import datetime

ONOS = "http://127.0.0.1:8181/onos/v1"
AUTH = ("onos", "rocks")

OUT = "onos_flow_overhead.csv"
INTERVAL = 1
DURATION = 300

def get_flow_count():
    r = requests.get(f"{ONOS}/flows", auth=AUTH, timeout=5)
    r.raise_for_status()
    return len(r.json().get("flows", []))

def get_device_flow_counts():
    r = requests.get(f"{ONOS}/flows", auth=AUTH, timeout=5)
    r.raise_for_status()

    counts = {}
    for flow in r.json().get("flows", []):
        dev = flow.get("deviceId", "unknown")
        counts[dev] = counts.get(dev, 0) + 1

    return counts

start = time.time()

with open(OUT, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["timestamp", "elapsed_sec", "total_flows", "device_id", "device_flow_count"])

    while time.time() - start <= DURATION:
        now = datetime.now().isoformat(timespec="seconds")
        elapsed = round(time.time() - start, 2)

        device_counts = get_device_flow_counts()
        total_flows = sum(device_counts.values())

        for dev, count in device_counts.items():
            writer.writerow([now, elapsed, total_flows, dev, count])

        print(f"[{elapsed}s] total_flows={total_flows}")

        time.sleep(INTERVAL)

print(f"Saved -> {OUT}")