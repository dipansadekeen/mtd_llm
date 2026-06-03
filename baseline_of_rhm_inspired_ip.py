#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
baseline_ofrhm_random_ip.py

OF-RHM-inspired Random Host/IP Mutation baseline.

This is NOT full OF-RHM virtual-IP/real-IP translation.
It implements the random host mutation policy using your existing
ip_shuffle_endpoint.py.
"""

import argparse
import random
import time
import os
import sys

# If this file is inside a subfolder, allow importing from parent folder.
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)

if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from ip_shuffle_endpoint import ip_shuffle_endpoint
from mtd_utils import HostIPQueueManager, all_hosts


def choose_random_hosts(k, exclude_hosts=None):
    exclude_hosts = set(exclude_hosts or [])

    eligible = [
        h for h in all_hosts
        if h not in exclude_hosts
    ]

    if not eligible:
        print("[OF-RHM] No eligible hosts.")
        return []

    k = min(int(k), len(eligible))
    return random.sample(eligible, k)


def choose_free_ip_octets(ip_manager, selected_hosts):
    current_ips = ip_manager.get_current_ips()

    used_octets = set()

    for host, ip in current_ips.items():
        if ip is None:
            continue

        # Allow selected hosts to leave their old IPs.
        if host in selected_hosts:
            continue

        try:
            used_octets.add(int(str(ip).split(".")[-1]))
        except Exception:
            pass

    available = [i for i in range(1, 255) if i not in used_octets]

    if len(available) < len(selected_hosts):
        raise RuntimeError("[OF-RHM] Not enough available IP octets.")

    return random.sample(available, len(selected_hosts))


def run_ofrhm_random_ip(k=5, exclude_hosts=None, seed=None, dry_run=False):
    if seed is not None:
        random.seed(seed)

    ip_manager = HostIPQueueManager()

    # Initialize h1-h40 default IP history if needed.
    for i in range(1, 41):
        ip_manager.set_host_ips(f"h{i}", [i])

    ip_manager.load_from_csv()

    selected_hosts = choose_random_hosts(k, exclude_hosts=exclude_hosts)

    if not selected_hosts:
        return None

    new_octets = choose_free_ip_octets(ip_manager, selected_hosts)

    print("\n[OF-RHM] Random IP mutation candidate")
    print("[OF-RHM] selected_hosts:", selected_hosts)
    print("[OF-RHM] new_octets:", new_octets)

    if dry_run:
        print("[OF-RHM] Dry run only. No IP mutation applied.")
        return {
            "selected_hosts": selected_hosts,
            "new_octets": new_octets
        }

    host_arg = ",".join(selected_hosts)
    ips_arg = ",".join(map(str, new_octets))

    print("[OF-RHM] Calling ip_shuffle_endpoint:")
    print(f'  host="{host_arg}"')
    print(f'  ips="{ips_arg}"')

    result = ip_shuffle_endpoint(
        host=host_arg,
        ips=ips_arg,
        interval=15,
        no_block_pid=True
    )

    # Update ip_history.csv
    shuffled_map = dict(zip(selected_hosts, new_octets))
    current_ips = ip_manager.get_current_ips()

    for host in all_hosts:
        if host in shuffled_map:
            ip_manager.update_host_queue(host, shuffled_map[host])
        else:
            old_ip = current_ips.get(host)
            if old_ip is not None:
                try:
                    ip_manager.update_host_queue(
                        host,
                        int(str(old_ip).split(".")[-1])
                    )
                except Exception:
                    pass

    ip_manager.save_to_csv()

    print("[OF-RHM] ip_history.csv updated.")
    print("[OF-RHM] shuffled_map:", shuffled_map)

    return {
        "endpoint_result": result,
        "ip_changes": shuffled_map,
        "hosts_arg": host_arg,
        "ips_arg": ips_arg
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--exclude", default="h40")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")

    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval", type=int, default=30)

    args = parser.parse_args()

    exclude_hosts = [
        h.strip()
        for h in args.exclude.split(",")
        if h.strip()
    ]

    cycle = 0

    while True:
        cycle += 1

        print("\n" + "=" * 70)
        print(f"[OF-RHM] CYCLE {cycle}")
        print("=" * 70)

        run_ofrhm_random_ip(
            k=args.k,
            exclude_hosts=exclude_hosts,
            seed=None if args.seed is None else args.seed + cycle,
            dry_run=args.dry_run
        )

        if not args.loop:
            break

        print(f"[OF-RHM] Sleeping {args.interval}s...")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()