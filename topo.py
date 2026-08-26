#!/usr/bin/env python3

from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController
from mininet.topo import Topo
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel
from functools import partial
import time, os, threading
import csv, os, re, time
import subprocess
from topo_mininet_random_attack_block import *

# new
from proactive_files.metrics_collector import capture_all_host_metrics #new
# ---------- CONFIG ----------
ONOS_IP   = "127.0.0.1"
ONOS_PORT = 6653

BRIDGE   = "br0"                 # Ubuntu/Linux bridge towards OPAL/Windows
EDGE_SW  = "s1"                  # switch where uplink lands
VETH_L   = "veth-br0"
VETH_R   = "veth-s1"

import threading
PING_FLAG_FILE = "/tmp/mutual_ping_flag.txt"   # write 1 or 0 here
PING_ANCHOR = "h40"                            # change this later if needed
PING_PERIOD = 3                                # seconds

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

    "h40": "4711"

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


# OPAL side
OPAL_IP    = "192.168.10.101"     # OPAL-RT target
OPAL_PORT="23"
H1_EXT_IP  = "192.168.10.200/24"  # h1 secondary address on same NIC

def sh(cmd: str):
    """quiet shell exec"""
    os.system(cmd + " >/dev/null 2>&1")

# -----------------------------------------------

def clear_arp_cache(net):
    """Clear ARP cache on all hosts."""
    for host in net.hosts:
        try:
            # Ensure the host is ready
            if host.shell and not host.waiting:
                host.cmd('ip -s -s neigh flush all')
                print("ARP cache cleared on {}.".format(host.name))
            else:
                print("Host {} is not ready to execute commands.".format(host.name))
        except Exception as e:
            print("Error clearing ARP cache on {}: {}".format(host.name, str(e)))
    print("ARP cache cleared on all hosts.")



def ping_all_from_h1(net, log_file):
    """Ping all other hosts from h1 and log the results."""
    h1 = net.get('h1')
    with open(log_file, 'a') as f:
        for i in range(2, 40):  # h2 to h39  #topo_change
            host = net.get('h%d' % i)
            try:
                result = h1.cmd('ping -c 2 %s' % host.IP())  # Ping 2 times for better accuracy
                if "2 received" in result:
                    status = "success"
                elif "0 received" in result:
                    status = "failed"
                else:
                    status = "partial"
                
                # Extract average latency
                latency = "N/A"
                if "min/avg/max" in result:
                    latency = result.split("min/avg/max/mdev = ")[1].split("/")[1]  # Extract avg latency
                
                # Log the result using % formatting
                log_entry = "Ping from h1 to %s (%s): %s, Avg Latency: %s ms\n" % (
                    host.name, host.IP(), status, latency
                )
                f.write(log_entry)
                print(log_entry.strip())

            except Exception as e:
                error_msg = "Error pinging {} ({}): {}\n".format(host.name, host.IP(), str(e))
                f.write(error_msg)
                print(error_msg.strip())

# ==========================================================
# NEW Topology Parser + CustomTopo (do not change anything else)
# ==========================================================
def parse_topology_file(file_path):
    hosts = {}
    switches = set()
    links = []
    section = None

    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                if 'Hosts' in line: section = 'host'
                elif 'Switches' in line: section = 'switch'
                elif 'Links' in line: section = 'link'
                continue

            try:
                if section == 'host':
                    name, ip, mac = [x.strip() for x in line.split(',')]
                    hosts[name] = (ip, mac)
                elif section == 'switch':
                    switches.add(line)
                elif section == 'link':
                    dev1, dev2 = [x.strip() for x in line.split(',')]
                    links.append((dev1, dev2))
            except:
                continue

    return hosts, switches, links


class CustomTopo(Topo):
    def build(self):
        hosts, switches, links = parse_topology_file('topology_s10.txt')

        for sw in switches:
            self.addSwitch(sw)

        for hname, (ip, mac) in hosts.items():
            self.addHost(hname, ip=ip, mac=mac)

        for d1, d2 in links:
            # self.addLink(d1, d2)
            self.addLink(d1, d2, cls=TCLink, bw=1, delay='10ms') # 1 Mbps
            # self.addLink(d1, d2, cls=TCLink, bw=10, delay='10ms', loss=2)



def add_external_uplink():
    """Create veth to Linux bridge and plug the right side to s1."""
    print(f"[uplink] wiring {EDGE_SW} ↔ {BRIDGE}")
    sh(f"ip link del {VETH_L}")
    sh(f"ip link del {VETH_R}")
    sh(f"ip link add {VETH_L} type veth peer name {VETH_R}")
    sh(f"ip link set {VETH_L} up")
    sh(f"ip link set {VETH_R} up")
    sh(f"ip link set {VETH_L} master {BRIDGE}")
    # add the other end into OVS s1
    sh(f"ovs-vsctl --may-exist add-port {EDGE_SW} {VETH_R}")

def setup_hx_nat_to_opal(h1,HOST_EXT_IP,HOST_IP1,OPAL_IP1,OPAL_PORT1):
    """Only h1 does NAT to OPAL; all other traffic is handled by ONOS."""
    parts = HOST_EXT_IP.split(".")     # ["192", "168", "30", "200"]
    HOST_EXT_NW = ".".join(parts[:3] + ["0/24"])
    print(f"host external network:{HOST_EXT_NW}")
    intf = h1.defaultIntf()
    # dual-stack h1: internal 10.0.0.101/24 is already set; add external /24
    h1.cmd(f"ip addr add {HOST_EXT_IP} dev {intf}")
    h1.cmd("sysctl -w net.ipv4.ip_forward=1")

    # clean and program NAT
    h1.cmd("iptables -t nat -F")
    h1.cmd("iptables -F")

    # DNAT: traffic sent to 10.0.0.101:2300 → OPAL:2300
    h1.cmd(f"iptables -t nat -A PREROUTING -p tcp -d {HOST_IP1} --dport {OPAL_PORT1} "f"-j DNAT --to-destination {OPAL_IP1}:{OPAL_PORT1}")

    # Allow forwarding of that TCP flow
    h1.cmd(f"iptables -A FORWARD -p tcp --dport {OPAL_PORT1} -j ACCEPT")

    # SNAT so replies from OPAL go back via h1 to the original initiator
    h1.cmd(f"iptables -t nat -A POSTROUTING -d {OPAL_IP1} -j MASQUERADE")

    # (optional) ICMP forward if you want ping traversals involving OPAL
    h1.cmd("iptables -A FORWARD -p icmp -j ACCEPT")
    h1.cmd(f"iptables -t nat -A POSTROUTING -s {HOST_EXT_NW} -d 10.0.0.0/24 -j MASQUERADE")

    print(f"[h1-nat] DNAT {HOST_IP1}:{OPAL_PORT1} → OPAL:{OPAL_PORT1} and MASQUERADE configured")
# /////////////////////////////////////////////////////////////////


def clear_arp_cache(net):
    """Clear ARP cache on all hosts."""
    for host in net.hosts:
        try:
            # Ensure the host is ready
            if host.shell and not host.waiting:
                host.cmd('ip -s -s neigh flush all')
                print("ARP cache cleared on {}.".format(host.name))
            else:
                print("Host {} is not ready to execute commands.".format(host.name))
        except Exception as e:
            print("Error clearing ARP cache on {}: {}".format(host.name, str(e)))
    print("ARP cache cleared on all hosts.")





# def run_iperf_traffic(net):
#     """
#     Continuously transmit UDP traffic from h1 to h2...h10.

#     Each flow:
#         0.3 Mbps
#         Approximately 20 packets/second
#         1875-byte UDP payload
#     """
#     h1 = net.get("h1")
#     port = 5001
#     packet_size = 1875

#     # Remove previously running iperf processes.
#     for host in net.hosts:
#         host.cmd("pkill -f iperf >/dev/null 2>&1 || true")

#     # Start destination servers.
#     for i in range(2, 11):
#         dst = net.get(f"h{i}")
#         dst.cmd(
#             f"iperf -s -u -p {port} -i 1 "
#             f"> iperf_h{i}_server.log 2>&1 &"
#         )

#     time.sleep(2)

#     # Start continuous traffic from h1.
#     for i in range(2, 11):
#         dst = net.get(f"h{i}")

#         h1.cmd(
#             f"iperf -c {dst.IP()} -u "
#             f"-p {port} "
#             f"-b 300K "
#             f"-l {packet_size} "
#             f"-t 0 "
#             f"-i 1 "
#             f"> iperf_h1_to_h{i}.log 2>&1 &"
#         )

#         print(f"[IPERF] h1 -> h{i}: continuous 0.3 Mbps, ~20 pps")


def run_dynamic_tcp_iperf(net, stop):
    """
    Maintain dynamic TCP traffic from h1 to h2...h40.

    Each flow:
        approximately 20 writes per second
        approximately 0.03 Mbps application payload
    """

    def current_ip(host):
        """Return the host's current 10.x.x.x address."""
        intf = host.defaultIntf().name

        process = host.popen(
            ["ip", "-4", "-o", "addr", "show", "dev", intf],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )

        output = process.communicate()[0].decode(errors="ignore")
        match = re.search(
            r"\binet\s+(10(?:\.\d+){3})/",
            output
        )

        return match.group(1) if match else None

    def start_process(host, command, log_name):
        """Start a process and redirect its output to a log."""
        log_file = open(log_name, "a")

        process = host.popen(
            command,
            stdout=log_file,
            stderr=subprocess.STDOUT
        )

        log_file.close()
        return process

    def stop_process(process):
        """Terminate a process cleanly."""
        if process is None:
            return

        if process.poll() is not None:
            return

        process.terminate()

        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    h1 = net.get("h1")
    targets = [
        net.get("h%d" % i)
        for i in range(2, 41)
    ]

    port = 5001
    packet_size = 188

    servers = {}
    clients = {}
    previous_ips = {}

    try:
        # Start one TCP server on every destination.
        for target in targets:
            servers[target.name] = start_process(
                target,
                [
                    "iperf3",
                    "-s",
                    "-p", str(port),
                    "-i", "1",
                    "-e"
                ],
                "iperf_%s_tcp_server.log"
                % target.name
            )

        time.sleep(2)

        while not stop.is_set():
            for target in targets:
                target_name = target.name
                new_ip = current_ip(target)
                old_ip = previous_ips.get(target_name)
                client = clients.get(target_name)

                if not new_ip:
                    continue

                ip_changed = (
                    old_ip is not None
                    and new_ip != old_ip
                )

                client_stopped = (
                    client is None
                    or client.poll() is not None
                )

                if not ip_changed and not client_stopped:
                    continue

                if ip_changed:
                    print(
                        "[TCP RECONNECT] %s: %s -> %s"
                        % (target_name, old_ip, new_ip)
                    )

                # Stop the old TCP connection.
                stop_process(client)

                # Remove a stale ARP entry for the new IP.
                arp_process = h1.popen(
                    [
                        "ip",
                        "neigh",
                        "flush",
                        "to",
                        new_ip
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                arp_process.wait()

                # Start a new TCP connection to the current IP.
                clients[target_name] = start_process(
                    h1,
                    [
                        "iperf",
                        "-c", new_ip,
                        "-p", str(port),
                        "-b", "20pps",
                        "-l", str(packet_size),
                        "-N",
                        "-t", "604800",
                        "-i", "1",
                        "-e"
                    ],
                    "iperf_h1_to_%s_tcp.log"
                    % target_name
                )

                previous_ips[target_name] = new_ip

                print(
                    "[TCP IPERF] h1 -> %s (%s): started"
                    % (target_name, new_ip)
                )

            stop.wait(1)

    finally:
        # Stop all TCP clients.
        for process in clients.values():
            stop_process(process)

        # Stop all TCP servers.
        for process in servers.values():
            stop_process(process)
# def ping_h1_to_all(net, stop):
#     h1 = net.get("h1")

#     while not stop.is_set():
#         h1.cmd("ip neigh flush all")

#         for h in net.hosts:
#             if h.name == "h1":
#                 continue

#             intf = h.defaultIntf().name
#             ip = h.cmd(
#                 "ip -4 -o addr show dev %s | "
#                 "awk '$4~/^10\\./{split($4,a,\"/\"); print a[1]; exit}'"
#                 % intf
#             ).strip()

#             if not ip:
#                 continue

#             result = h1.cmd("ping -n -c 1 -W 1 %s" % ip)
#             rtt = re.search(r"=\s*[\d.]+/([\d.]+)/", result)

#             print(
#                 "h1 -> %s (%s): %s"
#                 % (
#                     h.name,
#                     ip,
#                     "RTT " + rtt.group(1) + " ms" if rtt else "FAIL"
#                 )
#             )

#         stop.wait(1)

def ping_h1_to_all(net, stop): # last working
    h1 = net.get("h1")
    log = "ping_results.csv"

    if not os.path.exists(log):
        with open(log, "w", newline="") as f:
            csv.writer(f).writerow(
                ["time", "target", "ip", "status", "rtt_ms"]
            )

    while not stop.is_set():
        h1.cmd("ip neigh flush all")

        for h in net.hosts:
            if h.name == "h1":
                continue

            intf = h.defaultIntf().name
            ip = h.cmd(
                "ip -4 -o addr show dev %s | "
                "awk '$4~/^10\\./{split($4,a,\"/\"); print a[1]; exit}'"
                % intf
            ).strip()

            if not ip:
                continue

            result = h1.cmd("ping -n -c 3 -W 1 %s" % ip)
            rtt = re.search(r"=\s*[\d.]+/([\d.]+)/", result)

            status = "success" if rtt else "failed"
            rtt_value = rtt.group(1) if rtt else "N/A"

            print(
                "h1 -> %s (%s): %s"
                % (
                    h.name,
                    ip,
                    "RTT " + rtt_value + " ms" if rtt else "FAIL"
                )
            )

            with open(log, "a", newline="") as f: # replace "a" with "w" for last one
                csv.writer(f).writerow([
                    time.strftime("%Y-%m-%d %H:%M:%S"),
                    h.name,
                    ip,
                    status,
                    rtt_value
                ])

        stop.wait(1)


import re
import time
import subprocess


class DynamicIperfManager:

    def __init__(self, net):
        self.net = net
        self.h1 = net.get("h1")
        self.targets = [
            net.get("h%d" % i)
            for i in range(2, 41)
        ]

        self.servers = {}
        self.clients = {}
        self.previous_ips = {}
        self.port = 5001

    def _current_ip(self, host):
        """Fetch the host's live 10.x.x.x address."""
        process = host.popen(
            [
                "ip", "-4", "-o", "addr", "show",
                "dev", host.defaultIntf().name
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )

        output = process.communicate()[0].decode(
            errors="ignore"
        )

        match = re.search(
            r"\binet\s+(10(?:\.\d+){3})/",
            output
        )

        return match.group(1) if match else None

    def _stop_process(self, process):
        if process is None or process.poll() is not None:
            return

        process.terminate()

        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    def start(self):
        """Start one iperf3 server on each destination."""
        for target in self.targets:
            self.servers[target.name] = target.popen(
                [
                    "iperf3",
                    "-s",
                    "-p", str(self.port)
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

        time.sleep(2)
        self.synchronize()

    def synchronize(self):
        """Restart a client only if its IP changed or it stopped."""
        for target in self.targets:
            name = target.name
            new_ip = self._current_ip(target)
            old_ip = self.previous_ips.get(name)
            client = self.clients.get(name)

            if not new_ip:
                continue

            client_running = (
                client is not None
                and client.poll() is None
            )

            # Nothing changed
            if new_ip == old_ip and client_running:
                continue

            if old_ip and new_ip != old_ip:
                print(
                    "[IPERF IP CHANGE] %s: %s -> %s"
                    % (name, old_ip, new_ip)
                )

            self._stop_process(client)

            # Remove stale ARP information
            arp = self.h1.popen(
                ["ip", "neigh", "flush", "to", new_ip],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            arp.wait()

            # Start UDP traffic:
            # 188 bytes × 8 × 20 pps = 30,080 bps
            self.clients[name] = self.h1.popen(
                [
                    "iperf3",
                    "-c", new_ip,
                    "-u",
                    "-p", str(self.port),
                    "-b", "30080",
                    "-l", "188",
                    "-t", "604800"
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            self.previous_ips[name] = new_ip

            print(
                "[UDP IPERF] h1 -> %s (%s): active"
                % (name, new_ip)
            )

    def watch(self, stop_event):
        """Check for externally changed IPs every second."""
        while not stop_event.is_set():
            self.synchronize()
            stop_event.wait(1)

    def stop(self):
        """Stop every client and server."""
        for process in self.clients.values():
            self._stop_process(process)

        for process in self.servers.values():
            self._stop_process(process)
# //////////////////////////////////////////////////////////////////# //////////////////////////////////////////////////////////////////

# def main():
#     setLogLevel('info')

#     # Build topology
#     OVSSwitch13 = partial(OVSSwitch, protocols='OpenFlow13')
#     topo = CustomTopo()
#     net  = Mininet(topo=topo, controller=None, switch=OVSSwitch13, link=TCLink, autoStaticArp=True)

#     # Add ONOS controller
#     c0 = net.addController('c0', controller=RemoteController, ip=ONOS_IP, port=ONOS_PORT)

#     print("[+] Starting Mininet…")
#     net.start()

#     # Give deterministic /24s to hosts
#     for h in net.hosts:
#         # ip = H_INT_IPS[h.name]
#         # h.cmd(f"ip addr flush dev {h.defaultIntf()}")
#         # h.setIP(ip.split('/')[0], prefixLen=24)
#         # only h1 routes; others are endpoints
#         # if h.name == "h1":
#         #     h.cmd("sysctl -w net.ipv4.ip_forward=1")
#         # else:
#         #     h.cmd("sysctl -w net.ipv4.ip_forward=1")
#         h.cmd("sysctl -w net.ipv4.ip_forward=1")

#     # Make sure OVS is fully under ONOS (no local learning)
#     for sw in net.switches:
#         sw.cmd(f"ovs-vsctl set-fail-mode {sw.name} secure")
#         sw.cmd(f"ovs-vsctl set bridge {sw.name} protocols=OpenFlow13")
#         # ensure we DON'T have a local NORMAL rule lingering
#         sw.cmd(f"ovs-ofctl -O OpenFlow13 del-flows {sw.name}")

#     # Let switches connect to ONOS
#     c0.start()
#     for sw in net.switches:
#         sw.start([c0])
#         print(f"{sw.name} connected to ONOS")

#     time.sleep(2)
#     # Add uplink AFTER OVS exists
#     add_external_uplink()

#     # ===================== CHANGE #2 (ADD THREAD HERE) ========================
#     stop = threading.Event()
#     threading.Thread(target=ping_anchor_all, args=(net, stop), daemon=True).start()
#     print("[PING] watcher thread started")
#     # ==========================================================================

#     # Program h1 NAT → OPAL
#     # h1 = net.get('h1')
#     # setup_hx_nat_to_opal(h1,H1_EXT_IP,"10.0.0.101",OPAL_IP,OPAL_PORT)
#     # # Program h1 NAT → OPAL
#     # h3 = net.get('h3')
#     # setup_hx_nat_to_opal(h3,"192.168.30.200/24","10.0.0.103","192.168.30.101",OPAL_PORT)

#     # for h in net.hosts:
#     #     setup_hx_nat_to_opal(h,H_EXT_IPS[h.name],H_INT_IPS[h.name].split('/')[0],OPAL_IPS[h.name],H_EXT_PORTS[h.name])
#     #     # ip = H_INT_IPS[h.name]


#     for h in net.hosts:
#         if h.name in H_EXT_IPS:
#             int_ip = h.IP()  # <-- read existing Mininet IP
#             setup_hx_nat_to_opal(
#                 h,
#                 H_EXT_IPS[h.name],
#                 int_ip,
#                 OPAL_IPS[h.name],
#                 H_EXT_PORTS[h.name]
#             )



#     print("\n=== Ready ===")
#     print("- ONOS should show device of:0000000000000001 with ports (incl. veth-s1).")
#     print("- Only h1 performs DNAT/SNAT for OPAL on TCP/2300.")
#     print("- All other internal routing/forwarding is ONOS-controlled.\n")

#     CLI(net)

#     # ===================== CHANGE #3 (STOP THREAD CLEANLY) ====================
#     stop.set()
#     # ==========================================================================
#     net.stop()



def main():
    setLogLevel('info')

    OVSSwitch13 = partial(OVSSwitch, protocols='OpenFlow13')
    topo = CustomTopo()
    # net  = Mininet(topo=topo, controller=None, switch=OVSSwitch13, link=TCLink, autoStaticArp=True)
    net  = Mininet(topo=topo, controller=None, switch=OVSSwitch13, link=TCLink, autoStaticArp=False)

    c0 = net.addController('c0', controller=RemoteController, ip=ONOS_IP, port=ONOS_PORT)

    print("[+] Starting Mininet…")
    net.start()

    # host sysctls
    for h in net.hosts:
        h.cmd("sysctl -w net.ipv4.ip_forward=1")

    # switch config
    for sw in net.switches:
        sw.cmd(f"ovs-vsctl set-fail-mode {sw.name} secure")
        sw.cmd(f"ovs-vsctl set bridge {sw.name} protocols=OpenFlow13")
        sw.cmd(f"ovs-ofctl -O OpenFlow13 del-flows {sw.name}")

    # connect switches to ONOS
    c0.start()
    for sw in net.switches:
        sw.start([c0])
        print(f"{sw.name} connected to ONOS")

    time.sleep(3)

    # uplink after OVS exists
    add_external_uplink()

    # NAT setup
    for h in net.hosts:
        if h.name in H_EXT_IPS:
            setup_hx_nat_to_opal(h, H_EXT_IPS[h.name], h.IP(), OPAL_IPS[h.name], H_EXT_PORTS[h.name])


    # # //////// ||threading to collect data. --last try #start --best
    # stop = threading.Event()

    # thread = threading.Thread(
    #     target=ping_h1_to_all,
    #     args=(net, stop),
    #     daemon=True
    # )
    # thread.start()

    # try:
    #     CLI(net)
    # finally:
    #     stop.set()
    #     thread.join()

    #     net.stop()
    # # //////// ||threading to collect data. #end



    # .///////////////////// --iperf somehow works
    # net.pingAll()

    # stop = threading.Event()

    # # Start iperf
    # iperf_manager = DynamicIperfManager(net)
    # iperf_manager.start()

    # # Ping thread
    # ping_thread = threading.Thread(
    #     target=ping_h1_to_all,
    #     args=(net, stop),
    #     daemon=True
    # )

    # # Iperf IP-watcher thread
    # iperf_thread = threading.Thread(
    #     target=iperf_manager.watch,
    #     args=(stop,),
    #     daemon=True
    # )

    # ping_thread.start()
    # iperf_thread.start()

    # try:
    #     CLI(net)

    # finally:
    #     # Tell both threads to stop
    #     stop.set()

    #     # Wait for both threads
    #     ping_thread.join()
    #     iperf_thread.join()

    #     # Stop iperf processes
    #     iperf_manager.stop()

    #     # Stop Mininet once
    #     net.stop()
    # ./////////////////////

    # ///////////////////////////////////// ---new attack sample tryout
    net.pingAll()
    stop = threading.Event()

    attack_thread = threading.Thread(
        target=random_attack_loop,
        args=(net, stop),
        kwargs={"seed": None},
        name="random-attack-generator",
        daemon=True
    )
    attack_thread.start()

    try:
        CLI(net)
    finally:
        stop.set()
        attack_thread.join()
        net.stop()
    # ///////////////////////////////////// ---new attack sample tryout




    # just normal mininet run below:
    # net.pingAll()
    # # run_iperf_traffic(net) #new to simulate opal-rt run.
    # CLI(net) #old

    # # stop.set()
    # net.stop()



if __name__ == "__main__":
    main()
