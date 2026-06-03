# main_controller_proactive.py
#
# Architecture
# ────────────
# Each 30s step:
#   1. decision_proactive.decide()
#        reads  host_stats_onos.csv, link_stats_onos.csv, observability.csv
#        scores every host (S_IP) and every h1→hx pair (S_RRM)
#        filters C_IP / C_RRM  (score > 0 + cooldown ok)
#        returns sel_ip (top K_IP=1) and sel_rrm (top K_RRM=3)
#
#   2. _do_ip_shuffle(sel_ip)
#        shuffles only the 1 selected host
#
#   3. _do_route_mutate(sel_rrm)
#        reroutes only the ≤3 selected pairs
#
#   4. Both can fire independently in the same step (ALLOW_BOTH = True)
#
#   5. Cooldown counters ticked down; log written

from ip_shuffle_endpoint   import ip_shuffle_endpoint
from route_mutate_endpoint import route_shuffle_endpoint

import time
import random
import csv
import os
from collections import deque

from proactive_decision import (
    decide,
    load_hop_lookup,
    last_nonzero,
    log_decision_items,
    PRESET_HOSTS,
    ROUTE_CANDIDATES,
    H1_PAIRS,
    K_IP,
    K_RRM,
    CD,
)

# ── Files ─────────────────────────────────────────────────────────────────────
IP_HISTORY_FILE    = "ip_history.csv"
ROUTE_HISTORY_FILE = "route_history.csv"
ROUTE_HISTORY_SIZE = 10

# ── Host / switch map ─────────────────────────────────────────────────────────
HOST_TO_SWITCH = {
    "h1":  "s1",
    "h2":  "s2", "h3":  "s2", "h4":  "s2", "h5":  "s2",
    "h6":  "s2", "h7":  "s2", "h8":  "s2",
    "h9":  "s3", "h10": "s3", "h11": "s3", "h12": "s3",
    "h13": "s3", "h14": "s3", "h15": "s3",
    "h16": "s4", "h17": "s4", "h18": "s4", "h19": "s4",
    "h20": "s4", "h21": "s4",
    "h22": "s5", "h23": "s5", "h24": "s5", "h25": "s5",
    "h26": "s5", "h27": "s5",
    "h28": "s6", "h29": "s6", "h30": "s6", "h31": "s6",
    "h32": "s6", "h33": "s6",
    "h34": "s7", "h35": "s7", "h36": "s7", "h37": "s7",
    "h38": "s7", "h39": "s7", "h40": "s7",
}

SKIP_HOSTS = {"h40"}
all_hosts  = [f"h{i}" for i in range(1, 41) if f"h{i}" not in SKIP_HOSTS]


# ── Cooldown state ────────────────────────────────────────────────────────────
# Shared with decision_proactive.decide() so eligibility reflects real history.
cooldown_state = {
    "ip":  {h: 0 for h in PRESET_HOSTS},
    "rrm": {(a, b): 0 for a, b in ROUTE_CANDIDATES},
}


def _tick_cooldowns():
    """Decrement all counters by 1 at the end of each step."""
    for h in cooldown_state["ip"]:
        cooldown_state["ip"][h] = max(0, cooldown_state["ip"][h] - 1)
    for pair in cooldown_state["rrm"]:
        cooldown_state["rrm"][pair] = max(0, cooldown_state["rrm"][pair] - 1)


def _set_ip_cooldown(hosts):
    for h in hosts:
        cooldown_state["ip"][h] = CD


def _set_rrm_cooldown(pairs):
    for p in pairs:
        cooldown_state["rrm"][p] = CD


# ── HostIPQueueManager (unchanged from original) ──────────────────────────────

class HostIPQueueManager:
    def __init__(self, host_count=40, queue_size=10):
        self.host_count  = host_count
        self.queue_size  = queue_size
        self.queues      = {}
        self.current_ips = {}
        for i in range(1, host_count + 1):
            host = f"h{i}"
            self.queues[host]      = deque(maxlen=queue_size)
            self.current_ips[host] = None

    def set_host_ips(self, host, ip_list):
        if host not in self.queues:
            raise ValueError(f"Unknown host: {host}")
        self.queues[host].clear()
        for ip in ip_list[:self.queue_size]:
            self.queues[host].append(ip)
        self.current_ips[host] = self.queues[host][-1] if self.queues[host] else None

    def set_all_hosts_ips(self, host_ip_map):
        for host, ip_list in host_ip_map.items():
            self.set_host_ips(host, ip_list)

    def get_current_ips(self):
        return dict(self.current_ips)

    def get_all_host_ips(self):
        return {host: list(q) for host, q in self.queues.items()}

    def get_host_ips(self, host):
        if host not in self.queues:
            raise ValueError(f"Unknown host: {host}")
        return list(self.queues[host])

    def update_host_queue(self, host, new_ip):
        if host not in self.queues:
            raise ValueError(f"Unknown host: {host}")
        self.queues[host].append(new_ip)
        self.current_ips[host] = new_ip

    def save_to_csv(self, filename=IP_HISTORY_FILE):
        with open(filename, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["host", "history"])
            for host in sorted(self.queues.keys(), key=lambda x: int(x[1:])):
                writer.writerow([host, ",".join(map(str, self.queues[host]))])

    def load_from_csv(self, filename=IP_HISTORY_FILE):
        if not os.path.exists(filename):
            return
        with open(filename, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                host    = row["host"].strip()
                history = row["history"].strip()
                if host not in self.queues:
                    continue
                ip_list = [x.strip() for x in history.split(",") if x.strip()] if history else []
                self.set_host_ips(host, ip_list)


# ── RouteHistoryManager (unchanged from original) ─────────────────────────────

class RouteHistoryManager:
    def __init__(self, hosts, queue_size=10):
        self.queue_size = queue_size
        self.queues     = {}
        for i in range(len(hosts)):
            for j in range(i + 1, len(hosts)):
                key = self._pair_key(hosts[i], hosts[j])
                self.queues[key] = deque(maxlen=queue_size)

    def _pair_key(self, a, b):
        return tuple(sorted((a, b)))

    def update_pair(self, a, b, option_value):
        key = self._pair_key(a, b)
        if key not in self.queues:
            self.queues[key] = deque(maxlen=self.queue_size)
        self.queues[key].append(option_value)

    def get_pair_history(self, a, b):
        return list(self.queues.get(self._pair_key(a, b), []))

    def get_all_histories(self):
        return {f"{a},{b}": list(q) for (a, b), q in self.queues.items()}

    def save_to_csv(self, filename=ROUTE_HISTORY_FILE):
        with open(filename, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["host_a", "host_b", "history"])
            for (a, b), q in sorted(
                self.queues.items(),
                key=lambda x: (int(x[0][0][1:]), int(x[0][1][1:]))
            ):
                writer.writerow([a, b, ",".join(map(str, q))])

    def load_from_csv(self, filename=ROUTE_HISTORY_FILE):
        if not os.path.exists(filename):
            return
        with open(filename, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                a, b    = row["host_a"].strip(), row["host_b"].strip()
                history = row["history"].strip()
                key     = self._pair_key(a, b)
                if key not in self.queues:
                    self.queues[key] = deque(maxlen=self.queue_size)
                self.queues[key].clear()
                for x in history.split(","):
                    x = x.strip()
                    if x:
                        self.queues[key].append(int(x))


# ── IP shuffle action ──────────────────────────────────────────────────────────

def _do_ip_shuffle(ip_manager, route_manager, sel_ip):
    """
    Shuffles only the hosts in sel_ip.
    Avoids IP collisions with all other hosts.
    Advances route history with current values (no route change this step).
    """
    current_ips = ip_manager.get_current_ips()

    # IPs held by hosts NOT being shuffled
    used_ips = set()
    for host, ip in current_ips.items():
        if ip is not None and host not in sel_ip:
            used_ips.add(int(str(ip).split(".")[-1]))

    available_ips = [x for x in range(1, 255) if x not in used_ips]
    if len(available_ips) < len(sel_ip):
        print("  ⚠ Not enough free IPs — skipping IP shuffle.")
        return

    new_ips      = random.sample(available_ips, len(sel_ip))
    shuffled_map = dict(zip(sel_ip, new_ips))

    ip_shuffle_endpoint(
        host=",".join(sel_ip),
        ips=",".join(str(shuffled_map[h]) for h in sel_ip),
        interval=30,
        no_block_pid=True,
    )

    # Update IP queues: shuffled hosts get new IP, others carry forward
    for host in all_hosts:
        if host in shuffled_map:
            ip_manager.update_host_queue(host, shuffled_map[host])
        else:
            last_ip = current_ips.get(host)
            if last_ip is not None:
                ip_manager.update_host_queue(host, last_ip)

    # Advance route history (no route change this step)
    for a, b in ROUTE_CANDIDATES:
        hist          = route_manager.get_pair_history(a, b)
        current_route = hist[-1] if hist else 0
        route_manager.update_pair(a, b, current_route)

    ip_manager.save_to_csv()
    route_manager.save_to_csv()
    print(f"  [IP SHUFFLE]  {shuffled_map}")


# ── Route mutate action ────────────────────────────────────────────────────────

def _do_route_mutate(ip_manager, route_manager, sel_rrm):
    """
    Reroutes only the pairs in sel_rrm.
    Picks a new option that differs from the current one.
    Advances IP history with current IPs (no IP change this step).
    """
    hop_lookup = load_hop_lookup()
    pairs_arg  = []
    opts_arg   = []
    result_map = {}

    for a, b in sel_rrm:
        hist = route_manager.get_pair_history(a, b)

        forward_map  = hop_lookup.get((a, b), {})
        reverse_map  = hop_lookup.get((b, a), {})
        forward_opts = set(forward_map.keys())
        reverse_opts = set(reverse_map.keys())

        if forward_opts and reverse_opts:
            all_options = sorted(forward_opts & reverse_opts)
        elif forward_opts:
            all_options = sorted(forward_opts)
        else:
            all_options = []

        if not all_options:
            print(f"  ⚠ No path options for ({a},{b}) — skipping.")
            continue

        current_opt = hist[-1] if hist else None
        available   = [opt for opt in all_options if opt != current_opt] or all_options
        new_opt     = random.choice(available)

        print(
            f"  ({a},{b})  "
            f"forward={sorted(forward_opts)}  "
            f"reverse={sorted(reverse_opts)}  "
            f"current={current_opt}  chosen={new_opt}"
        )

        pairs_arg.append(f"{a},{b}")
        opts_arg.append(str(new_opt))
        result_map[(a, b)] = new_opt

    if not pairs_arg:
        print("  ⚠ No valid route updates — skipping route mutate.")
        return

    route_shuffle_endpoint(
        specific_multiple=True,
        hosts=";".join(pairs_arg),
        opt=";".join(opts_arg),
    )

    # Update route history for mutated pairs
    for (a, b), new_opt in result_map.items():
        route_manager.update_pair(a, b, new_opt)

    # Advance IP history (no IP change this step)
    current_ips = ip_manager.get_current_ips()
    for host in all_hosts:
        last_ip = current_ips.get(host)
        if last_ip is not None:
            ip_manager.update_host_queue(host, last_ip)

    ip_manager.save_to_csv()
    route_manager.save_to_csv()
    print(f"  [ROUTE SHUFFLE]  {result_map}")


# ── Main per-step function ────────────────────────────────────────────────────

def run_shuffle(ip_manager, route_manager, i):
    """
    One full 30s step:
        1. Score → filter → select
        2. Execute IP shuffle on sel_ip   (if any)
        3. Execute route mutate on sel_rrm (if any, independent of IP)
        4. Tick cooldowns
        5. Log
    """
    print(f"\n{'─'*60}")
    print(f"  Step {i}")

    sel_ip, sel_rrm, c_ip, c_rrm, ip_scores, rrm_scores = decide(
        ip_manager, route_manager, i, cooldown_state
    )

    action_taken = "none"

    if sel_ip:
        print(f"\n  → IP shuffle candidates  : {[s['host'] for s in c_ip]}")
        print(f"    selected (top K={K_IP})  : {sel_ip}")
        _do_ip_shuffle(ip_manager, route_manager, sel_ip)
        _set_ip_cooldown(sel_ip)
        action_taken = "ip"

    if sel_rrm:
        print(f"\n  → Route candidates : {[s['pair'] for s in c_rrm]}")
        print(f"    selected (top K={K_RRM}): {sel_rrm}")
        _do_route_mutate(ip_manager, route_manager, sel_rrm)
        _set_rrm_cooldown(sel_rrm)
        action_taken = "both" if action_taken == "ip" else "route"

    if action_taken == "none":
        print("  No candidates above threshold — no action this step.")

    _tick_cooldowns()

    log_decision_items(
        ip_manager    = ip_manager,
        route_manager = route_manager,
        i             = i,
        sel_ip        = sel_ip,
        sel_rrm       = sel_rrm,
        c_ip          = c_ip,
        c_rrm         = c_rrm,
        ip_scores     = ip_scores,
        rrm_scores    = rrm_scores,
        action_taken  = action_taken,
    )

    return action_taken


# ── Entry point ───────────────────────────────────────────────────────────────

ip_manager = HostIPQueueManager()
for i in range(1, 41):
    ip_manager.set_host_ips(f"h{i}", [i])
ip_manager.load_from_csv()

route_manager = RouteHistoryManager(all_hosts, queue_size=ROUTE_HISTORY_SIZE)
route_manager.load_from_csv()

step = 0
while True:
    run_shuffle(ip_manager, route_manager, step * 6)
    print(ip_manager.get_all_host_ips())
    step += 1
    time.sleep(30)