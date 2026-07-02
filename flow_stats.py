# import requests
# import csv
# import time
# from datetime import datetime
# from collections import deque

# ONOS_IP = "127.0.0.1"
# ONOS_PORT = "8181"
# USERNAME = "onos"
# PASSWORD = "rocks"
# INTERVAL = 5

# RAW_FLOW_CSV = "onos_flow_raw_last5min_v3.csv"
# HOST_SUMMARY_CSV = "onos_host_summary_snapshot_v3.csv"

# RAW_WINDOW_SEC = 300
# SHORT_LIVED_THRESHOLD_SEC = 10

# raw_flow_records = deque()


# def onos_get(endpoint):
#     url = f"http://{ONOS_IP}:{ONOS_PORT}{endpoint}"
#     r = requests.get(url, auth=(USERNAME, PASSWORD), timeout=10)
#     r.raise_for_status()
#     return r.json()


# def get_criterion(selector, field):
#     for c in selector.get("criteria", []):
#         if c.get("type") == field:
#             return c
#     return {}


# def get_output_port(treatment):
#     for instr in treatment.get("instructions", []):
#         if instr.get("type") == "OUTPUT":
#             return instr.get("port")
#     return None


# def is_added_non_core_flow(flow):
#     if flow.get("state") != "ADDED":
#         return False

#     app_id = str(flow.get("appId", ""))

#     core_apps = [
#         "org.onosproject.core",
#         "org.onosproject.openflow",
#         "org.onosproject.hostprovider",
#         "org.onosproject.lldpprovider",
#         "org.onosproject.proxyarp",
#     ]

#     return not any(app_id.startswith(core) for core in core_apps)


# def prune_old_records(now):
#     while raw_flow_records and now - raw_flow_records[0]["seen_epoch"] > RAW_WINDOW_SEC:
#         raw_flow_records.popleft()


# def write_raw_flow_csv():
#     header = [
#         "timestamp",
#         "seen_epoch",
#         "deviceId",
#         "flowId",
#         "state",
#         "appId",
#         "priority",
#         "eth_src",
#         "eth_dst",
#         "ipv4_src",
#         "ipv4_dst",
#         "ip_proto",
#         "tcp_src",
#         "tcp_dst",
#         "udp_src",
#         "udp_dst",
#         "dst_port",
#         "in_port",
#         "out_port",
#         "packets",
#         "bytes",
#         "flow_lifetime_sec",
#     ]

#     with open(RAW_FLOW_CSV, "w", newline="") as f:
#         writer = csv.DictWriter(f, fieldnames=header)
#         writer.writeheader()
#         writer.writerows(raw_flow_records)


# def write_host_summary_csv(timestamp):
#     dst_summary = {}

#     for r in raw_flow_records:
#         # dst = r["ipv4_dst"]
#         dst = r["ipv4_dst"] or r["eth_dst"]

#         if not dst:
#             continue

#         dst_summary.setdefault(dst, {
#             "flow_ids": set(),
#             "sender_ips": set(),
#             "sender_macs": set(),
#             "short_lived_flow_ids": set(),
#             "long_lived_flow_ids": set(),
#             "lifetimes": [],
#             "total_packets": 0,
#             "total_bytes": 0,
#             "first_seen_epoch": r["seen_epoch"],
#             "last_seen_epoch": r["seen_epoch"],
#         })

#         s = dst_summary[dst]

#         s["flow_ids"].add(r["flowId"])

#         if r["ipv4_src"]:
#             s["sender_ips"].add(r["ipv4_src"])

#         if r["eth_src"]:
#             s["sender_macs"].add(r["eth_src"])

#         s["lifetimes"].append(r["flow_lifetime_sec"])
#         s["total_packets"] += r["packets"]
#         s["total_bytes"] += r["bytes"]

#         s["first_seen_epoch"] = min(s["first_seen_epoch"], r["seen_epoch"])
#         s["last_seen_epoch"] = max(s["last_seen_epoch"], r["seen_epoch"])

#         if r["flow_lifetime_sec"] <= SHORT_LIVED_THRESHOLD_SEC:
#             s["short_lived_flow_ids"].add(r["flowId"])
#         else:
#             s["long_lived_flow_ids"].add(r["flowId"])

#     rows = []

#     for dst, s in dst_summary.items():
#         lifetimes = s["lifetimes"]

#         rows.append({
#             "timestamp": timestamp,
#             "dst_host": dst,

#             "window_sec": RAW_WINDOW_SEC,
#             "first_seen_time": datetime.fromtimestamp(s["first_seen_epoch"]).strftime("%Y-%m-%d %H:%M:%S"),
#             "last_seen_time": datetime.fromtimestamp(s["last_seen_epoch"]).strftime("%Y-%m-%d %H:%M:%S"),

#             "unique_flow_count_towards_host": len(s["flow_ids"]),
#             "short_lived_flow_count_towards_host": len(s["short_lived_flow_ids"]),
#             "long_lived_flow_count_towards_host": len(s["long_lived_flow_ids"]),

#             "avg_flow_lifetime_towards_host": round(sum(lifetimes) / len(lifetimes), 2) if lifetimes else 0,
#             "min_flow_lifetime_towards_host": min(lifetimes) if lifetimes else 0,
#             "max_flow_lifetime_towards_host": max(lifetimes) if lifetimes else 0,

#             "unique_sender_ip_count": len(s["sender_ips"]),
#             "sender_ips": ",".join(sorted(s["sender_ips"])),

#             "unique_sender_mac_count": len(s["sender_macs"]),
#             "sender_macs": ",".join(sorted(s["sender_macs"])),

#             "total_packets_towards_host": s["total_packets"],
#             "total_bytes_towards_host": s["total_bytes"],
#         })

#     header = [
#         "timestamp",
#         "dst_host",
#         "window_sec",
#         "first_seen_time",
#         "last_seen_time",
#         "unique_flow_count_towards_host",
#         "short_lived_flow_count_towards_host",
#         "long_lived_flow_count_towards_host",
#         "avg_flow_lifetime_towards_host",
#         "min_flow_lifetime_towards_host",
#         "max_flow_lifetime_towards_host",
#         "unique_sender_ip_count",
#         "sender_ips",
#         "unique_sender_mac_count",
#         "sender_macs",
#         "total_packets_towards_host",
#         "total_bytes_towards_host",
#     ]

#     with open(HOST_SUMMARY_CSV, "w", newline="") as f:
#         writer = csv.DictWriter(f, fieldnames=header)
#         writer.writeheader()
#         writer.writerows(rows)


# def collect_once():
#     timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#     now = time.time()

#     flows = onos_get("/onos/v1/flows").get("flows", [])

#     for flow in flows:
#         if not is_added_non_core_flow(flow):
#             continue

#         selector = flow.get("selector", {})
#         treatment = flow.get("treatment", {})

#         eth_src = get_criterion(selector, "ETH_SRC").get("mac")
#         eth_dst = get_criterion(selector, "ETH_DST").get("mac")
#         ipv4_src = get_criterion(selector, "IPV4_SRC").get("ip")
#         ipv4_dst = get_criterion(selector, "IPV4_DST").get("ip")

#         ip_proto = get_criterion(selector, "IP_PROTO").get("protocol")

#         tcp_src = get_criterion(selector, "TCP_SRC").get("tcpPort")
#         tcp_dst = get_criterion(selector, "TCP_DST").get("tcpPort")
#         udp_src = get_criterion(selector, "UDP_SRC").get("udpPort")
#         udp_dst = get_criterion(selector, "UDP_DST").get("udpPort")

#         dst_port = tcp_dst if tcp_dst is not None else udp_dst

#         raw_flow_records.append({
#             "timestamp": timestamp,
#             "seen_epoch": now,
#             "deviceId": flow.get("deviceId"),
#             "flowId": flow.get("id"),
#             "state": flow.get("state"),
#             "appId": flow.get("appId"),
#             "priority": flow.get("priority"),
#             "eth_src": eth_src,
#             "eth_dst": eth_dst,
#             "ipv4_src": ipv4_src,
#             "ipv4_dst": ipv4_dst,
#             "ip_proto": ip_proto,
#             "tcp_src": tcp_src,
#             "tcp_dst": tcp_dst,
#             "udp_src": udp_src,
#             "udp_dst": udp_dst,
#             "dst_port": dst_port,
#             "in_port": get_criterion(selector, "IN_PORT").get("port"),
#             "out_port": get_output_port(treatment),
#             "packets": int(flow.get("packets", 0)),
#             "bytes": int(flow.get("bytes", 0)),
#             "flow_lifetime_sec": float(flow.get("life", 0)),
#         })

#     prune_old_records(now)
#     write_raw_flow_csv()
#     write_host_summary_csv(timestamp)

#     print(f"Updated raw 5-min records: {len(raw_flow_records)}")


# if __name__ == "__main__":
#     while True:
#         try:
#             collect_once()
#         except Exception as e:
#             print("Error:", e)

#         time.sleep(INTERVAL)



# for routes as well
#!/usr/bin/env python3
import requests
import csv
import time
from datetime import datetime
from collections import deque, defaultdict


# =====================================================
# CONFIG
# =====================================================

ONOS_IP = "127.0.0.1"
ONOS_PORT = "8181"
USERNAME = "onos"
PASSWORD = "rocks"
INTERVAL = 5

HOST_SUMMARY_CSV = "onos_host_summary_snapshot_v3.csv"
ROUTE_OVERLAP_CSV = "onos_active_flow_route_overlap_v3.csv"

RAW_WINDOW_SEC = 300
SHORT_LIVED_THRESHOLD_SEC = 10

# Route-overlap filtering
ONLY_ADDED = True
APP_KEYS = ["fwd"]          # [] disables app filtering
IGNORE_ZERO = False

DEV = {
    f"of:000000000000000{i:x}": f"s{i}"
    for i in range(1, 14)
}

IP2MAC = {
    f"10.0.0.{i}": f"00:00:00:00:00:{i:02x}"
    for i in range(1, 41)
}

MAC2HOST = {
    v.lower(): f"h{i}"
    for i, v in enumerate(IP2MAC.values(), start=1)
}

raw_flow_records = deque()


# =====================================================
# BASIC HELPERS
# =====================================================

def onos_get(endpoint):
    url = f"http://{ONOS_IP}:{ONOS_PORT}/onos/v1{endpoint}"
    r = requests.get(url, auth=(USERNAME, PASSWORD), timeout=10)
    r.raise_for_status()
    return r.json()


def norm_mac(x):
    return str(x).lower().strip() if x else None


def norm_ip(x):
    if not x:
        return None
    return str(x).replace("/32", "").replace("/24", "").strip()


def sw(x):
    return DEV.get(x, x)


def host_name(mac_addr):
    return MAC2HOST.get(norm_mac(mac_addr), norm_mac(mac_addr))


def canon_link_id(a_dev, a_port, b_dev, b_port):
    """
    Same link_id format as link_stats_onos.csv:

        of:0000000000000001:2 -> of:000000000000000c:1
    """
    a = (a_dev, int(a_port))
    b = (b_dev, int(b_port))
    left, right = sorted([a, b])
    return f"{left[0]}:{left[1]} -> {right[0]}:{right[1]}"


def canon_mac_pair(src_mac, dst_mac):
    """
    Canonical MAC pair for scoring.

    h1->h33 and h33->h1 become the same mac_pair.
    """
    if not src_mac or not dst_mac:
        return ""

    a = norm_mac(src_mac)
    b = norm_mac(dst_mac)

    return " <-> ".join(sorted([a, b]))


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


def get_output_ports(flow):
    ports = []

    for instr in flow.get("treatment", {}).get("instructions", []):
        if instr.get("type") == "OUTPUT" and instr.get("port") is not None:
            ports.append(str(instr.get("port")))

    return ports


def flow_fields(flow):
    d = {
        "smac": None,
        "dmac": None,
        "sip": None,
        "dip": None,
    }

    for c in flow.get("selector", {}).get("criteria", []):
        ctype = c.get("type")

        if ctype == "ETH_SRC":
            d["smac"] = norm_mac(c.get("mac"))

        elif ctype == "ETH_DST":
            d["dmac"] = norm_mac(c.get("mac"))

        elif ctype == "IPV4_SRC":
            d["sip"] = norm_ip(c.get("ip"))

        elif ctype == "IPV4_DST":
            d["dip"] = norm_ip(c.get("ip"))

    # Fallback IP -> MAC for Mininet hosts.
    d["smac"] = d["smac"] or IP2MAC.get(d["sip"])
    d["dmac"] = d["dmac"] or IP2MAC.get(d["dip"])

    return d


def is_added_non_core_flow(flow):
    if str(flow.get("state", "")).upper() != "ADDED":
        return False

    app_id = str(flow.get("appId", "")).lower()

    core_apps = [
        "org.onosproject.core",
        "org.onosproject.openflow",
        "org.onosproject.hostprovider",
        "org.onosproject.lldpprovider",
        "org.onosproject.proxyarp",
    ]

    return not any(app_id.startswith(core) for core in core_apps)


def is_route_flow_candidate(flow):
    state = str(flow.get("state", "")).upper()
    appid = str(flow.get("appId", "")).lower()
    pkts = int(flow.get("packets", 0))

    if ONLY_ADDED and state != "ADDED":
        return False

    if APP_KEYS and not any(k in appid for k in APP_KEYS):
        return False

    if IGNORE_ZERO and pkts <= 0:
        return False

    return True


# =====================================================
# FLOW FETCHING
# =====================================================

def get_all_flows():
    """
    Per-device fetch is better for route reconstruction because each flow
    gets a reliable deviceId.
    """
    flows = []

    devices = onos_get("/devices").get("devices", [])

    for d in devices:
        dev = d["id"]

        for f in onos_get(f"/flows/{dev}").get("flows", []):
            f["deviceId"] = f.get("deviceId", dev)
            flows.append(f)

    return flows


# =====================================================
# HOST SUMMARY
# =====================================================

def prune_old_records(now):
    while raw_flow_records and now - raw_flow_records[0]["seen_epoch"] > RAW_WINDOW_SEC:
        raw_flow_records.popleft()


def write_host_summary_csv(timestamp):
    """
    Writes:
        onos_host_summary_snapshot_v3.csv

    This is for IP/host-side scoring.

    Important:
        dst_host prefers eth_dst over ipv4_dst so proactive_new_scoring.py
        can map dst_host using host_from_mac().
    """
    dst_summary = {}

    for r in raw_flow_records:
        # Prefer MAC because your scoring maps dst_host using host_from_mac().
        dst = r["eth_dst"] or r["ipv4_dst"]

        if not dst:
            continue

        if dst not in dst_summary:
            dst_summary[dst] = {
                "flow_ids": set(),
                "sender_ips": set(),
                "sender_macs": set(),

                "flow_lifetimes": {},
                "flow_packets": {},
                "flow_bytes": {},

                "first_seen_epoch": r["seen_epoch"],
                "last_seen_epoch": r["seen_epoch"],
            }

        s = dst_summary[dst]
        fid = str(r["flowId"])

        s["flow_ids"].add(fid)

        if r["ipv4_src"]:
            s["sender_ips"].add(r["ipv4_src"])

        if r["eth_src"]:
            s["sender_macs"].add(r["eth_src"])

        # Latest value per flow ID, avoids repeated cumulative overcounting.
        s["flow_lifetimes"][fid] = float(r["flow_lifetime_sec"])
        s["flow_packets"][fid] = int(r["packets"])
        s["flow_bytes"][fid] = int(r["bytes"])

        s["first_seen_epoch"] = min(s["first_seen_epoch"], r["seen_epoch"])
        s["last_seen_epoch"] = max(s["last_seen_epoch"], r["seen_epoch"])

    rows = []

    for dst, s in dst_summary.items():
        lifetimes = list(s["flow_lifetimes"].values())

        short_lived = [
            fid for fid, life in s["flow_lifetimes"].items()
            if life <= SHORT_LIVED_THRESHOLD_SEC
        ]

        long_lived = [
            fid for fid, life in s["flow_lifetimes"].items()
            if life > SHORT_LIVED_THRESHOLD_SEC
        ]

        rows.append({
            "timestamp": timestamp,
            "dst_host": dst,

            "window_sec": RAW_WINDOW_SEC,
            "first_seen_time": datetime.fromtimestamp(
                s["first_seen_epoch"]
            ).strftime("%Y-%m-%d %H:%M:%S"),
            "last_seen_time": datetime.fromtimestamp(
                s["last_seen_epoch"]
            ).strftime("%Y-%m-%d %H:%M:%S"),

            "unique_flow_count_towards_host": len(s["flow_ids"]),
            "short_lived_flow_count_towards_host": len(short_lived),
            "long_lived_flow_count_towards_host": len(long_lived),

            "avg_flow_lifetime_towards_host": round(
                sum(lifetimes) / len(lifetimes), 2
            ) if lifetimes else 0,
            "min_flow_lifetime_towards_host": min(lifetimes) if lifetimes else 0,
            "max_flow_lifetime_towards_host": max(lifetimes) if lifetimes else 0,

            "unique_sender_ip_count": len(s["sender_ips"]),
            "sender_ips": ",".join(sorted(s["sender_ips"])),

            "unique_sender_mac_count": len(s["sender_macs"]),
            "sender_macs": ",".join(sorted(s["sender_macs"])),

            "total_packets_towards_host": sum(s["flow_packets"].values()),
            "total_bytes_towards_host": sum(s["flow_bytes"].values()),
        })

    rows = sorted(
        rows,
        key=lambda r: (
            r["unique_flow_count_towards_host"],
            r["short_lived_flow_count_towards_host"],
            r["unique_sender_mac_count"],
        ),
        reverse=True,
    )

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

    return len(rows)


# =====================================================
# MAC-PAIR ROUTE OVERLAP
# =====================================================

def build_pair_links():
    """
    Builds directed ONOS adjacency, but stores canonical link_id matching
    link_stats_onos.csv.
    """
    pair_link = {}

    for l in onos_get("/links").get("links", []):
        sd = l["src"]["device"]
        sp = str(l["src"]["port"])
        dd = l["dst"]["device"]
        dp = str(l["dst"]["port"])

        link_id = canon_link_id(sd, sp, dd, dp)

        pair_link[(sd, dd)] = {
            "id": link_id,
            "txt": link_id,
            "src_port": sp,
            "dst_port": dp,
        }

    return pair_link


def write_route_overlap_csv(timestamp, flows):
    """
    Writes:
        onos_active_flow_route_overlap_v3.csv

    One row = one active directed MAC-pair route.

    This is the table your proactive route scoring should use.
    """
    pair_link = build_pair_links()
    active = [f for f in flows if is_route_flow_candidate(f)]

    route_links = defaultdict(set)
    route_ids = defaultdict(set)
    route_bytes = defaultdict(int)
    route_pkts = defaultdict(int)
    link_txt = {}

    # -----------------------------------------------------
    # 1) Reconstruct active route links per directed MAC pair
    # -----------------------------------------------------
    for f in active:
        dev = f.get("deviceId")
        fid = str(f.get("id"))

        ff = flow_fields(f)
        ops = get_output_ports(f)

        src_mac = ff.get("smac")
        dst_mac = ff.get("dmac")

        if not src_mac or not dst_mac:
            continue

        key = (norm_mac(src_mac), norm_mac(dst_mac))

        for (sd, dd), info in pair_link.items():
            if dev != sd:
                continue

            if info["src_port"] not in ops:
                continue

            # Avoid duplicate physical link counting for same MAC pair.
            if info["id"] in route_links[key]:
                continue

            route_links[key].add(info["id"])
            route_ids[key].add(fid)
            route_bytes[key] += int(f.get("bytes", 0))
            route_pkts[key] += int(f.get("packets", 0))
            link_txt[info["id"]] = info["txt"]

    keys = list(route_links)

    # -----------------------------------------------------
    # 2) Build link -> MAC-pair users
    # -----------------------------------------------------
    link_users = defaultdict(set)

    for k in keys:
        for lid in route_links[k]:
            link_users[lid].add(k)

    # -----------------------------------------------------
    # 3) Per-MAC-pair route overlap summary
    # -----------------------------------------------------
    rows = []

    for k in keys:
        src_mac, dst_mac = k
        links = route_links[k]

        overlapping_links = set()
        overlapping_routes = set()
        overlapping_mac_pairs = set()
        overlap_with_flows = []

        for other in keys:
            if k == other:
                continue

            shared = links & route_links[other]

            if not shared:
                continue

            overlapping_links |= shared
            overlapping_routes.add(other)
            overlapping_mac_pairs.add(canon_mac_pair(other[0], other[1]))

            overlap_with_flows.append(
                f"{host_name(other[0])}->{host_name(other[1])}"
                f"({len(shared)} shared link)"
            )

        per_link_overlap_counts = {
            lid: len(link_users[lid]) - 1
            for lid in links
        }

        max_overlap_on_any_link = max(
            per_link_overlap_counts.values(),
            default=0,
        )

        max_total_flows_on_any_link = max(
            (len(link_users[lid]) for lid in links),
            default=0,
        )

        most_overlapped_links = [
            link_txt.get(lid, lid)
            for lid, count in per_link_overlap_counts.items()
            if count == max_overlap_on_any_link
        ]

        per_link_overlap_text = []

        for lid in sorted(links):
            per_link_overlap_text.append(
                f"{link_txt.get(lid, lid)}: "
                f"total={len(link_users[lid])}, "
                f"others={len(link_users[lid]) - 1}"
            )

        rows.append({
            "timestamp": timestamp,

            "flow": f"{host_name(src_mac)}->{host_name(dst_mac)}",

            "src_mac": src_mac,
            "dst_mac": dst_mac,
            "mac_pair": canon_mac_pair(src_mac, dst_mac),
            "directed_mac_pair": f"{src_mac}->{dst_mac}",

            "active_route_link_count": len(links),
            "active_route_links": "; ".join(
                sorted(link_txt.get(x, x) for x in links)
            ),
            "active_route_link_ids": "; ".join(sorted(links)),

            "overlapped_link_count": len(overlapping_links),
            "overlapping_links": "; ".join(
                sorted(link_txt.get(x, x) for x in overlapping_links)
            ),
            "overlapping_link_ids": "; ".join(sorted(overlapping_links)),

            "overlapped_route_count": len(overlapping_routes),
            "overlapping_routes": "; ".join(
                sorted(
                    f"{host_name(a)}->{host_name(b)}"
                    for a, b in overlapping_routes
                )
            ),
            "overlapping_mac_pairs": "; ".join(sorted(overlapping_mac_pairs)),

            "overlap_with_flows": "; ".join(sorted(overlap_with_flows)),
            "per_link_overlap_counts": "; ".join(per_link_overlap_text),

            "max_overlap_on_any_link": max_overlap_on_any_link,
            "max_total_flows_on_any_link": max_total_flows_on_any_link,
            "most_overlapped_links": "; ".join(sorted(most_overlapped_links)),

            "example_flow_ids": "; ".join(sorted(route_ids[k])),
            "packets": route_pkts[k],
            "bytes": route_bytes[k],
        })

    rows = sorted(
        rows,
        key=lambda r: (
            r["overlapped_route_count"],
            r["overlapped_link_count"],
            r["max_overlap_on_any_link"],
            r["active_route_link_count"],
            r["bytes"],
        ),
        reverse=True,
    )

    header = [
        "timestamp",

        "flow",

        "src_mac",
        "dst_mac",
        "mac_pair",
        "directed_mac_pair",

        "active_route_link_count",
        "active_route_links",
        "active_route_link_ids",

        "overlapped_link_count",
        "overlapping_links",
        "overlapping_link_ids",

        "overlapped_route_count",
        "overlapping_routes",
        "overlapping_mac_pairs",

        "overlap_with_flows",
        "per_link_overlap_counts",

        "max_overlap_on_any_link",
        "max_total_flows_on_any_link",
        "most_overlapped_links",

        "example_flow_ids",
        "packets",
        "bytes",
    ]

    with open(ROUTE_OVERLAP_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)

    return len(active), len(rows)


# =====================================================
# MAIN COLLECTION
# =====================================================

def collect_once():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    now = time.time()

    flows = get_all_flows()

    # Internal rolling raw records only.
    # We do not write raw CSV anymore.
    for flow in flows:
        if not is_added_non_core_flow(flow):
            continue

        selector = flow.get("selector", {})
        treatment = flow.get("treatment", {})

        eth_src = norm_mac(get_criterion(selector, "ETH_SRC").get("mac"))
        eth_dst = norm_mac(get_criterion(selector, "ETH_DST").get("mac"))
        ipv4_src = norm_ip(get_criterion(selector, "IPV4_SRC").get("ip"))
        ipv4_dst = norm_ip(get_criterion(selector, "IPV4_DST").get("ip"))

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

    host_rows = write_host_summary_csv(timestamp)

    active_route_flows, route_rows = write_route_overlap_csv(
        timestamp,
        flows,
    )

    print(
        f"[{timestamp}] "
        f"host_summary_rows={host_rows}, "
        f"route_active_flows={active_route_flows}, "
        f"route_overlap_rows={route_rows}, "
        f"rolling_records={len(raw_flow_records)}"
    )


if __name__ == "__main__":
    while True:
        try:
            collect_once()
        except Exception as e:
            print("Error:", e)

        time.sleep(INTERVAL)