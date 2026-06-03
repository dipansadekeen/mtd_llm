#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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
from mtd_utils import HostIPQueueManager #new

class IPHopper:
    # PING_FLAG_FILE = "/tmp/mutual_ping_flag.txt"

    mac_list = [
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
        "h1": "192.168.140.200/24", "h2": "192.168.102.200/24", "h3": "192.168.103.200/24",
        "h4": "192.168.104.200/24", "h5": "192.168.105.200/24", "h6": "192.168.106.200/24",
        "h7": "192.168.107.200/24", "h8": "192.168.108.200/24", "h9": "192.168.109.200/24",
        "h10": "192.168.110.200/24", "h11": "192.168.111.200/24", "h12": "192.168.112.200/24",
        "h13": "192.168.113.200/24", "h14": "192.168.114.200/24", "h15": "192.168.115.200/24",
        "h16": "192.168.116.200/24", "h17": "192.168.117.200/24", "h18": "192.168.118.200/24",
        "h19": "192.168.119.200/24", "h20": "192.168.120.200/24", "h21": "192.168.121.200/24",
        "h22": "192.168.122.200/24", "h23": "192.168.123.200/24", "h24": "192.168.124.200/24",
        "h25": "192.168.125.200/24", "h26": "192.168.126.200/24", "h27": "192.168.127.200/24",
        "h28": "192.168.128.200/24", "h29": "192.168.129.200/24", "h30": "192.168.130.200/24",
        "h31": "192.168.131.200/24", "h32": "192.168.132.200/24", "h33": "192.168.133.200/24",
        "h34": "192.168.134.200/24", "h35": "192.168.135.200/24", "h36": "192.168.136.200/24",
        "h37": "192.168.137.200/24", "h38": "192.168.138.200/24", "h39": "192.168.139.200/24",
        "h40": "192.168.101.200/24",
    }

    H_EXT_PORTS = {
        "h1": "4789", "h2": "4713", "h3": "4715", "h4": "4717", "h5": "4719", "h6": "4721",
        "h7": "4723", "h8": "4725", "h9": "4727", "h10": "4729", "h11": "4731", "h12": "4733",
        "h13": "4735", "h14": "4737", "h15": "4739", "h16": "4741", "h17": "4743", "h18": "4745",
        "h19": "4747", "h20": "4749", "h21": "4751", "h22": "4753", "h23": "4755", "h24": "4757",
        "h25": "4759", "h26": "4761", "h27": "4763", "h28": "4765", "h29": "4767", "h30": "4769",
        "h31": "4771", "h32": "4773", "h33": "4775", "h34": "4777", "h35": "4779", "h36": "4781",
        "h37": "4783", "h38": "4785", "h39": "4787", "h40": "4711",
    }

    OPAL_IPS = {
        "h1": "192.168.140.101", "h2": "192.168.102.101", "h3": "192.168.103.101",
        "h4": "192.168.104.101", "h5": "192.168.105.101", "h6": "192.168.106.101",
        "h7": "192.168.107.101", "h8": "192.168.108.101", "h9": "192.168.109.101",
        "h10": "192.168.110.101", "h11": "192.168.111.101", "h12": "192.168.112.101",
        "h13": "192.168.113.101", "h14": "192.168.114.101", "h15": "192.168.115.101",
        "h16": "192.168.116.101", "h17": "192.168.117.101", "h18": "192.168.118.101",
        "h19": "192.168.119.101", "h20": "192.168.120.101", "h21": "192.168.121.101",
        "h22": "192.168.122.101", "h23": "192.168.123.101", "h24": "192.168.124.101",
        "h25": "192.168.125.101", "h26": "192.168.126.101", "h27": "192.168.127.101",
        "h28": "192.168.128.101", "h29": "192.168.129.101", "h30": "192.168.130.101",
        "h31": "192.168.131.101", "h32": "192.168.132.101", "h33": "192.168.133.101",
        "h34": "192.168.134.101", "h35": "192.168.135.101", "h36": "192.168.136.101",
        "h37": "192.168.137.101", "h38": "192.168.138.101", "h39": "192.168.139.101",
        "h40": "192.168.101.101",
    }

    DEFAULT_HOP_INTERVAL = 15
    DEFAULT_CIDR = 24
    DEFAULT_LOW = 50
    DEFAULT_HIGH = 250
    DEFAULT_AVOID = "10.0.0.55"

    ONOS = "http://127.0.0.1:8181/onos/v1"
    AUTH = ("onos", "rocks")

    def __init__(self):
        self.state = {}

    def sh(self, cmd):
        return subprocess.check_output(
            cmd, shell=True, stderr=subprocess.STDOUT
        ).decode("utf-8", "ignore")

    def try_sh(self, cmd):
        try:
            return True, self.sh(cmd)
        except subprocess.CalledProcessError as e:
            out = e.output.decode("utf-8", "ignore") if getattr(e, "output", None) else ""
            return False, out

    def pidfile_for_host(self, host):
        return f"/var/run/mininet/{host}.pid"

    def find_host_pid_once(self, host):
        pidfile = self.pidfile_for_host(host)
        try:
            with open(pidfile, "r") as f:
                p = f.read().strip()
                if p.isdigit() and os.path.exists(f"/proc/{p}/ns/net"):
                    return p
        except Exception:
            pass

        ok, out = self.try_sh(
            f"ps -eo pid,cmd | grep 'mininet:{host}' | grep -v grep | awk 'NR==1{{print $1}}'"
        )
        if ok:
            p = out.strip()
            if p.isdigit() and os.path.exists(f"/proc/{p}/ns/net"):
                return p

        ok2, out2 = self.try_sh(
            f"ps -eo pid,cmd | grep mnexec | grep -v grep | grep '{host}' | awk 'NR==1{{print $1}}'"
        )
        if ok2:
            p2 = out2.strip()
            if p2.isdigit() and os.path.exists(f"/proc/{p2}/ns/net"):
                return p2

        return None

    def get_host_pid(self, host, block=True, poll=1.0):
        printed = False
        while True:
            pid = self.find_host_pid_once(host)
            if pid:
                return pid
            if not block:
                return None
            if not printed:
                print(f"[-] No {host} PID yet. In Mininet run:  {host} bash -c 'sleep infinity' &")
                printed = True
            time.sleep(poll)

    def detect_iface(self, pid):
        ok, out = self.try_sh(f"mnexec -a {pid} -- ip -o link")
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

    # def atomic_write(self, path, contents):
    #     tmp = path + ".tmp"
    #     with open(tmp, "w") as f:
    #         f.write(contents + "\n")
    #     os.replace(tmp, path)

    def parse_ips_arg(self, ips_arg):
        items = re.split(r"[;,]+", ips_arg.strip())
        cleaned = []
        for it in items:
            it = it.strip()
            if not it:
                continue
            if re.fullmatch(r"\d{1,3}", it):
                num = int(it)
                if not (1 <= num <= 254):
                    raise ValueError(f"invalid last-octet number: {it}")
                cleaned.append(f"10.0.0.{num}")
            elif re.fullmatch(r"\d+\.\d+\.\d+\.\d+", it):
                cleaned.append(it)
            else:
                raise ValueError(f"invalid IP or octet: {it}")
        return cleaned

    def rand_ip_from_list(self, low, high, avoid_set):
        while True:
            ip = "10.0.0.%d" % random.randint(low, high)
            if ip not in avoid_set:
                return ip

    def ip_present(self, pid, iface, ip):
        ok, out = self.try_sh(f"mnexec -a {pid} -- ip -4 -o addr show dev {iface}")
        if not ok:
            return False
        return any((" inet " in line and (ip + "/") in line) for line in out.splitlines())

    def set_ip_and_verify(self, pid, iface, ip, cidr):
        cmds = [
            f"ip -4 addr flush dev {iface}",
            f"ip addr add {ip}/{cidr} dev {iface}",
            f"ip link set {iface} up",
        ]
        if shutil.which("arping"):
            cmds.append(f"arping -U -c 2 -I {iface} {ip} >/dev/null 2>&1 || true")

        joined = " && ".join(cmds)
        self.try_sh(f"mnexec -a {pid} -- bash -c \"{joined}\"")

        if self.ip_present(pid, iface, ip):
            print(f"[HOP] {ip}")
            return True

        print("[-] Could not verify IP on iface after setting. Debug dump:")
        _, dump = self.try_sh(f"mnexec -a {pid} -- ip -4 addr show dev {iface}")
        if dump.strip():
            print(dump.strip())
        return False

    def infer_mac_from_host(self, host):
        try:
            num = int(host[1:])
            return "00:00:00:00:00:%02x" % num
        except Exception:
            print(f"[!] Could not infer MAC for {host}")
            return None

    def host_remove(self, host):
        mac = self.infer_mac_from_host(host)
        if not mac:
            return
        url = f"{self.ONOS}/hosts/{mac}/None"
        try:
            r = requests.delete(url, auth=self.AUTH)
            print(f"[ONOS] remove {host} ({mac}): {r.status_code}")
        except Exception as e:
            print(f"[!] Error removing {host} ({mac}): {e}")

    def reapply_nat_and_routes_if_needed(self, host, pid, iface, new_internal_ip):
        ext = self.H_EXT_IPS.get(host)
        opal_ip = self.OPAL_IPS.get(host)
        port_str = self.H_EXT_PORTS.get(host)

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
            f"ip addr add {ext} dev {iface} 2>/dev/null || true",
            "sysctl -w net.ipv4.ip_forward=1 >/dev/null",
            "iptables -t nat -F",
            "iptables -F",
            f"iptables -t nat -A PREROUTING -p tcp -d {dnat_match_ip} --dport {port} -j DNAT --to-destination {opal_ip}:{port}",
            f"iptables -t nat -A PREROUTING -p udp -d {dnat_match_ip} --dport {port} -j DNAT --to-destination {opal_ip}:{port}",
            f"iptables -A FORWARD -p tcp --dport {port} -j ACCEPT",
            f"iptables -A FORWARD -p udp --dport {port} -j ACCEPT",
            f"iptables -t nat -A POSTROUTING -d {opal_ip} -j MASQUERADE",
            "iptables -A FORWARD -p icmp -j ACCEPT",
            f"iptables -t nat -A POSTROUTING -s {ext_nw} -d 10.0.0.0/24 -j MASQUERADE",
        ]

        joined = " && ".join(cmds)
        ok, out = self.try_sh(f"mnexec -a {pid} -- bash -c \"{joined}\"")
        if ok:
            print(f"[NAT] {host}: ext={ext} internal={new_internal_ip} DNAT {dnat_match_ip}:{port} -> {opal_ip}:{port}")
        else:
            print(f"[!] NAT reapply failed for {host}:\n{out}")

    def send_last_octets(self, target_ip='192.168.10.45', port=5000):
        # new 
        ip_manager = HostIPQueueManager()
        ip_manager.load_from_csv()
        fallback_current_ips = ip_manager.get_current_ips()
        # new 

        resp = requests.get(self.ONOS + "/hosts", auth=self.AUTH, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        hosts = data.get("hosts", [])
        mac_to_ip = {h["mac"]: h.get("ipAddresses", []) for h in hosts}

        last_octets = []
        # for mac in self.mac_list:
        #     ips = mac_to_ip.get(mac, [])
        #     ip_10 = next((ip for ip in ips if ip.startswith("10.0.0.")), None)
        #     last_octets.append(ip_10.split(".")[-1] if ip_10 else "no_ip_found")
        
        #new | handle missing ips
        for mac in self.mac_list:
            host = f"h{int(mac.split(':')[-1], 16)}"

            ips = mac_to_ip.get(mac, [])
            ip_10 = next((ip for ip in ips if ip.startswith("10.0.0.")), None)

            if ip_10:
                last_octets.append(ip_10.split(".")[-1])
                continue

            fallback = fallback_current_ips.get(host)

            if fallback is None:
                last_octets.append("no_ip_found")
            else:
                fallback = str(fallback)
                last_octets.append(fallback.split(".")[-1])

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                print(f"Connecting to {target_ip}:{port}...")
                s.connect((target_ip, port))
                print("Connected.")
                json_data = json.dumps(list(last_octets))
                s.sendall(json_data.encode("utf-8"))
                print("All rows sent successfully!")
        except Exception as e:
            print(f"Error: {e}")

    def learn_onos(self, host, new_ip):
        anchor = "h1"
        if host == anchor:
            return

        p_anchor = self.get_host_pid(anchor, block=True)
        p_host = self.get_host_pid(host, block=True)

        ok, out = self.try_sh(
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

        self.try_sh(f"mnexec -a {p_anchor} -- ping -c 4 -W 1 {new_ip} >/dev/null 2>&1 || true")
        self.try_sh(f"mnexec -a {p_host} -- ping -c 4 -W 1 {anchor_ip} >/dev/null 2>&1 || true")
        print(f"[LEARN] {anchor}({anchor_ip}) <-> {host}({new_ip})")

    def parse_hosts_arg(self, host_arg: str):
        hosts = [h.strip() for h in re.split(r"[;,]+", host_arg.strip()) if h.strip()]
        for h in hosts:
            if not re.fullmatch(r"h\d+", h):
                raise ValueError(f"invalid host name: {h}")
        return hosts

    def is_dir_path(self, p: str):
        return p and (p.endswith("/") or os.path.isdir(p))

    def ipfile_for_host(self, ipfile_arg: str, host: str):
        if not ipfile_arg:
            return f"/tmp/rrm_{host}_ip.txt"

        if "{host}" in ipfile_arg:
            return ipfile_arg.format(host=host)

        if self.is_dir_path(ipfile_arg):
            d = ipfile_arg.rstrip("/")
            return f"{d}/rrm_{host}_ip.txt"

        return ipfile_arg

    def build_host_ip_map(self, hosts, ips_list):
        if not ips_list or len(ips_list) < len(hosts):
            raise ValueError(f"Need at least {len(hosts)} IPs for {len(hosts)} hosts")
        return {hosts[i]: ips_list[i] for i in range(len(hosts))}

    def ensure_host_state(self, host, no_block_pid=False):
        pid = self.get_host_pid(host, block=not no_block_pid)
        if not pid:
            print(f"[-] Could not find pid for {host}")
            return None

        iface = self.detect_iface(pid)
        prev = self.state.get(host)

        if (not prev) or (prev["pid"] != pid) or (prev["iface"] != iface):
            self.state[host] = {"pid": pid, "iface": iface}
            print(f"[i] {host} PID {pid}, iface {iface}")

        return self.state[host]

    def run_once(
        self,
        host,
        interval=15,
        cidr=24,
        ips=None,
        low=50,
        high=250,
        avoid="10.0.0.55",
        ipfile=None,
        no_block_pid=False,
        send_octets=True,
        send_target_ip="192.168.10.45",
        send_target_port=5000,
    ):
        hosts = self.parse_hosts_arg(host)
        # avoid_set = set(ip.strip() for ip in re.split(r"[;,]+", avoid) if ip.strip())
        avoid_set = set()

        ips_list = self.parse_ips_arg(ips) if ips else None
        host_ip_map = None

        if len(hosts) > 1 and ips_list:
            host_ip_map = self.build_host_ip_map(hosts, ips_list)

        for h in hosts:
            st = self.ensure_host_state(h, no_block_pid=no_block_pid)
            if not st:
                continue

            pid = st["pid"]
            iface = st["iface"]
            ipfile_path = self.ipfile_for_host(ipfile, h)

            if host_ip_map:
                ip = host_ip_map[h]
                if ip in avoid_set:
                    print(f"[-] {h}: mapped ip {ip} is in avoid list; skipping")
                    continue
            else:
                if ips_list:
                    ip = random.choice(ips_list)
                    if ip in avoid_set:
                        print(f"[-] {h}: chosen ip {ip} is in avoid list; skipping")
                        continue
                else:
                    ip = self.rand_ip_from_list(low, high, avoid_set)

            ok = self.set_ip_and_verify(pid, iface, ip, cidr)
            if not ok:
                print(f"[-] {h}: IP set/verify failed for {ip}")
                continue

            # self.atomic_write(ipfile_path, ip)
            print(f"[WROTE] {ipfile_path} <- {ip}")

            self.reapply_nat_and_routes_if_needed(h, pid, iface, ip)
            self.host_remove(h)
            self.learn_onos(h, ip)

        # self.atomic_write(self.PING_FLAG_FILE, "1")
        # print("[FLAG] wrote 1 (request relearn)")

        if send_octets:
            try:
                print('sent last octates')
                self.send_last_octets(send_target_ip, send_target_port)
            except Exception as e:
                print(f"[!] send_last_octets failed: {e}")

        return True


def ip_shuffle_endpoint(**kwargs):
    """
    Callable endpoint.
    Example:
        ip_shuffle_endpoint(
            host="h1,h2,h3",
            ips="10,20,30",
            interval=15
        )
    """
    hopper = IPHopper()
    return hopper.run_once(**kwargs)


if __name__ == "__main__":
    # CLI kept optional, but NO sudo auto-escalation here
    ap = argparse.ArgumentParser(description="Callable IP hopper")
    ap.add_argument("--host", "-H", required=True)
    ap.add_argument("--interval", "-t", type=int, default=15)
    ap.add_argument("--cidr", type=int, default=24)
    ap.add_argument("--ips", "-i", required=False)
    ap.add_argument("--low", type=int, default=50)
    ap.add_argument("--high", type=int, default=250)
    ap.add_argument("--avoid", default="10.0.0.55")
    ap.add_argument("--ipfile", default=None)
    ap.add_argument("--no-block-pid", action="store_true")
    args = ap.parse_args()

    ip_shuffle_endpoint(
        host=args.host,
        interval=args.interval,
        cidr=args.cidr,
        ips=args.ips,
        low=args.low,
        high=args.high,
        avoid=args.avoid,
        ipfile=args.ipfile,
        no_block_pid=args.no_block_pid,
    )