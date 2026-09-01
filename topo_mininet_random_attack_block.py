"""
Copy the imports/constants/functions into mtd_onos_proactive_test.py before
create_network(), then use the integration block shown at the bottom of this
file in place of the final CLI(net) / net.stop() lines.

The worker runs one 60-second episode at a time, cleans up only the processes
that it started, waits 60 attack-free seconds, and repeats.  It resolves live
Linux interface addresses and restarts an active episode if one of its selected
hosts changes IP.
"""

import math
import random
import subprocess
import threading
import time


ATTACK_SECONDS = 60
COOLDOWN_SECONDS = 60       # Change to 30 only if you want a 30-second gap.
IP_CHECK_SECONDS = 2
HPING_INTERVAL = "u1000"   # Approximately 1,000 packets/second per sender.


LINK_PATTERNS = {
    "b-d": (
        (range(2, 9), range(34, 41), ".6M", 5201),
        (range(9, 16), range(28, 34), ".4M", 5202),
    ),
    "a-b": (
        (range(2, 9), range(22, 28), ".6M", 5201),
        (range(9, 16), range(16, 22), ".4M", 5202),
    ),
    "b-c": (
        (range(16, 22), range(34, 41), ".6M", 5201),
        (range(22, 28), range(28, 34), ".4M", 5202),
    ),
}


def _print(message):
    print(message, flush=True)


def _host_name(number):
    return "h{}".format(number)


def _live_ip(host):
    """Read the address currently configured on the host's Linux interface."""
    process = host.popen(
        ["ip", "-4", "-o", "addr", "show", "dev", str(host.defaultIntf())],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    try:
        output, _ = process.communicate(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        return None

    fields = output.split()
    for index, field in enumerate(fields[:-1]):
        if field == "inet":
            return fields[index + 1].split("/", 1)[0]
    return None


def _current_addresses(net, host_names):
    return {name: _live_ip(net.get(name)) for name in host_names}


def _ping_ready(source, destination_ip):
    """Use a separate process so the attack thread does not share host.cmd()."""
    process = source.popen(
        ["ping", "-n", "-c", "1", "-W", "1", destination_ip],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        return process.wait(timeout=3) == 0
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        return False


def _stop_process(process):
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _stop_processes(processes):
    for process in processes:
        _stop_process(process)


# def _host_attack_selection(rng, attack_type):
#     victim = _host_name(rng.randint(2, 40))
#     candidates = [_host_name(number) for number in range(2, 41)
#                   if _host_name(number) != victim]

#     if attack_type == "icmp":
#         # attackers = rng.sample(candidates, rng.randint(4, 6))
#         attackers = rng.sample(candidates, rng.randint(4, 10))
        
#     else:
#         attackers = [rng.choice(candidates)]
#     return attackers, victim
def _host_attack_selection(rng, attack_type):
    victim = _host_name(rng.randint(2, 40))

    candidates = [
        _host_name(number)
        for number in range(2, 41)
        if _host_name(number) != victim
    ]

    if attack_type in ("ping", "icmp"):
        # Both normal ping and ICMP flood use 4–10 sources
        attackers = rng.sample(candidates, rng.randint(4, 10))
    else:
        # SYN flood uses one source
        attackers = [rng.choice(candidates)]

    return attackers, victim


# def _launch_host_processes(net, attack_type, attackers, victim_ip):
#     processes = []
#     mode = ["-1"] if attack_type == "icmp" else ["-S", "-p", "80"]

#     for attacker_name in attackers:
#         attacker = net.get(attacker_name)
#         if not _ping_ready(attacker, victim_ip):
#             _print("[CONNECTIVITY] {} cannot reach {}; retrying soon".format(
#                 attacker_name, victim_ip
#             ))
#             _stop_processes(processes)
#             return []

#     for attacker_name in attackers:
#         command = (
#             ["hping3"] + mode
#             + ["-d", "20", "-i", HPING_INTERVAL, victim_ip]
#         )
#         process = net.get(attacker_name).popen(
#             command,
#             stdout=subprocess.DEVNULL,
#             stderr=subprocess.DEVNULL,
#         )
#         processes.append(process)
#         _print("[PROCESS] {} hping3 pid={} -> {}".format(
#             attacker_name, process.pid, victim_ip
#         ))

#     return processes
def _launch_host_processes(net, attack_type, attackers, victim_ip):
    processes = []
    commands = {
        "ping": ["ping", "-n", "-i", "1", victim_ip],
        "icmp": ["hping3", "-1", "-d", "20", "-i", HPING_INTERVAL, victim_ip],
        "syn": ["hping3", "-S", "-p", "80", "-d", "20",
                "-i", HPING_INTERVAL, victim_ip],
    }

    for name in attackers:
        if not _ping_ready(net.get(name), victim_ip):
            _print("[CONNECTIVITY] {} cannot reach {}; retrying".format(
                name, victim_ip))
            return []

    for name in attackers:
        process = net.get(name).popen(
            commands[attack_type],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        processes.append(process)
        _print("[PROCESS] {} {} pid={} -> {}".format(
            name, attack_type, process.pid, victim_ip))

    return processes


def _run_host_attack(net, stop_event, rng, episode, attack_type):
    attackers, victim = _host_attack_selection(rng, attack_type)
    # label = "ICMP HOST FLOOD" if attack_type == "icmp" else "SYN HOST FLOOD"
    labels = {
    "ping": "MULTI-HOST NORMAL PING",
    "icmp": "ICMP HOST FLOOD",
    "syn": "SYN HOST FLOOD",
    }
    label = labels[attack_type]
    selected_names = attackers + [victim]
    deadline = time.monotonic() + ATTACK_SECONDS
    processes = []
    previous_addresses = None

    _print("\n[EPISODE {:04d}] SELECTED {}".format(episode, label))
    _print("[EPISODE {:04d}] attackers={} victim={} duration={}s".format(
        episode, ",".join(attackers), victim, ATTACK_SECONDS
    ))

    try:
        while not stop_event.is_set() and time.monotonic() < deadline:
            addresses = _current_addresses(net, selected_names)

            if any(address is None for address in addresses.values()):
                _stop_processes(processes)
                processes = []
                previous_addresses = None
                _print("[EPISODE {:04d}] waiting for valid host IPs".format(episode))
                stop_event.wait(IP_CHECK_SECONDS)
                continue

            process_ended = processes and any(
                process.poll() is not None for process in processes
            )
            addresses_changed = (
                previous_addresses is not None and addresses != previous_addresses
            )

            if not processes or process_ended or addresses_changed:
                if addresses_changed:
                    _print("[EPISODE {:04d}] IP change detected; restarting {}".format(
                        episode, label
                    ))
                elif process_ended:
                    _print("[EPISODE {:04d}] traffic process exited; restarting".format(
                        episode))

                _stop_processes(processes)
                victim_ip = addresses[victim]
                processes = _launch_host_processes(
                    net, attack_type, attackers, victim_ip
                )

                if not processes:
                    previous_addresses = None
                    stop_event.wait(IP_CHECK_SECONDS)
                    continue

                if stop_event.wait(0.25):
                    break
                if any(process.poll() is not None for process in processes):
                    _print("[EPISODE {:04d}] traffic process failed to start".format(
                        episode))
                    _stop_processes(processes)
                    processes = []
                    previous_addresses = None
                    stop_event.wait(IP_CHECK_SECONDS)
                    continue

                previous_addresses = addresses
                _print("[EPISODE {:04d}] {} ACTIVE -> {} ({})".format(
                    episode, label, victim, victim_ip
                ))

            remaining = max(0.0, deadline - time.monotonic())
            stop_event.wait(min(IP_CHECK_SECONDS, remaining))
    finally:
        _stop_processes(processes)
        _print("[EPISODE {:04d}] {} STOPPED".format(episode, label))


def _link_attack_selection(rng):
    pattern = rng.choice(sorted(LINK_PATTERNS))
    flows = []
    for source_range, destination_range, rate, port in LINK_PATTERNS[pattern]:
        flows.append({
            "source": _host_name(rng.choice(list(source_range))),
            "destination": _host_name(rng.choice(list(destination_range))),
            "rate": rate,
            "port": port,
        })
    return pattern, flows


def _launch_link_processes(net, flows, addresses, duration):
    processes = []

    for flow in flows:
        source = net.get(flow["source"])
        destination_ip = addresses[flow["destination"]]
        if not _ping_ready(source, destination_ip):
            _print("[CONNECTIVITY] {} cannot reach {} ({}); retrying soon".format(
                flow["source"], flow["destination"], destination_ip
            ))
            return []

    # Start both one-shot servers before either client.
    for flow in flows:
        server = net.get(flow["destination"]).popen(
            ["iperf3", "-s", "-1", "-p", str(flow["port"])],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        processes.append(server)
        _print("[PROCESS] {} iperf3-server pid={} port={}".format(
            flow["destination"], server.pid, flow["port"]
        ))

    time.sleep(0.4)

    for flow in flows:
        destination_ip = addresses[flow["destination"]]
        client = net.get(flow["source"]).popen(
            [
                "iperf3", "-c", destination_ip, "-u",
                "-b", flow["rate"], "-t", str(max(1, duration)),
                "-p", str(flow["port"]),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        processes.append(client)
        _print("[PROCESS] {} iperf3-client pid={} -> {} ({}) rate={}".format(
            flow["source"], client.pid, flow["destination"], destination_ip,
            flow["rate"]
        ))

    return processes


# def _run_link_attack(net, stop_event, rng, episode):
#     pattern, flows = _link_attack_selection(rng)
#     selected_names = sorted({
#         name for flow in flows for name in (flow["source"], flow["destination"])
#     })
#     deadline = time.monotonic() + ATTACK_SECONDS
#     processes = []
#     previous_addresses = None

#     _print("\n[EPISODE {:04d}] SELECTED LINK FLOOD pattern={}".format(
#         episode, pattern
#     ))
#     for number, flow in enumerate(flows, 1):
#         _print("[EPISODE {:04d}] flow{} {} -> {} rate={}".format(
#             episode, number, flow["source"], flow["destination"], flow["rate"]
#         ))

#     try:
#         while not stop_event.is_set() and time.monotonic() < deadline:
#             addresses = _current_addresses(net, selected_names)

#             if any(address is None for address in addresses.values()):
#                 _stop_processes(processes)
#                 processes = []
#                 previous_addresses = None
#                 _print("[EPISODE {:04d}] waiting for valid host IPs".format(episode))
#                 stop_event.wait(IP_CHECK_SECONDS)
#                 continue

#             process_ended = processes and any(
#                 process.poll() is not None for process in processes
#             )
#             addresses_changed = (
#                 previous_addresses is not None and addresses != previous_addresses
#             )

#             if not processes or process_ended or addresses_changed:
#                 if addresses_changed:
#                     _print("[EPISODE {:04d}] IP change detected; restarting both flows".format(
#                         episode
#                     ))
#                 elif process_ended:
#                     _print("[EPISODE {:04d}] iperf3 process exited; restarting both flows".format(
#                         episode
#                     ))

#                 _stop_processes(processes)
#                 remaining = max(1, int(math.ceil(deadline - time.monotonic())))
#                 processes = _launch_link_processes(
#                     net, flows, addresses, remaining
#                 )

#                 if not processes:
#                     previous_addresses = None
#                     stop_event.wait(IP_CHECK_SECONDS)
#                     continue

#                 if stop_event.wait(0.4):
#                     break
#                 if any(process.poll() is not None for process in processes):
#                     _print("[EPISODE {:04d}] iperf3 failed to start; check installation".format(
#                         episode
#                     ))
#                     _stop_processes(processes)
#                     processes = []
#                     previous_addresses = None
#                     stop_event.wait(IP_CHECK_SECONDS)
#                     continue

#                 previous_addresses = addresses
#                 _print("[EPISODE {:04d}] LINK FLOOD ACTIVE pattern={}".format(
#                     episode, pattern
#                 ))

#             remaining = max(0.0, deadline - time.monotonic())
#             stop_event.wait(min(IP_CHECK_SECONDS, remaining))
#     finally:
#         _stop_processes(processes)
#         _print("[EPISODE {:04d}] LINK FLOOD STOPPED pattern={}".format(
#             episode, pattern
#         ))
def _run_link_attack(net, stop_event, rng, episode):
    pattern, flows = _link_attack_selection(rng)
    names = sorted({n for f in flows for n in (f["source"], f["destination"])})
    deadline = time.monotonic() + ATTACK_SECONDS
    processes, previous_addresses = [], None

    _print("\n[EPISODE {:04d}] SELECTED LINK FLOOD pattern={}".format(
        episode, pattern))
    for i, f in enumerate(flows, 1):
        _print("[EPISODE {:04d}] flow{} {} -> {} rate={}".format(
            episode, i, f["source"], f["destination"], f["rate"]))

    try:
        while not stop_event.is_set() and time.monotonic() < deadline:
            addresses = _current_addresses(net, names)

            if any(ip is None for ip in addresses.values()):
                _stop_processes(processes)
                processes, previous_addresses = [], None
                _print("[EPISODE {:04d}] waiting for valid host IPs".format(
                    episode))
                stop_event.wait(IP_CHECK_SECONDS)
                continue

            ended = processes and any(p.poll() is not None for p in processes)
            changed = previous_addresses is not None and addresses != previous_addresses

            if not processes or ended or changed:
                if changed:
                    _print("[EPISODE {:04d}] IP changed; restarting flows".format(
                        episode))
                elif ended:
                    _print("[EPISODE {:04d}] iperf3 exited; restarting flows".format(
                        episode))

                _stop_processes(processes)
                remaining = max(1, math.ceil(deadline - time.monotonic()))
                processes = _launch_link_processes(
                    net, flows, addresses, remaining)

                if not processes:
                    previous_addresses = None
                    stop_event.wait(IP_CHECK_SECONDS)
                    continue

                if stop_event.wait(0.4):
                    break

                if any(p.poll() is not None for p in processes):
                    _print("[EPISODE {:04d}] iperf3 failed to start".format(
                        episode))
                    _stop_processes(processes)
                    processes, previous_addresses = [], None
                    stop_event.wait(IP_CHECK_SECONDS)
                    continue

                previous_addresses = addresses
                _print("[EPISODE {:04d}] LINK FLOOD ACTIVE pattern={}".format(
                    episode, pattern))

            stop_event.wait(min(
                IP_CHECK_SECONDS,
                max(0.0, deadline - time.monotonic())
            ))
    finally:
        _stop_processes(processes)
        _print("[EPISODE {:04d}] LINK FLOOD STOPPED pattern={}".format(
            episode, pattern))


def random_attack_loop(net, stop_event, seed=None):
    """Run randomized Mininet traffic episodes until stopped.

    Episode probability:
      20% multi-source normal ping
      20% multi-source ICMP flood
      20% single-source SYN flood
      40% two-flow UDP link flood
    """
    rng = random.Random(seed)
    episode = 1
    choices = ("ping", "icmp", "syn", "link", "link")

    _print("[ATTACK GENERATOR] started: attack={}s cooldown={}s".format(
        ATTACK_SECONDS, COOLDOWN_SECONDS
    ))

    while not stop_event.is_set():
        attack_type = rng.choice(choices)
        try:
            if attack_type == "link":
                _run_link_attack(net, stop_event, rng, episode)
            else:
                _run_host_attack(net, stop_event, rng, episode, attack_type)
        except Exception as error:
            _print("[EPISODE {:04d}] ERROR: {}".format(episode, error))

        if stop_event.is_set():
            break

        _print("[COOLDOWN] no attack for {} seconds".format(COOLDOWN_SECONDS))
        if stop_event.wait(COOLDOWN_SECONDS):
            break
        episode += 1

    _print("[ATTACK GENERATOR] stopped cleanly")


def proactive_attack_demo(net, stop_event, seed=None):
    rng = random.Random(seed)
    MUTATION_WAIT, BETWEEN_EVENTS, HOST_SECONDS, PROBE_SECONDS, LINK_SECONDS = 8, 5, 15, 3, 15
    _print("\n" + "=" * 72); _print("PROACTIVE MTD DEMO: 3 HOST + 2 LINK EVENTS"); _print("=" * 72)

    # HOSTS: UDP ~500 pps, SYN ~1000 pps, then random UDP/SYN.
    victims = rng.sample([_host_name(i) for i in range(2, 41)], 3)
    modes = ["udp", "syn", rng.choice(["udp", "syn"])]

    for event, (victim, mode) in enumerate(zip(victims, modes), 1):
        if stop_event.is_set(): return
        candidates = [_host_name(i) for i in range(2, 41) if _host_name(i) != victim]
        probers, victim_host = rng.sample(candidates, rng.randint(5, 10)), net.get(victim)
        learned_ip = _live_ip(victim_host)
        if not learned_ip: _print("[HOST {}] {} has no live IP; skipping".format(event, victim)); continue

        # Recon: 5-10 hosts each send exactly 10 pings.
        _print("\n" + "-" * 72); _print("[HOST EVENT {}/3] RECON | mode={}".format(event, mode.upper())); _print("-" * 72)
        _print("[RECON] victim={} | learned IP={} | probers={} | ping -c 10".format(victim, learned_ip, len(probers)))
        _print("[RECON] {}".format(",".join(probers)))
        processes = [net.get(h).popen(["ping", "-n", "-c", "10", "-W", "1", learned_ip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for h in probers]
        for p in processes:
            try: p.wait(timeout=15)
            except subprocess.TimeoutExpired: _stop_process(p)

        # Attacker freezes its knowledge here.
        _print("[RECON] complete | attacker stores {}".format(learned_ip))
        _print("[MTD WINDOW] {}s for proactive mutation".format(MUTATION_WAIT))
        if stop_event.wait(MUTATION_WAIT): return

        current_ip = _live_ip(victim_host)
        stale = bool(current_ip and current_ip != learned_ip)
        _print("[KNOWLEDGE] learned={} | current={} | STALE={}".format(learned_ip, current_ip, "YES" if stale else "NO"))

        # Attack uses OLD IP only. No address refresh.
        source = rng.choice(candidates)

        if mode == "udp":
            # 2,000 us interval = ~500 packets/sec.
            _print("[ATTACK] UDP | {} -> OLD {} | ~500 pps | {}s".format(source, learned_ip, HOST_SECONDS))
            p = net.get(source).popen(["hping3", "--udp", "-p", "5001", "-d", "120", "-i", "u2000", learned_ip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            # 1,000 us interval = ~1,000 SYN packets/sec.
            _print("[ATTACK] SYN | {} -> OLD {} | ~1000 pps | {}s".format(source, learned_ip, HOST_SECONDS))
            p = net.get(source).popen(["hping3", "-S", "-p", "80", "-d", "20", "-i", "u1000", learned_ip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        stop_event.wait(HOST_SECONDS); _stop_process(p)

        final_ip = _live_ip(victim_host)
        invalidated = bool(final_ip and final_ip != learned_ip)
        _print("[HOST RESULT {}] learned={} | actual={} | invalidated={} | attacked OLD IP={}".format(event, learned_ip, final_ip, "YES" if invalidated else "NO", learned_ip))
        if stop_event.wait(BETWEEN_EVENTS): return


    # LINKS: 2 separate link demonstrations.
    for event, pattern in enumerate(rng.sample(sorted(LINK_PATTERNS), 2), 1):
        if stop_event.is_set(): return

        # Select endpoints ONCE. Recon and attack reuse exactly these endpoints.
        base = [{"source": _host_name(rng.choice(list(src))), "destination": _host_name(rng.choice(list(dst))), "port": port} for src, dst, _, port in LINK_PATTERNS[pattern]]
        names = sorted({n for f in base for n in (f["source"], f["destination"])})
        learned = _current_addresses(net, names)
        if any(ip is None for ip in learned.values()): _print("[LINK {}] invalid IP; skipping".format(event)); continue

        # Recon traffic is deliberately light: 0.05 Mbps per flow.
        probe_flows = [{"source": f["source"], "destination": f["destination"], "rate": ".05M", "port": f["port"]} for f in base]

        # Attack = two 1 Mbps flows => 2 Mbps offered load toward the shared bottleneck.
        attack_flows = [{"source": f["source"], "destination": f["destination"], "rate": "1M", "port": f["port"]} for f in base]

        _print("\n" + "-" * 72); _print("[LINK EVENT {}/2] RECON | pattern={}".format(event, pattern)); _print("-" * 72)
        for i, f in enumerate(base, 1): _print("[RECON] flow{} {} -> {} ({})".format(i, f["source"], f["destination"], learned[f["destination"]]))

        # Short non-congesting reconnaissance.
        _print("[RECON] light probe | 2 x 0.05 Mbps | {}s".format(PROBE_SECONDS))
        processes = _launch_link_processes(net, probe_flows, learned, PROBE_SECONDS)
        stop_event.wait(PROBE_SECONDS + 1); _stop_processes(processes)

        _print("[RECON] endpoints/path knowledge stored")
        _print("[MTD WINDOW] {}s for proactive route mutation".format(MUTATION_WAIT))
        if stop_event.wait(MUTATION_WAIT): return

        current = _current_addresses(net, names)
        for f in base: _print("[KNOWLEDGE] {} -> {} | learned={} | current={}".format(f["source"], f["destination"], learned[f["destination"]], current.get(f["destination"])))

        # Reuse the exact same endpoints, but now overload a 1-Mbps bottleneck.
        _print("[ATTACK] SAME endpoints | 1 Mbps + 1 Mbps = 2 Mbps offered load | {}s".format(LINK_SECONDS))
        _print("[ATTACK] expected bottleneck capacity=1 Mbps | offered load=200%")
        processes = _launch_link_processes(net, attack_flows, learned, LINK_SECONDS)
        stop_event.wait(LINK_SECONDS); _stop_processes(processes)

        _print("[LINK RESULT {}] pattern={} | same endpoints=YES | refreshed knowledge=NO".format(event, pattern))
        _print("[LINK RESULT {}] verify old target link stays uncongested after route mutation".format(event))
        if stop_event.wait(BETWEEN_EVENTS): return

    _print("\n" + "=" * 72); _print("DEMO COMPLETE: 3 HOST + 2 LINK EVENTS"); _print("=" * 72)
# ---------------------------------------------------------------------------
# INTEGRATION BLOCK
# Replace only the final CLI(net), stop_event.set(), net.stop() section inside
# create_network() with the following. Do not add a second CLI(net).
# ---------------------------------------------------------------------------
# stop = threading.Event()
# attack_thread = threading.Thread(
#     target=random_attack_loop,
#     args=(net, stop),
#     kwargs={"seed": None},       # Set an integer for repeatable selections.
#     name="random-attack-generator",
#     daemon=True,
# )
# attack_thread.start()
#
# try:
#     CLI(net)
# finally:
#     stop.set()
#     attack_thread.join()
#     net.stop()