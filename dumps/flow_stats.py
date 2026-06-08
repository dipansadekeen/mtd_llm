demo code but probably garbage.

import requests
import csv
import time
from datetime import datetime

ONOS_IP = "127.0.0.1"
ONOS_PORT = "8181"
USERNAME = "onos"
PASSWORD = "rocks"
INTERVAL = 5

FLOW_CSV = "onos_flow_stats.csv"
HOST_CSV = "onos_host_map.csv"
CONN_CSV = "onos_connection_map.csv"

connection_first_seen = {}


def onos_get(endpoint):
    url = f"http://{ONOS_IP}:{ONOS_PORT}{endpoint}"
    r = requests.get(url, auth=(USERNAME, PASSWORD), timeout=10)
    r.raise_for_status()
    return r.json()


def init_csv(file, header):
    try:
        with open(file, "x", newline="") as f:
            csv.writer(f).writerow(header)
    except FileExistsError:
        pass


def get_criterion(selector, field):
    for c in selector.get("criteria", []):
        if c.get("type") == field:
            return c
    return {}


def log_hosts(timestamp):
    hosts = onos_get("/onos/v1/hosts").get("hosts", [])

    with open(HOST_CSV, "a", newline="") as f:
        writer = csv.writer(f)

        for h in hosts:
            writer.writerow([
                timestamp,
                h.get("id"),
                ",".join(h.get("mac", [])) if isinstance(h.get("mac"), list) else h.get("mac"),
                ",".join(h.get("ipAddresses", [])),
                h.get("vlan"),
                h.get("locations", [{}])[0].get("elementId"),
                h.get("locations", [{}])[0].get("port")
            ])

    print(f"Logged {len(hosts)} hosts")


def log_flows_and_connections(timestamp):
    flows = onos_get("/onos/v1/flows").get("flows", [])

    with open(FLOW_CSV, "a", newline="") as f_flow, open(CONN_CSV, "a", newline="") as f_conn:
        flow_writer = csv.writer(f_flow)
        conn_writer = csv.writer(f_conn)

        for flow in flows:
            selector = flow.get("selector", {})
            treatment = flow.get("treatment", {})

            eth_src = get_criterion(selector, "ETH_SRC").get("mac")
            eth_dst = get_criterion(selector, "ETH_DST").get("mac")
            ipv4_src = get_criterion(selector, "IPV4_SRC").get("ip")
            ipv4_dst = get_criterion(selector, "IPV4_DST").get("ip")
            in_port = get_criterion(selector, "IN_PORT").get("port")

            device_id = flow.get("deviceId")
            flow_id = flow.get("id")

            conn_key = f"{eth_src}|{eth_dst}|{ipv4_src}|{ipv4_dst}|{device_id}"

            if conn_key not in connection_first_seen:
                connection_first_seen[conn_key] = time.time()

            active_age_sec = round(time.time() - connection_first_seen[conn_key], 2)

            flow_writer.writerow([
                timestamp,
                device_id,
                flow_id,
                flow.get("state"),
                flow.get("priority"),
                flow.get("packets"),
                flow.get("bytes"),
                flow.get("life"),
                flow.get("appId"),
                eth_src,
                eth_dst,
                ipv4_src,
                ipv4_dst,
                in_port,
                selector,
                treatment
            ])

            conn_writer.writerow([
                timestamp,
                conn_key,
                eth_src,
                eth_dst,
                ipv4_src,
                ipv4_dst,
                device_id,
                flow_id,
                flow.get("packets"),
                flow.get("bytes"),
                flow.get("life"),
                active_age_sec,
                flow.get("state")
            ])

    print(f"Logged {len(flows)} flows/connections")


if __name__ == "__main__":
    init_csv(FLOW_CSV, [
        "timestamp", "deviceId", "flowId", "state", "priority",
        "packets", "bytes", "life", "appId",
        "eth_src", "eth_dst", "ipv4_src", "ipv4_dst",
        "in_port", "selector", "treatment"
    ])

    init_csv(HOST_CSV, [
        "timestamp", "host_id", "mac", "ipAddresses",
        "vlan", "switch_id", "port"
    ])

    init_csv(CONN_CSV, [
        "timestamp", "connection_id", "eth_src", "eth_dst",
        "ipv4_src", "ipv4_dst", "deviceId", "flowId",
        "packets", "bytes", "flow_life_sec",
        "observed_active_age_sec", "state"
    ])

    while True:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            log_hosts(timestamp)
            log_flows_and_connections(timestamp)
        except Exception as e:
            print("Error:", e)

        time.sleep(INTERVAL)

