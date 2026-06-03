import requests, time, csv
from datetime import datetime
from collections import deque

# ==================================================
# CONFIG
# ==================================================
ONOS_BASE = "http://localhost:8181/onos/v1"
AUTH = ("onos", "rocks")

INTERVAL = 30                 # seconds
WINDOW_SECONDS = 10 * 60      # 50 minutes rolling

LINK_CSV = "link_stats_onos.csv"
HOST_CSV = "host_stats_onos.csv"

# ==================================================cant'
# COMMON HELPERS
# ==================================================
def now_iso():
    return datetime.now().isoformat()

# ==================================================
# LINK / PORT STATS (former link_load.py)
# ==================================================
LINK_HEADER = [
    "timestamp", "switch_id", "port",
    "rx_packets", "tx_packets", "rx_bytes", "tx_bytes"
]

link_buffer = deque()

def fetch_port_stats_raw():
    url = f"{ONOS_BASE}/statistics/ports"
    try:
        r = requests.get(url, auth=AUTH, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[!] Port stats error: {e}")
        return None

def update_link_stats(t_now):
    data = fetch_port_stats_raw()
    if not data:
        return 0

    ts = now_iso()
    rows = 0

    for dev_stat in data.get("statistics", []):
        dev = dev_stat.get("device")
        for p in dev_stat.get("ports", []):
            row = [
                ts, dev, p.get("port"),
                p.get("packetsReceived", 0),
                p.get("packetsSent", 0),
                p.get("bytesReceived", 0),
                p.get("bytesSent", 0)
            ]
            link_buffer.append((t_now, row))
            rows += 1

    while link_buffer and (t_now - link_buffer[0][0]) > WINDOW_SECONDS:
        link_buffer.popleft()

    with open(LINK_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(LINK_HEADER)
        for _, r in link_buffer:
            w.writerow(r)

    return rows

# ==================================================
# EDGE HOST STATS (former flow_stats.py)
# ==================================================
HOST_HEADER = [
    "timestamp","host_ip","host_mac","deviceId","port",
    "rx_bytes","tx_bytes","rx_packets","tx_packets",
    "rx_mbps","tx_mbps","rx_pps","tx_pps"
]

host_buffer = deque()
prev_stats = {}
prev_t = None

def fetch_hosts():
    url = f"{ONOS_BASE}/hosts"
    try:
        r = requests.get(url, auth=AUTH, timeout=5)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"[!] Host fetch error: {e}")
        return {}

    out = {}
    for h in data.get("hosts", []):
        ips = h.get("ipAddresses", [])
        mac = h.get("mac")
        locs = h.get("locations", [])
        if not locs:
            continue
        loc = locs[0]
        dev = loc.get("elementId") or loc.get("deviceId")
        port = loc.get("port")
        if dev and port is not None:
            out[(dev, int(port))] = {
                "ip": ips[0] if ips else None,
                "mac": mac
            }
    return out

def fetch_port_counters():
    data = fetch_port_stats_raw()
    if not data:
        return {}

    out = {}
    for dev_stat in data.get("statistics", []):
        dev = dev_stat.get("device")
        for p in dev_stat.get("ports", []):
            port = p.get("port")
            if port is None:
                continue
            out[(dev, int(port))] = {
                "rx_pkts": p.get("packetsReceived", 0),
                "tx_pkts": p.get("packetsSent", 0),
                "rx_bytes": p.get("bytesReceived", 0),
                "tx_bytes": p.get("bytesSent", 0),
            }
    return out

def update_host_stats(t_now):
    global prev_stats, prev_t

    hosts = fetch_hosts()
    curr = fetch_port_counters()
    if prev_t is None:
        prev_stats = curr
        prev_t = t_now
        return 0

    dt = max(1e-6, t_now - prev_t)
    ts = now_iso()
    rows = 0

    for key, h in hosts.items():
        if key not in curr:
            continue
        c = curr[key]
        p = prev_stats.get(key)

        # if p:
        #     rx_pps = (c["rx_pkts"] - p["rx_pkts"]) / dt
        #     tx_pps = (c["tx_pkts"] - p["tx_pkts"]) / dt
        #     rx_mbps = (c["rx_bytes"] - p["rx_bytes"]) * 8 / dt / 1e6
        #     tx_mbps = (c["tx_bytes"] - p["tx_bytes"]) * 8 / dt / 1e6
        # else:
        #     rx_pps = tx_pps = rx_mbps = tx_mbps = 0.0
        
        # new new new new
        if p:
            # Raw ONOS counters are switch-port view:
            # c["rx_*"] = host -> switch
            # c["tx_*"] = switch -> host

            # Host-view CSV:
            # rx_* = host receives traffic
            # tx_* = host sends traffic
            rx_pps = (c["tx_pkts"] - p["tx_pkts"]) / dt
            tx_pps = (c["rx_pkts"] - p["rx_pkts"]) / dt

            rx_mbps = (c["tx_bytes"] - p["tx_bytes"]) * 8 / dt / 1e6
            tx_mbps = (c["rx_bytes"] - p["rx_bytes"]) * 8 / dt / 1e6
        else:
            rx_pps = tx_pps = rx_mbps = tx_mbps = 0.0

        row = [
            ts, h["ip"], h["mac"],
            key[0], key[1],
            c["rx_bytes"], c["tx_bytes"],
            c["rx_pkts"], c["tx_pkts"],
            round(rx_mbps, 3), round(tx_mbps, 3),
            round(rx_pps, 2), round(tx_pps, 2)
        ]

        host_buffer.append((t_now, row))
        rows += 1

    while host_buffer and (t_now - host_buffer[0][0]) > WINDOW_SECONDS:
        host_buffer.popleft()

    with open(HOST_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(HOST_HEADER)
        for _, r in host_buffer:
            w.writerow(r)

    prev_stats = curr
    prev_t = t_now
    return rows

# ------------ work on link creation------------------ #

def canon_link_id(a_dev, a_port, b_dev, b_port):
    a = (a_dev, int(a_port))
    b = (b_dev, int(b_port))
    left, right = sorted([a, b])
    # return f"{left[0]}:{left[1]} <-> {right[0]}:{right[1]}"
    return f"{left[0]}:{left[1]} -> {right[0]}:{right[1]}"


def fetch_links():
    url = f"{ONOS_BASE}/links"
    try:
        r = requests.get(url, auth=AUTH, timeout=5)
        r.raise_for_status()
        return r.json().get("links", [])
    except Exception as e:
        print(f"[!] Links fetch error: {e}")
        return []

def build_unique_links(links_json):
    """
    Returns a list of unique UNDIRECTED links:
      [{"link_id":..., "a":(dev,port), "b":(dev,port)}, ...]
    """
    seen = set()
    out = []

    for L in links_json:
        sdev = L["src"]["device"]; sport = int(L["src"]["port"])
        ddev = L["dst"]["device"]; dport = int(L["dst"]["port"])

        a, b = sorted([(sdev, sport), (ddev, dport)])
        key = (a, b)
        if key in seen:
            continue
        seen.add(key)

        out.append({
            "link_id": canon_link_id(a[0], a[1], b[0], b[1]),
            "a": a,
            "b": b
        })

    return out


# LINK-LEVEL OUTPUT: one row per link (no endpoint columns)
# EDGE_HEADER = [
#     "timestamp", "link_id",
#     "rx_packets", "tx_packets",
#     "rx_bytes", "tx_bytes"
# ]

EDGE_HEADER = [
    "timestamp","link_id",
    "rx_packets","tx_packets",
    "rx_bytes","tx_bytes",
    "rx_mbps","tx_mbps",
    "rx_pps","tx_pps"
]

edge_buffer = deque()
prev_link_stats = {}
prev_link_t = None



def update_edge_stats(t_now):
    global prev_link_stats, prev_link_t
    # 1) unique links from topology
    links_json = fetch_links()
    uniq_links = build_unique_links(links_json)

    # 2) port counters from stats
    data = fetch_port_stats_raw()
    if not data:
        return 0

    ep_counters = {}
    for dev_stat in data.get("statistics", []):
        dev = dev_stat.get("device")
        for p in dev_stat.get("ports", []):
            port = p.get("port")
            if port is None:
                continue
            ep_counters[(dev, int(port))] = {
                "rx_pkts":  p.get("packetsReceived", 0),
                "tx_pkts":  p.get("packetsSent", 0),
                "rx_bytes": p.get("bytesReceived", 0),
                "tx_bytes": p.get("bytesSent", 0),
            }

    # 3) aggregate per link (sum endpoints)
    ts = now_iso()
    rows = 0

    # ///////
    if prev_link_t is None:
        prev_link_t = t_now
    # //////

    for L in uniq_links:
        a = L["a"]
        b = L["b"]

        a_cnt = ep_counters.get(a, {"rx_pkts":0,"tx_pkts":0,"rx_bytes":0,"tx_bytes":0})
        b_cnt = ep_counters.get(b, {"rx_pkts":0,"tx_pkts":0,"rx_bytes":0,"tx_bytes":0})

        # rx_packets = a_cnt["rx_pkts"]  + b_cnt["rx_pkts"]
        # tx_packets = a_cnt["tx_pkts"]  + b_cnt["tx_pkts"]
        # rx_bytes   = a_cnt["rx_bytes"] + b_cnt["rx_bytes"]
        # tx_bytes   = a_cnt["tx_bytes"] + b_cnt["tx_bytes"]

        # row = [ts, L["link_id"], rx_packets, tx_packets, rx_bytes, tx_bytes]

        # ////////////////
        link_id = L["link_id"]

        rx_packets = a_cnt["rx_pkts"]  + b_cnt["rx_pkts"]
        tx_packets = a_cnt["tx_pkts"]  + b_cnt["tx_pkts"]
        rx_bytes   = a_cnt["rx_bytes"] + b_cnt["rx_bytes"]
        tx_bytes   = a_cnt["tx_bytes"] + b_cnt["tx_bytes"]

        dt = max(1e-6, t_now - prev_link_t)
        prev = prev_link_stats.get(link_id)

        if prev:
            rx_mbps = (rx_bytes - prev["rx_bytes"]) * 8 / dt / 1e6
            tx_mbps = (tx_bytes - prev["tx_bytes"]) * 8 / dt / 1e6
        else:
            rx_mbps = tx_mbps = 0.0

        # //////////////////////////////////////
        if prev:
            drx_bytes = rx_bytes - prev["rx_bytes"]
            dtx_bytes = tx_bytes - prev["tx_bytes"]

            drx_pkts = rx_packets - prev["rx_packets"]
            dtx_pkts = tx_packets - prev["tx_packets"]

            # protect against counter reset
            drx_bytes = max(0, drx_bytes)
            dtx_bytes = max(0, dtx_bytes)
            drx_pkts  = max(0, drx_pkts)
            dtx_pkts  = max(0, dtx_pkts)

            rx_mbps = drx_bytes * 8 / dt / 1e6
            tx_mbps = dtx_bytes * 8 / dt / 1e6

            rx_pps = drx_pkts / dt
            tx_pps = dtx_pkts / dt
        else:
            rx_mbps = tx_mbps = 0.0
            rx_pps  = tx_pps  = 0.0

        # /////////////////////////////////////////

        
        # prev_link_stats[link_id] = {
        #     "rx_bytes": rx_bytes,
        #     "tx_bytes": tx_bytes
        # }
        # ////////////////////
        prev_link_stats[link_id] = {
            "rx_bytes": rx_bytes,
            "tx_bytes": tx_bytes,
            "rx_packets": rx_packets,
            "tx_packets": tx_packets
        }
        # ///////////////////


        row = [
            ts,
            link_id,
            rx_packets,
            tx_packets,
            rx_bytes,
            tx_bytes,
            round(rx_mbps,3),
            round(tx_mbps,3),
            round(rx_pps,2),
            round(tx_pps,2)
        ]
        # ////////////////
        edge_buffer.append((t_now, row))
        rows += 1

    # 4) rolling window
    while edge_buffer and (t_now - edge_buffer[0][0]) > WINDOW_SECONDS:
        edge_buffer.popleft()

    # 5) write CSV
    with open("link_stats_onos.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(EDGE_HEADER)
        for _, r in edge_buffer:
            w.writerow(r)
    
    # ///////////////
    prev_link_t = t_now
    # //////////////
    return rows

#--------------link creation ends-----------------------#

# ==================================================
# MAIN LOOP
# ==================================================
print("[*] ONOS link + host logging started (30s, rolling 15min). Ctrl+C to stop.")

try:
    while True:
        t = time.time()

        # n_links = update_link_stats(t)
        n_hosts = update_host_stats(t)

        # print(f"[{now_iso()}] Links: {n_links}, Edge-hosts: {n_hosts}")
        n_links = update_edge_stats(t) #------link-creation------_#
        print(f"[{now_iso()}] Links: {n_links}, Hosts: {n_hosts}")

        time.sleep(INTERVAL)

except KeyboardInterrupt:
    print("\n[*] Logging stopped.")
