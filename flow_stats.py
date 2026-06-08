import requests
import csv
import time
from datetime import datetime
from collections import deque

ONOS_IP = "127.0.0.1"
ONOS_PORT = "8181"
USERNAME = "onos"
PASSWORD = "rocks"
INTERVAL = 5

RAW_FLOW_CSV = "onos_flow_raw_last5min_v3.csv"
HOST_SUMMARY_CSV = "onos_host_summary_snapshot_v3.csv"

RAW_WINDOW_SEC = 300
SHORT_LIVED_THRESHOLD_SEC = 10

raw_flow_records = deque()


def onos_get(endpoint):
    url = f"http://{ONOS_IP}:{ONOS_PORT}{endpoint}"
    r = requests.get(url, auth=(USERNAME, PASSWORD), timeout=10)
    r.raise_for_status()
    return r.json()


def get_criterion(selector, field):
    for c in selector.get("criteria", []):
        if c.get("type") == field:
            return c
    return {}


def get_output_port(treatment):
    for instr in treatment.get("instructions", []):
        if instr.get("type") == "OUTPUT":
            return instr.get("port")
    return None


def is_added_non_core_flow(flow):
    if flow.get("state") != "ADDED":
        return False

    app_id = str(flow.get("appId", ""))

    core_apps = [
        "org.onosproject.core",
        "org.onosproject.openflow",
        "org.onosproject.hostprovider",
        "org.onosproject.lldpprovider",
        "org.onosproject.proxyarp",
    ]

    return not any(app_id.startswith(core) for core in core_apps)


def prune_old_records(now):
    while raw_flow_records and now - raw_flow_records[0]["seen_epoch"] > RAW_WINDOW_SEC:
        raw_flow_records.popleft()


def write_raw_flow_csv():
    header = [
        "timestamp",
        "seen_epoch",
        "deviceId",
        "flowId",
        "state",
        "appId",
        "priority",
        "eth_src",
        "eth_dst",
        "ipv4_src",
        "ipv4_dst",
        "ip_proto",
        "tcp_src",
        "tcp_dst",
        "udp_src",
        "udp_dst",
        "dst_port",
        "in_port",
        "out_port",
        "packets",
        "bytes",
        "flow_lifetime_sec",
    ]

    with open(RAW_FLOW_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        writer.writerows(raw_flow_records)


def write_host_summary_csv(timestamp):
    dst_summary = {}

    for r in raw_flow_records:
        # dst = r["ipv4_dst"]
        dst = r["ipv4_dst"] or r["eth_dst"]

        if not dst:
            continue

        dst_summary.setdefault(dst, {
            "flow_ids": set(),
            "sender_ips": set(),
            "sender_macs": set(),
            "short_lived_flow_ids": set(),
            "long_lived_flow_ids": set(),
            "lifetimes": [],
            "total_packets": 0,
            "total_bytes": 0,
            "first_seen_epoch": r["seen_epoch"],
            "last_seen_epoch": r["seen_epoch"],
        })

        s = dst_summary[dst]

        s["flow_ids"].add(r["flowId"])

        if r["ipv4_src"]:
            s["sender_ips"].add(r["ipv4_src"])

        if r["eth_src"]:
            s["sender_macs"].add(r["eth_src"])

        s["lifetimes"].append(r["flow_lifetime_sec"])
        s["total_packets"] += r["packets"]
        s["total_bytes"] += r["bytes"]

        s["first_seen_epoch"] = min(s["first_seen_epoch"], r["seen_epoch"])
        s["last_seen_epoch"] = max(s["last_seen_epoch"], r["seen_epoch"])

        if r["flow_lifetime_sec"] <= SHORT_LIVED_THRESHOLD_SEC:
            s["short_lived_flow_ids"].add(r["flowId"])
        else:
            s["long_lived_flow_ids"].add(r["flowId"])

    rows = []

    for dst, s in dst_summary.items():
        lifetimes = s["lifetimes"]

        rows.append({
            "timestamp": timestamp,
            "dst_host": dst,

            "window_sec": RAW_WINDOW_SEC,
            "first_seen_time": datetime.fromtimestamp(s["first_seen_epoch"]).strftime("%Y-%m-%d %H:%M:%S"),
            "last_seen_time": datetime.fromtimestamp(s["last_seen_epoch"]).strftime("%Y-%m-%d %H:%M:%S"),

            "unique_flow_count_towards_host": len(s["flow_ids"]),
            "short_lived_flow_count_towards_host": len(s["short_lived_flow_ids"]),
            "long_lived_flow_count_towards_host": len(s["long_lived_flow_ids"]),

            "avg_flow_lifetime_towards_host": round(sum(lifetimes) / len(lifetimes), 2) if lifetimes else 0,
            "min_flow_lifetime_towards_host": min(lifetimes) if lifetimes else 0,
            "max_flow_lifetime_towards_host": max(lifetimes) if lifetimes else 0,

            "unique_sender_ip_count": len(s["sender_ips"]),
            "sender_ips": ",".join(sorted(s["sender_ips"])),

            "unique_sender_mac_count": len(s["sender_macs"]),
            "sender_macs": ",".join(sorted(s["sender_macs"])),

            "total_packets_towards_host": s["total_packets"],
            "total_bytes_towards_host": s["total_bytes"],
        })

    header = [
        "timestamp",
        "dst_host",
        "window_sec",
        "first_seen_time",
        "last_seen_time",
        "unique_flow_count_towards_host",
        "short_lived_flow_count_towards_host",
        "long_lived_flow_count_towards_host",
        "avg_flow_lifetime_towards_host",
        "min_flow_lifetime_towards_host",
        "max_flow_lifetime_towards_host",
        "unique_sender_ip_count",
        "sender_ips",
        "unique_sender_mac_count",
        "sender_macs",
        "total_packets_towards_host",
        "total_bytes_towards_host",
    ]

    with open(HOST_SUMMARY_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def collect_once():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    now = time.time()

    flows = onos_get("/onos/v1/flows").get("flows", [])

    for flow in flows:
        if not is_added_non_core_flow(flow):
            continue

        selector = flow.get("selector", {})
        treatment = flow.get("treatment", {})

        eth_src = get_criterion(selector, "ETH_SRC").get("mac")
        eth_dst = get_criterion(selector, "ETH_DST").get("mac")
        ipv4_src = get_criterion(selector, "IPV4_SRC").get("ip")
        ipv4_dst = get_criterion(selector, "IPV4_DST").get("ip")

        ip_proto = get_criterion(selector, "IP_PROTO").get("protocol")

        tcp_src = get_criterion(selector, "TCP_SRC").get("tcpPort")
        tcp_dst = get_criterion(selector, "TCP_DST").get("tcpPort")
        udp_src = get_criterion(selector, "UDP_SRC").get("udpPort")
        udp_dst = get_criterion(selector, "UDP_DST").get("udpPort")

        dst_port = tcp_dst if tcp_dst is not None else udp_dst

        raw_flow_records.append({
            "timestamp": timestamp,
            "seen_epoch": now,
            "deviceId": flow.get("deviceId"),
            "flowId": flow.get("id"),
            "state": flow.get("state"),
            "appId": flow.get("appId"),
            "priority": flow.get("priority"),
            "eth_src": eth_src,
            "eth_dst": eth_dst,
            "ipv4_src": ipv4_src,
            "ipv4_dst": ipv4_dst,
            "ip_proto": ip_proto,
            "tcp_src": tcp_src,
            "tcp_dst": tcp_dst,
            "udp_src": udp_src,
            "udp_dst": udp_dst,
            "dst_port": dst_port,
            "in_port": get_criterion(selector, "IN_PORT").get("port"),
            "out_port": get_output_port(treatment),
            "packets": int(flow.get("packets", 0)),
            "bytes": int(flow.get("bytes", 0)),
            "flow_lifetime_sec": float(flow.get("life", 0)),
        })

    prune_old_records(now)
    write_raw_flow_csv()
    write_host_summary_csv(timestamp)

    print(f"Updated raw 5-min records: {len(raw_flow_records)}")


if __name__ == "__main__":
    while True:
        try:
            collect_once()
        except Exception as e:
            print("Error:", e)

        time.sleep(INTERVAL)