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

OUTPUT_CSV = "onos_security_snapshot.csv"

SHORT_LIVED_THRESHOLD_SEC = 10
HISTORY_LIMIT = 10

connection_first_seen = {}
flow_history = {}
mac_history = {}


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


def format_time(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def log_security_snapshot(timestamp):
    flows = onos_get("/onos/v1/flows").get("flows", [])

    rows = []
    src_stats = {}
    dst_stats = {}

    now = time.time()

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

        in_port = get_criterion(selector, "IN_PORT").get("port")
        out_port = get_output_port(treatment)

        device_id = flow.get("deviceId")
        flow_id = flow.get("id")
        app_id = flow.get("appId")

        packets = int(flow.get("packets", 0))
        bytes_ = int(flow.get("bytes", 0))
        flow_lifetime_sec = float(flow.get("life", 0))

        dst_port = tcp_dst if tcp_dst is not None else udp_dst

        conn_key = f"{eth_src}|{eth_dst}|{ipv4_src}|{ipv4_dst}|{dst_port}|{device_id}|{flow_id}"

        if conn_key not in connection_first_seen:
            connection_first_seen[conn_key] = now

        observed_active_age_sec = round(now - connection_first_seen[conn_key], 2)

        flow_history.setdefault(conn_key, deque(maxlen=HISTORY_LIMIT))
        flow_history[conn_key].append({
            "time": now,
            "packets": packets,
            "bytes": bytes_,
            "life": flow_lifetime_sec,
            "state": flow.get("state"),
        })

        if eth_src:
            mac_history.setdefault(eth_src, deque(maxlen=HISTORY_LIMIT))
            mac_history[eth_src].append({
                "time": now,
                "ipv4_src": ipv4_src,
                "ipv4_dst": ipv4_dst,
                "dst_port": dst_port,
                "life": flow_lifetime_sec,
            })

        flow_hist = flow_history[conn_key]
        mac_hist = mac_history.get(eth_src, [])

        flow_seen_last10 = len(flow_hist)
        flow_packet_change_last10 = flow_hist[-1]["packets"] - flow_hist[0]["packets"] if len(flow_hist) > 1 else 0
        flow_byte_change_last10 = flow_hist[-1]["bytes"] - flow_hist[0]["bytes"] if len(flow_hist) > 1 else 0

        src_mac_first_seen_time = format_time(mac_hist[0]["time"]) if mac_hist else None
        src_mac_last_seen_time = format_time(mac_hist[-1]["time"]) if mac_hist else None
        src_mac_observed_age_sec = round(mac_hist[-1]["time"] - mac_hist[0]["time"], 2) if len(mac_hist) > 1 else 0

        mac_ips_last10 = set()
        mac_dst_ips_last10 = set()
        mac_dst_ports_last10 = set()
        mac_short_lived_count_last10 = 0

        for item in mac_hist:
            if item["ipv4_src"]:
                mac_ips_last10.add(item["ipv4_src"])
            if item["ipv4_dst"]:
                mac_dst_ips_last10.add(item["ipv4_dst"])
            if item["dst_port"]:
                mac_dst_ports_last10.add(item["dst_port"])
            if item["life"] <= SHORT_LIVED_THRESHOLD_SEC:
                mac_short_lived_count_last10 += 1

        if ipv4_src:
            src_stats.setdefault(ipv4_src, {
                "dst_ips": set(),
                "dst_ports": set(),
                "flow_count": 0,
                "short_lived_count": 0,
            })

            if ipv4_dst:
                src_stats[ipv4_src]["dst_ips"].add(ipv4_dst)

            if dst_port:
                src_stats[ipv4_src]["dst_ports"].add(dst_port)

            src_stats[ipv4_src]["flow_count"] += 1

            if flow_lifetime_sec <= SHORT_LIVED_THRESHOLD_SEC:
                src_stats[ipv4_src]["short_lived_count"] += 1

        if ipv4_dst:
            dst_stats.setdefault(ipv4_dst, {
                "src_ips": set(),
                "flow_count": 0,
                "total_packets": 0,
                "total_bytes": 0,
            })

            if ipv4_src:
                dst_stats[ipv4_dst]["src_ips"].add(ipv4_src)

            dst_stats[ipv4_dst]["flow_count"] += 1
            dst_stats[ipv4_dst]["total_packets"] += packets
            dst_stats[ipv4_dst]["total_bytes"] += bytes_

        rows.append({
            "timestamp": timestamp,
            "deviceId": device_id,
            "flowId": flow_id,
            "state": flow.get("state"),
            "appId": app_id,
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
            "in_port": in_port,
            "out_port": out_port,

            "packets": packets,
            "bytes": bytes_,
            "flow_lifetime_sec": flow_lifetime_sec,
            "observed_active_age_sec": observed_active_age_sec,

            "flow_seen_last10": flow_seen_last10,
            "flow_packet_change_last10": flow_packet_change_last10,
            "flow_byte_change_last10": flow_byte_change_last10,

            "src_mac_first_seen_time": src_mac_first_seen_time,
            "src_mac_last_seen_time": src_mac_last_seen_time,
            "src_mac_observed_age_sec": src_mac_observed_age_sec,
            "src_mac_ip_count_last10": len(mac_ips_last10),
            "src_mac_ips_last10": ",".join(sorted(mac_ips_last10)),
            "src_mac_unique_dst_ip_count_last10": len(mac_dst_ips_last10),
            "src_mac_unique_dst_port_count_last10": len(mac_dst_ports_last10),
            "src_mac_short_lived_count_last10": mac_short_lived_count_last10,
        })

    final_rows = []

    for row in rows:
        src = row["ipv4_src"]
        dst = row["ipv4_dst"]

        if src in src_stats:
            row["unique_dst_ip_count_by_src"] = len(src_stats[src]["dst_ips"])
            row["unique_dst_port_count_by_src"] = len(src_stats[src]["dst_ports"])
            row["flow_count_by_src"] = src_stats[src]["flow_count"]
            row["short_lived_flow_count_by_src"] = src_stats[src]["short_lived_count"]
        else:
            row["unique_dst_ip_count_by_src"] = 0
            row["unique_dst_port_count_by_src"] = 0
            row["flow_count_by_src"] = 0
            row["short_lived_flow_count_by_src"] = 0

        if dst in dst_stats:
            row["flow_count_by_dst"] = dst_stats[dst]["flow_count"]
            row["unique_src_count_by_dst"] = len(dst_stats[dst]["src_ips"])
            row["total_packets_by_dst"] = dst_stats[dst]["total_packets"]
            row["total_bytes_by_dst"] = dst_stats[dst]["total_bytes"]
        else:
            row["flow_count_by_dst"] = 0
            row["unique_src_count_by_dst"] = 0
            row["total_packets_by_dst"] = 0
            row["total_bytes_by_dst"] = 0

        final_rows.append(row)

    header = [
        "timestamp",
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
        "in_port",
        "out_port",

        "packets",
        "bytes",
        "flow_lifetime_sec",
        "observed_active_age_sec",

        "flow_seen_last10",
        "flow_packet_change_last10",
        "flow_byte_change_last10",

        "src_mac_first_seen_time",
        "src_mac_last_seen_time",
        "src_mac_observed_age_sec",
        "src_mac_ip_count_last10",
        "src_mac_ips_last10",
        "src_mac_unique_dst_ip_count_last10",
        "src_mac_unique_dst_port_count_last10",
        "src_mac_short_lived_count_last10",

        "unique_dst_ip_count_by_src",
        "unique_dst_port_count_by_src",
        "flow_count_by_src",
        "short_lived_flow_count_by_src",

        "flow_count_by_dst",
        "unique_src_count_by_dst",
        "total_packets_by_dst",
        "total_bytes_by_dst",
    ]

    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        writer.writerows(final_rows)

    print(f"Snapshot updated: {len(final_rows)} active non-core flows")


if __name__ == "__main__":
    while True:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            log_security_snapshot(timestamp)
        except Exception as e:
            print("Error:", e)

        time.sleep(INTERVAL)