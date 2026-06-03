#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generic reliable IP hopper for Mininet hosts.
ROLLBACK VERSION: uses original set_ip_and_verify() (flushes iface),
then re-applies NAT (adds external IP + iptables DNAT/SNAT) after each hop.

Examples:
  sudo python ip_hopper.py --host h1 --ips "90;30;80" --interval 60
  sudo python ip_hopper.py -H h2 -i "10.0.0.22,10.0.0.33" --cidr 24
"""
import socket
import os
import sys
import random
import time
import argparse
import subprocess
import shutil
import re
import requests
import json
# ------------------ NAT MAPPING (host -> ext ip/port/opalside) ------------------


PING_FLAG_FILE = "/tmp/mutual_ping_flag.txt"   # define once near top (global)



mac_list= [
# "00:00:00:00:00:01",
"00:00:00:00:00:28",
"00:00:00:00:00:02",
"00:00:00:00:00:03",
"00:00:00:00:00:04",
"00:00:00:00:00:05",
"00:00:00:00:00:06",
"00:00:00:00:00:07",
"00:00:00:00:00:08",
"00:00:00:00:00:09",
"00:00:00:00:00:0A",
"00:00:00:00:00:0B",
"00:00:00:00:00:0C",
"00:00:00:00:00:0D",
"00:00:00:00:00:0E",
"00:00:00:00:00:0F",
"00:00:00:00:00:10",
"00:00:00:00:00:11",
"00:00:00:00:00:12",
"00:00:00:00:00:13",
"00:00:00:00:00:14",
"00:00:00:00:00:15",
"00:00:00:00:00:16",
"00:00:00:00:00:17",
"00:00:00:00:00:18",
"00:00:00:00:00:19",
"00:00:00:00:00:1A",
"00:00:00:00:00:1B",
"00:00:00:00:00:1C",
"00:00:00:00:00:1D",
"00:00:00:00:00:1E",
"00:00:00:00:00:1F",
"00:00:00:00:00:20",
"00:00:00:00:00:21",
"00:00:00:00:00:22",
"00:00:00:00:00:23",
"00:00:00:00:00:24",
"00:00:00:00:00:25",
"00:00:00:00:00:26",
"00:00:00:00:00:27",
]

H_EXT_IPS = {
    "h1": "192.168.140.200/24",
    "h2": "192.168.102.200/24",
    "h3": "192.168.103.200/24",
    "h4": "192.168.104.200/24",
    "h5": "192.168.105.200/24",
    "h6": "192.168.106.200/24",
    "h7": "192.168.107.200/24",
    "h8": "192.168.108.200/24",
    "h9": "192.168.109.200/24",
    "h10": "192.168.110.200/24",
    "h11": "192.168.111.200/24",
    "h12": "192.168.112.200/24",
    "h13": "192.168.113.200/24",
    "h14": "192.168.114.200/24",
    "h15": "192.168.115.200/24",
    "h16": "192.168.116.200/24",
    "h17": "192.168.117.200/24",
    "h18": "192.168.118.200/24",
    "h19": "192.168.119.200/24",
    "h20": "192.168.120.200/24",
    "h21": "192.168.121.200/24",
    "h22": "192.168.122.200/24",
    "h23": "192.168.123.200/24",
    "h24": "192.168.124.200/24",
    "h25": "192.168.125.200/24",
    "h26": "192.168.126.200/24",
    "h27": "192.168.127.200/24",
    "h28": "192.168.128.200/24",
    "h29": "192.168.129.200/24",
    "h30": "192.168.130.200/24",
    "h31": "192.168.131.200/24",
    "h32": "192.168.132.200/24",
    "h33": "192.168.133.200/24",
    "h34": "192.168.134.200/24",
    "h35": "192.168.135.200/24",
    "h36": "192.168.136.200/24",
    "h37": "192.168.137.200/24",
    "h38": "192.168.138.200/24",
    "h39": "192.168.139.200/24",
    "h40": "192.168.101.200/24",
}

H_EXT_PORTS = {
    "h1": "4789",
    "h2": "4713",
    "h3": "4715",
    "h4": "4717",
    "h5": "4719",
    "h6": "4721",
    "h7": "4723",
    "h8": "4725",
    "h9": "4727",
    "h10": "4729",
    "h11": "4731",
    "h12": "4733",
    "h13": "4735",
    "h14": "4737",
    "h15": "4739",
    "h16": "4741",
    "h17": "4743",
    "h18": "4745",
    "h19": "4747",
    "h20": "4749",
    "h21": "4751",
    "h22": "4753",
    "h23": "4755",
    "h24": "4757",
    "h25": "4759",
    "h26": "4761",
    "h27": "4763",
    "h28": "4765",
    "h29": "4767",
    "h30": "4769",
    "h31": "4771",
    "h32": "4773",
    "h33": "4775",
    "h34": "4777",
    "h35": "4779",
    "h36": "4781",
    "h37": "4783",
    "h38": "4785",
    "h39": "4787",
    "h40": "4711",
}

OPAL_IPS = {
    "h1": "192.168.140.101",
    "h2": "192.168.102.101",
    "h3": "192.168.103.101",
    "h4": "192.168.104.101",
    "h5": "192.168.105.101",
    "h6": "192.168.106.101",
    "h7": "192.168.107.101",
    "h8": "192.168.108.101",
    "h9": "192.168.109.101",
    "h10": "192.168.110.101",
    "h11": "192.168.111.101",
    "h12": "192.168.112.101",
    "h13": "192.168.113.101",
    "h14": "192.168.114.101",
    "h15": "192.168.115.101",
    "h16": "192.168.116.101",
    "h17": "192.168.117.101",
    "h18": "192.168.118.101",
    "h19": "192.168.119.101",
    "h20": "192.168.120.101",
    "h21": "192.168.121.101",
    "h22": "192.168.122.101",
    "h23": "192.168.123.101",
    "h24": "192.168.124.101",
    "h25": "192.168.125.101",
    "h26": "192.168.126.101",
    "h27": "192.168.127.101",
    "h28": "192.168.128.101",
    "h29": "192.168.129.101",
    "h30": "192.168.130.101",
    "h31": "192.168.131.101",
    "h32": "192.168.132.101",
    "h33": "192.168.133.101",
    "h34": "192.168.134.101",
    "h35": "192.168.135.101",
    "h36": "192.168.136.101",
    "h37": "192.168.137.101",
    "h38": "192.168.138.101",
    "h39": "192.168.139.101",
    "h40": "192.168.101.101",
}

# ------------------ defaults ------------------
DEFAULT_HOP_INTERVAL = 15
DEFAULT_CIDR = 24
DEFAULT_LOW, DEFAULT_HIGH = 50, 250
DEFAULT_AVOID = "10.0.0.55"

# --- ONOS settings ---
ONOS = "http://127.0.0.1:8181/onos/v1"
AUTH = ("onos", "rocks")

# ------------------ shell helpers ------------------
def sh(cmd):
    return subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode("utf-8", "ignore")

def try_sh(cmd):
    try:
        return True, sh(cmd)
    except subprocess.CalledProcessError as e:
        out = e.output.decode("utf-8", "ignore") if getattr(e, "output", None) else ""
        return False, out

# ------------------ PID discovery ------------------
def pidfile_for_host(host):
    return f"/var/run/mininet/{host}.pid"

def find_host_pid_once(host):
    pidfile = pidfile_for_host(host)
    try:
        with open(pidfile, "r") as f:
            p = f.read().strip()
            if p.isdigit() and os.path.exists(f"/proc/{p}/ns/net"):
                return p
    except Exception:
        pass

    ok, out = try_sh(f"ps -eo pid,cmd | grep 'mininet:{host}' | grep -v grep | awk 'NR==1{{print $1}}'")
    if ok:
        p = out.strip()
        if p.isdigit() and os.path.exists(f"/proc/{p}/ns/net"):
            return p

    ok2, out2 = try_sh(f"ps -eo pid,cmd | grep mnexec | grep -v grep | grep '{host}' | awk 'NR==1{{print $1}}'")
    if ok2:
        p2 = out2.strip()
        if p2.isdigit() and os.path.exists(f"/proc/{p2}/ns/net"):
            return p2

    return None

def get_host_pid(host, block=True, poll=1.0):
    printed = False
    while True:
        pid = find_host_pid_once(host)
        if pid:
            return pid
        if not block:
            return None
        if not printed:
            print(f"[-] No {host} PID yet. In Mininet run:  {host} bash -c 'sleep infinity' &")
            printed = True
        time.sleep(poll)

# ------------------ iface detection ------------------
def detect_iface(pid):
    ok, out = try_sh(f"mnexec -a {pid} -- ip -o link")
    if not ok:
        raise RuntimeError("Could not list links inside host namespace:\n" + out)

    names = []
    for line in out.splitlines():
        m = re.search(r":\s*([^:]+):", line)
        if m:
            names.append(m.group(1).split("@", 1)[0])

    for n in names:
        if n.endswith("-eth0"):
            return n
    if "eth0" in names:
        return "eth0"
    for n in names:
        if n != "lo":
            return n
    raise RuntimeError("No usable interface inside host namespace")

# ------------------ file write ------------------
def atomic_write(path, contents):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(contents + "\n")
    os.replace(tmp, path)

# ------------------ ip utils ------------------
def parse_ips_arg(ips_arg):
    items = re.split(r"[;,]+", ips_arg.strip())
    cleaned = []
    for it in items:
        it = it.strip()
        if not it:
            continue
        if re.fullmatch(r"\d{1,3}", it):
            num = int(it)
            if not (1 <= num <= 254):
                raise argparse.ArgumentTypeError(f"invalid last-octet number: {it}")
            cleaned.append(f"10.0.0.{num}")
        elif re.fullmatch(r"\d+\.\d+\.\d+\.\d+", it):
            cleaned.append(it)
        else:
            raise argparse.ArgumentTypeError(f"invalid IP or octet: {it}")
    return cleaned

def rand_ip_from_list(low, high, avoid_set):
    while True:
        ip = "10.0.0.%d" % random.randint(low, high)
        if ip not in avoid_set:
            return ip

def ip_present(pid, iface, ip):
    ok, out = try_sh(f"mnexec -a {pid} -- ip -4 -o addr show dev {iface}")
    if not ok:
        return False
    return any((" inet " in line and (ip + "/") in line) for line in out.splitlines())

def set_ip_and_verify(pid, iface, ip, cidr):
    """
    ORIGINAL behavior:
      - flush ALL IPv4 addresses on iface
      - add new internal IP
      - link up
      - optional GARP
    """
    cmds = [
        f"ip -4 addr flush dev {iface}",
        f"ip addr add {ip}/{cidr} dev {iface}",
        f"ip link set {iface} up",
    ]
    if shutil.which("arping"):
        cmds.append(f"arping -U -c 2 -I {iface} {ip} >/dev/null 2>&1 || true")

    joined = " && ".join(cmds)
    _ok, _out = try_sh(f"mnexec -a {pid} -- bash -c \"{joined}\"")

    if ip_present(pid, iface, ip):
        print(f"[HOP] {ip}")
        return True

    print("[-] Could not verify IP on iface after setting. Debug dump:")
    _ok2, dump = try_sh(f"mnexec -a {pid} -- ip -4 addr show dev {iface}")
    if dump.strip():
        print(dump.strip())
    return False

# ------------------ ONOS host removal ------------------
def infer_mac_from_host(host):
    try:
        num = int(host[1:])
        return "00:00:00:00:00:%02x" % num
    except Exception:
        print(f"[!] Could not infer MAC for {host}")
        return None

def host_remove(host):
    mac = infer_mac_from_host(host)
    if not mac:
        return
    url = f"{ONOS}/hosts/{mac}/None"
    try:
        r = requests.delete(url, auth=AUTH)
        print(f"[ONOS] remove {host} ({mac}): {r.status_code}")
    except Exception as e:
        print(f"[!] Error removing {host} ({mac}): {e}")

# ------------------ NAT reapply (called after each hop) ------------------
def reapply_nat_and_routes_if_needed(host, pid, iface, new_internal_ip):
    """
    After IP hop (which flushes iface), restore:
      - external IP on same iface
      - ip_forward
      - DNAT (tcp+udp) for current internal IP:port -> OPAL:port
      - FORWARD accept
      - MASQUERADE to OPAL
      - optional ICMP + ext->int MASQ (as in your working script)
    """
    ext = H_EXT_IPS.get(host)
    opal_ip = OPAL_IPS.get(host)
    port_str = H_EXT_PORTS.get(host)

    if not ext or not opal_ip or not port_str:
        return

    try:
        port = int(port_str)
    except Exception:
        print(f"[!] Invalid port for {host}: {port_str}")
        return

    ext_ip = ext.split("/")[0]
    parts = ext_ip.split(".")
    ext_nw = ".".join(parts[:3] + ["0/24"])

    dnat_match_ip = new_internal_ip

    cmds = [
        # restore external IP (lost due to ip flush)
        f"ip addr add {ext} dev {iface} 2>/dev/null || true",
        "sysctl -w net.ipv4.ip_forward=1 >/dev/null",

        # reset NAT/filter in this host namespace (matches your working script)
        "iptables -t nat -F",
        "iptables -F",

        # DNAT TCP + UDP to OPAL
        f"iptables -t nat -A PREROUTING -p tcp -d {dnat_match_ip} --dport {port} "
        f"-j DNAT --to-destination {opal_ip}:{port}",
        f"iptables -t nat -A PREROUTING -p udp -d {dnat_match_ip} --dport {port} "
        f"-j DNAT --to-destination {opal_ip}:{port}",

        # Allow forwarding TCP + UDP
        f"iptables -A FORWARD -p tcp --dport {port} -j ACCEPT",
        f"iptables -A FORWARD -p udp --dport {port} -j ACCEPT",

        # SNAT so OPAL replies return via this host
        f"iptables -t nat -A POSTROUTING -d {opal_ip} -j MASQUERADE",

        # Optional extras (same style as your script)
        "iptables -A FORWARD -p icmp -j ACCEPT",
        f"iptables -t nat -A POSTROUTING -s {ext_nw} -d 10.0.0.0/24 -j MASQUERADE",
    ]

    joined = " && ".join(cmds)
    ok, out = try_sh(f"mnexec -a {pid} -- bash -c \"{joined}\"")
    if ok:
        print(f"[NAT] {host}: ext={ext} internal={new_internal_ip} "
              f"DNAT {dnat_match_ip}:{port} -> {opal_ip}:{port}")
    else:
        print(f"[!] NAT reapply failed for {host}:\n{out}")



def send_last_octets(target_ip='192.168.10.48', port=5000):
    """
    Creates a TCP socket, connects to the target IP and port,
    and sends 39 rows of last octets.
    """
    # Example data: last octets of IPs 
    resp = requests.get(ONOS + "/hosts", auth=AUTH, timeout=5)
    resp.raise_for_status()
    data = resp.json()
    hosts = data.get("hosts", [])  # safer than ["hosts"]

    mac_to_ip = {h["mac"]: h.get("ipAddresses", []) for h in hosts}

    for mac in mac_list:
        ips =mac_to_ip.get(mac,[])
        print(mac,ips if ips else "no_ip_found")
    # last_octets = [ip.split(".")[-1] for ips in mac_to_ip.values() for ip in ips]
    last_octets = []
    for mac in mac_list:
        ips = mac_to_ip.get(mac, [])
        ip_10 = next((ip for ip in ips if ip.startswith("10.0.0.")), None)
        last_octets.append(ip_10.split(".")[-1] if ip_10 else "no_ip_found")

    print(last_octets)
    try:
        # 1️⃣ Create TCP socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            print(f"Connecting to {target_ip}:{port}...")
            s.connect((target_ip, port))
            print("Connected.")

            # 2️⃣ Send each row
            # for octet in last_octets:
            #     # Send as bytes, add newline for separation
            #     s.sendall((octet).encode('utf-8'))
            
            
            data_array=list(last_octets)
            json_data=json.dumps(data_array)
            s.sendall((json_data).encode('utf-8'))


            print("All rows sent successfully!")

    except Exception as e:
        print(f"Error: {e}")

def learn_onos(host, new_ip):
    anchor = "h1"
    if host == anchor:
        return

    p_anchor = get_host_pid(anchor, block=True)
    p_host   = get_host_pid(host, block=True)

    # get anchor current 10.0.0.x IP
    ok, out = try_sh(
        f"mnexec -a {p_anchor} -- bash -lc "
        "\"ip -4 -o addr show scope global | awk '{print $4}'\""
    )

    if not ok:
        print("[LEARN] could not read h1 IP")
        return

    anchor_ip = None
    for tok in out.split():
        ip_only = tok.split("/")[0]
        if ip_only.startswith("10.0.0."):
            anchor_ip = ip_only
            break

    if not anchor_ip:
        print("[LEARN] no 10.0.0.x on h1")
        return

    # ping by IP (NOT hostname)
    try_sh(f"mnexec -a {p_anchor} -- ping -c 4 -W 1 {new_ip} >/dev/null 2>&1 || true")
    try_sh(f"mnexec -a {p_host}   -- ping -c 4 -W 1 {anchor_ip} >/dev/null 2>&1 || true")

    print(f"[LEARN] {anchor}({anchor_ip}) <-> {host}({new_ip})")


# ------------------ NEW: multi-host parsing ------------------
def parse_hosts_arg(host_arg: str):
    # "--host h1,h2,h3" -> ["h1","h2","h3"]
    hosts = [h.strip() for h in re.split(r"[;,]+", host_arg.strip()) if h.strip()]
    # optional: basic validation
    for h in hosts:
        if not re.fullmatch(r"h\d+", h):
            raise argparse.ArgumentTypeError(f"invalid host name: {h}")
    return hosts

def is_dir_path(p: str):
    return p and (p.endswith("/") or os.path.isdir(p))

def ipfile_for_host(ipfile_arg: str, host: str):
    """
    If user provides:
      - None -> /tmp/rrm_<host>_ip.txt
      - directory -> <dir>/rrm_<host>_ip.txt
      - template containing {host} -> formatted
      - plain file -> if multiple hosts, we auto-suffix by host
    """
    if not ipfile_arg:
        return f"/tmp/rrm_{host}_ip.txt"

    if "{host}" in ipfile_arg:
        return ipfile_arg.format(host=host)

    if is_dir_path(ipfile_arg):
        d = ipfile_arg.rstrip("/")
        return f"{d}/rrm_{host}_ip.txt"

    # plain file path
    return ipfile_arg

def build_host_ip_map(hosts, ips_list):
    """
    Deterministic mapping: hosts[i] -> ips_list[i]
    Requires len(ips_list) >= len(hosts)
    """
    if not ips_list or len(ips_list) < len(hosts):
        raise ValueError(f"Need at least {len(hosts)} IPs for {len(hosts)} hosts, got {0 if not ips_list else len(ips_list)}")
    return {hosts[i]: ips_list[i] for i in range(len(hosts))}


# ------------------ REPLACE main() WITH THIS ------------------
def main():
    ap = argparse.ArgumentParser(description="Reliable IP hopper for Mininet hosts (multi-host capable)")
    ap.add_argument("--host", "-H", required=True,
                    help="Mininet host(s). Single: h1  | Multiple: h1,h2,h3")
    ap.add_argument("--interval", "-t", type=int, default=DEFAULT_HOP_INTERVAL,
                    help="seconds between hops")
    ap.add_argument("--cidr", type=int, default=DEFAULT_CIDR,
                    help="CIDR for internal IP (default 24)")
    ap.add_argument("--ips", "-i", required=False,
                    help="For single host: list of last-octets or full IPs. "
                         "For multi-host mapping: provide >= number of hosts. "
                         "Example: --host h1,h2,h3 --ips '10,20,30'")
    ap.add_argument("--low", type=int, default=DEFAULT_LOW)
    ap.add_argument("--high", type=int, default=DEFAULT_HIGH)
    ap.add_argument("--avoid", default=DEFAULT_AVOID,
                    help="comma/semicolon-separated IPs to avoid (only used when random picking)")
    ap.add_argument("--ipfile", default=None,
                    help="(optional) file/dir/template. "
                         "Dir: /tmp/ips/  | Template: /tmp/rrm_{host}_ip.txt")
    ap.add_argument("--no-block-pid", action="store_true",
                    help="if set, do not block waiting for host pid")
    args = ap.parse_args()

    hosts = parse_hosts_arg(args.host)
    avoid_set = set(ip.strip() for ip in re.split(r"[;,]+", args.avoid) if ip.strip())

    ips_list = None
    if args.ips:
        try:
            ips_list = parse_ips_arg(args.ips)  # you already have this
        except Exception as e:
            print(f"Error parsing --ips: {e}")
            sys.exit(2)

    # If multiple hosts + ips provided -> deterministic host->ip mapping
    host_ip_map = None
    if len(hosts) > 1 and ips_list:
        try:
            host_ip_map = build_host_ip_map(hosts, ips_list)
        except Exception as e:
            print(f"Error building host->ip mapping: {e}")
            sys.exit(2)

    # Cache pid/iface per host
    state = {}  # host -> {"pid":..., "iface":...}

    def ensure_host_state(h):
        pid = get_host_pid(h, block=not args.no_block_pid)
        if not pid:
            print(f"[-] Could not find pid for {h}")
            return None
        iface = detect_iface(pid)
        prev = state.get(h)
        if (not prev) or (prev["pid"] != pid) or (prev["iface"] != iface):
            state[h] = {"pid": pid, "iface": iface}
            print(f"[i] {h} PID {pid}, iface {iface}")
        return state[h]

    # Loop forever (like before), but hop ALL hosts each cycle
    while True:
        for h in hosts:
            st = ensure_host_state(h)
            if not st:
                continue

            pid = st["pid"]
            iface = st["iface"]
            ipfile = ipfile_for_host(args.ipfile, h)

            # Choose IP
            if host_ip_map:
                ip = host_ip_map[h]  # deterministic
                if ip in avoid_set:
                    print(f"[-] {h}: mapped ip {ip} is in avoid list; skipping")
                    continue
            else:
                # single host or no mapping -> existing behavior
                if ips_list:
                    ip = random.choice(ips_list)
                    if ip in avoid_set:
                        print(f"[-] {h}: chosen ip {ip} is in avoid list; retrying")
                        continue
                else:
                    ip = rand_ip_from_list(args.low, args.high, avoid_set)

            # Set IP (flush iface) + write file + reapply NAT
            ok = set_ip_and_verify(pid, iface, ip, args.cidr)
            if not ok:
                print(f"[-] {h}: IP set/verify failed for {ip}")
                continue

            atomic_write(ipfile, ip)
            print(f"[WROTE] {ipfile} <- {ip}")

            reapply_nat_and_routes_if_needed(h, pid, iface, ip)

            # Your existing ONOS relearn + metadata steps
            host_remove(h)
            learn_onos(h, ip)

        # One flag write per cycle (not per host)
        atomic_write(PING_FLAG_FILE, "1")
        print("[FLAG] wrote 1 (request relearn)")

        # One ONOS host list send per cycle (not per host)
        try:
            send_last_octets('192.168.10.48', 5000)
        except Exception as e:
            print(f"[!] send_last_octets failed: {e}")

        # time.sleep(args.interval)
        return
#  sudo python3 ip_hopper.py --host h1,h2,h3 --ips "10,20,30" --interval 15
if __name__ == "__main__":
    if os.geteuid() != 0:
        os.execvp("sudo", ["sudo", "-E", sys.executable] + sys.argv)
    main()