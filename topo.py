#!/usr/bin/env python3
# Fully working: 1 switch (s1), 6 hosts (h1..h6), ONOS control, h1 NAT→OPAL

from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController
from mininet.topo import Topo
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel
from functools import partial
import time, os, threading

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

# H_EXT_PORTS = {
#     "h1": "4749",
#     "h2": "4714",
#     "h3": "4716",
#     "h4": "4718",
#     "h5": "4720",
#     "h6": "4722",
#     "h7": "4724",
#     "h8": "4726",
#     "h9": "4728",
#     "h10": "4730",
#     "h11": "4731",
#     "h12": "4733",
#     "h13": "4735",
#     "h14": "4737",
#     "h15": "4739",
#     "h16": "4741",
#     "h17": "4743",
#     "h18": "4745",
#     "h19": "4747",
#     "h20": "4712",
# }

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
            self.addLink(d1, d2, cls=TCLink, bw=10, delay='10ms') # 10 Mbps
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
import os, time, subprocess

def read_flag():
    try:
        return open(PING_FLAG_FILE).read().strip()
    except:
        return ""

def anchor_to_all(net):
    # flag=1: anchor -> all AND all -> anchor (by IP)
    if PING_ANCHOR not in [h.name for h in net.hosts]:
        print(f"[PING] anchor {PING_ANCHOR} not found")
        return

    def _mnexec(host, cmd):
        pid = open(f"/var/run/mininet/{host}.pid").read().strip()
        subprocess.call(
            f"mnexec -a {pid} -- bash -lc {cmd!r}",
            shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

    a_ip = net.get(PING_ANCHOR).IP()
    for h in net.hosts:
        if h.name == PING_ANCHOR:
            continue
        h_ip = h.IP()
        _mnexec(PING_ANCHOR, f"ping -c 1 -W 1 {h_ip} || true")
        _mnexec(h.name,      f"ping -c 1 -W 1 {a_ip} || true")

    print(f"[PING] {PING_ANCHOR}<->all done")

def pingall(net, stop):
    """
    Listener + dispatcher:
      flag=1 -> anchor_to_all(net)
      flag=2 -> pingAll-like sweep (all->all, 1 ping each pair)
    """
    def _mnexec(host, cmd):
        pid = open(f"/var/run/mininet/{host}.pid").read().strip()
        subprocess.call(
            f"mnexec -a {pid} -- bash -lc {cmd!r}",
            shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

    last = None
    print(f"[PING] watcher started (1=anchor<->all, 2=pingAll)")
    while not stop.is_set():
        cur = read_flag()
        if cur and cur != last:
            if cur == "1":
                anchor_to_all(net)
            elif cur == "2":
                hosts = [(h.name, h.IP()) for h in net.hosts]
                for sname, _ in hosts:
                    for dname, dip in hosts:
                        if sname != dname:
                            _mnexec(sname, f"ping -c 1 -W 1 {dip} || true")
                print("[PING] pingAll sweep done")
            last = cur
        time.sleep(PING_PERIOD)

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


def ping_x(net):
    print("[PING] thread started")

    while True:
        clear_arp_cache(net)
        time.sleep(1)

        h40 = net.get('h40')
        h41 = net.get('h41')

        success = True

        # h40 -> all
        for h in net.hosts:
            if h.name == 'h40':
                continue
            result = h40.cmd('ping -c 2 %s' % h.IP())
            ok = ("2 received" in result)
            print("[PING] h40 -> %s : %s" % (h.name, "OK" if ok else "FAIL"))
            if not ok:
                success = False

        # h41 -> all
        for h in net.hosts:
            if h.name == 'h41':
                continue
            result = h41.cmd('ping -c 2 %s' % h.IP())
            ok = ("2 received" in result)
            print("[PING] h41 -> %s : %s" % (h.name, "OK" if ok else "FAIL"))
            if not ok:
                success = False

        if success:
            print("[PING] h40 & h41 success -> running net.pingAll()")
            clear_arp_cache(net)
            time.sleep(1)
            net.pingAll()
        else:
            print("[PING] validation failed -> skipping pingAll")

        time.sleep(3)

def ping_metrics_cycle(net, stop_event):
    """Cycle: ping → metrics → repeat (no ping logging)."""

    h1 = net.get('h1')

    while not stop_event.is_set():

        print("\n[Cycle] Pinging hosts...")

        # ---- PING PHASE (NO LOGGING) ----
        for i in range(2, 16):
            host = net.get('h%d' % i)

            result = h1.cmd('ping -c 2 %s' % host.IP())

            # Optional: still compute status (for debugging only)
            if "0% packet loss" in result:
                status = "ok"
            else:
                status = "loss"

            print("Ping h1 -> %s : %s" % (host.name, status))

            if stop_event.is_set():
                return

        print("\n[Cycle] Running metrics...")

        # ---- METRICS PHASE (THIS IS WHAT YOU LOG) ----
        capture_all_host_metrics(
            net,
            output_csv="h1_to_all_metrics.csv",
            ping_count=5,
            iperf_duration=5,
            udp_bandwidth="5M",
            port=5001,
            src_host_name="h1"
        )

        # Optional pause between cycles
        time.sleep(120)
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
    net  = Mininet(topo=topo, controller=None, switch=OVSSwitch13, link=TCLink, autoStaticArp=True)

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

    # with open("/tmp/shuffle_flag.txt", "w") as f:
    #     f.write("1\n")

    # stop_event = threading.Event() #new

    # cycle_thread = threading.Thread( #new
    #     target=ping_metrics_cycle, #new
    #     args=(net, stop_event) #new
    # )
    # cycle_thread.daemon = True #new
    # cycle_thread.start() #new

    # CLI(net) #new

    # stop_event.set() #new
    # cycle_thread.join() #new
    
    
    CLI(net) 

    # stop.set()
    net.stop()



if __name__ == "__main__":
    main()
