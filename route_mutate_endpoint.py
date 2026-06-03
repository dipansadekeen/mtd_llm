#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import re
import csv
import random
import requests
import subprocess


class RouteMutator:
    ONOS = "http://127.0.0.1:8181/onos/v1"
    AUTH = ("onos", "rocks")

    LOG_FILE = "/tmp/path_match_log.txt"
    CSV_FILE = "hop_list.csv"
    CYCLE_INTERVAL = 20
    PAIR_COUNT_PER_CYCLE = 10

    def __init__(self, csv_file=None, log_file=None):
        self.csv_file = csv_file or self.CSV_FILE
        self.log_file = log_file or self.LOG_FILE
        self.path_db = self.load_path_database_from_csv(self.csv_file)

    # ==============================================================
    # PATH DATABASE UTILITIES
    # ==============================================================

    def load_path_database_from_csv(self, csv_file):
        path_db = {}
        try:
            with open(csv_file, "r", newline="") as f:
                reader = csv.reader(f)
                for row in reader:
                    if not row:
                        continue

                    if len(row) >= 7:
                        parts = [c.strip().strip('"') for c in row]
                    else:
                        line = row[0].strip().strip('"')
                        parts = [p.strip().strip('"') for p in line.split(",")]

                    if len(parts) < 7:
                        continue

                    src, dst = parts[0], parts[1]
                    try:
                        opt = int(parts[2])
                    except ValueError:
                        opt = 1

                    normalized = ", ".join(parts[:6] + parts[6:])
                    path_db[(src, dst, opt)] = normalized

            print(f"[✓] Loaded {len(path_db)} paths from {csv_file}")
        except FileNotFoundError:
            print(f"[✗] CSV file '{csv_file}' not found.")
        return path_db

    def generate_path_rules(self, path_data):
        parts = [p.strip() for p in path_data.strip().strip('"').split(",")]
        src_host, dst_host, path_option = parts[:3]
        hop_count = int(float(parts[3]))
        src_mac, dst_mac = parts[4], parts[5]
        raw_links = parts[6:]

        links = []
        for l in raw_links:
            l = l.strip().replace(" ", "")
            if "->" in l:
                a, b = l.split("->")
                links.append(f"{a.strip()} -> {b.strip()}")
            else:
                links.append(l.strip())

        rules = []

        for i in range(len(links)):
            sub = ", ".join(links[i:])
            hops = len(links) - i
            rules.append(f"{src_mac}, {dst_mac}, {sub}, {float(hops)}")

        rev_links = []
        for l in links:
            if "->" not in l:
                continue
            a, b = [x.strip() for x in l.split("->")]
            rev_links.append(f"{b} -> {a}")
        rev_links.reverse()

        for i in range(len(rev_links)):
            sub = ", ".join(rev_links[i:])
            hops = len(rev_links) - i
            rules.append(f"{dst_mac}, {src_mac}, {sub}, {float(hops)}")

        return rules

    def get_rules(self, src, dst, option):
        key = (src, dst, option)
        if key not in self.path_db:
            return []
        return self.generate_path_rules(self.path_db[key])

    def get_available_options(self, src, dst):
        return sorted([opt for (s, d, opt) in self.path_db.keys() if s == src and d == dst])

    def get_all_host_pairs(self):
        return sorted(list({(s, d) for (s, d, _) in self.path_db.keys()}))

    # ==============================================================
    # ONOS CONTROL HELPERS
    # ==============================================================

    def clear_fwd_flows(self):
        url = f"{self.ONOS}/flows/application/org.onosproject.fwd"
        r = requests.delete(url, auth=self.AUTH)
        print(f"[ONOS] Cleared fwd flows: HTTP {r.status_code}")

    def clear_all_flows(self):
        devices_url = f"{self.ONOS}/devices"
        r = requests.get(devices_url, auth=self.AUTH)
        if r.status_code != 200:
            print(f"[ERROR] Could not get device list: {r.status_code}")
            return
        devices = [d["id"] for d in r.json().get("devices", [])]
        for dev in devices:
            url = f"{self.ONOS}/flows/{dev}"
            r2 = requests.delete(url, auth=self.AUTH)
            print(f"  Cleared flows on {dev}: HTTP {r2.status_code}")

    def trigger_relearning(self):
        print("[*] Triggering ONOS re-learning (ARP+ping)")
        try:
            subprocess.run(
                "mnexec -a $(cat /var/run/mininet/h1.pid) arping -c1 -A -I h1-eth0 10.0.0.1",
                shell=True,
            )
            subprocess.run(
                "mnexec -a $(cat /var/run/mininet/h1.pid) ping -c1 10.0.0.2",
                shell=True,
            )
        except Exception as e:
            print(f"[!] Could not send ping/arp: {e}")

    # ==============================================================
    # PAIR BUILDERS
    # ==============================================================

    def parse_host_token(self, tok):
        tok = tok.strip()
        m = re.match(r"^([a-zA-Z]+)?(\d+)$", tok)
        if not m:
            raise ValueError(f"Invalid host token: {tok}")
        prefix = m.group(1) if m.group(1) else "h"
        idx = int(m.group(2))
        return prefix, idx

    def build_pairs_from_range(self, range_str):
        parts = [p.strip() for p in range_str.split(",") if p.strip()]
        if len(parts) != 2:
            raise ValueError(f"--range expects 'hA,hB'. Got: {range_str}")

        p1, a = self.parse_host_token(parts[0])
        p2, b = self.parse_host_token(parts[1])
        if p1 != p2:
            raise ValueError(f"Range hosts must share same prefix. Got: {parts[0]} and {parts[1]}")

        lo, hi = (a, b) if a <= b else (b, a)
        hosts = [f"{p1}{i}" for i in range(lo, hi + 1)]

        pairs = []
        for s in hosts:
            for d in hosts:
                if s != d:
                    pairs.append((s, d))
        return pairs

    def build_pairs_from_specific(self, spec_str):
        spec_str = spec_str.strip().strip('"').strip("'")
        if not spec_str:
            return []

        pairs = []
        chunks = [c.strip() for c in spec_str.split(";") if c.strip()]
        for ch in chunks:
            ab = [x.strip() for x in ch.split(",") if x.strip()]
            if len(ab) != 2:
                raise ValueError(f"Invalid pair '{ch}'. Use format: h1,h2;h3,h6")
            pairs.append((ab[0], ab[1]))
        return pairs

    def filter_pairs_to_db(self, pairs):
        kept = []
        for (s, d) in pairs:
            if self.get_available_options(s, d):
                kept.append((s, d))
        return kept

    def dedupe_undirected_pairs(self, pairs):
        seen = set()
        out = []
        for a, b in pairs:
            key = tuple(sorted((a, b)))
            if a == b:
                continue
            if key in seen:
                continue
            seen.add(key)
            out.append((a, b))
        return out

    def build_specific_multiple_map(self, hosts_str, opt_str):
        if not hosts_str or not opt_str:
            raise ValueError("--specific_multiple requires both --hosts and --opt")

        hosts_str = hosts_str.strip().strip('"').strip("'")
        opt_str = opt_str.strip().strip('"').strip("'")

        pair_chunks = [x.strip() for x in hosts_str.split(";") if x.strip()]
        opt_chunks = [x.strip() for x in opt_str.split(";") if x.strip()]

        if len(pair_chunks) != len(opt_chunks):
            raise ValueError(
                f"Host-pair count ({len(pair_chunks)}) must match option count ({len(opt_chunks)})"
            )

        result = []
        for pair_str, opt_val in zip(pair_chunks, opt_chunks):
            ab = [x.strip() for x in pair_str.split(",") if x.strip()]
            if len(ab) != 2:
                raise ValueError(f"Invalid host pair: {pair_str}")

            src, dst = ab[0], ab[1]

            try:
                opt = int(opt_val)
            except ValueError:
                raise ValueError(f"Invalid option number: {opt_val}")

            if (src, dst, opt) not in self.path_db:
                raise ValueError(f"No hop_list.csv entry for ({src}, {dst}, {opt})")

            result.append((src, dst, opt))

        return result

    # ==============================================================
    # ONE-SHOT ROUTE SHUFFLE
    # ==============================================================

    def run_once(
        self,
        random_k=None,
        specific=None,
        specific_multiple=False,
        range_str=None,
        interval=None,
        hosts=None,
        opt=None,
        trigger_learning=False,
    ):
        if not self.path_db:
            return False

        db_pairs = self.get_all_host_pairs()
        print(f"[✓] Found {len(db_pairs)} host pairs in DB.")

        fixed_pair_options = []
        all_pairs = []

        if range_str:
            candidate_pairs = self.build_pairs_from_range(range_str)
            candidate_pairs = self.filter_pairs_to_db(candidate_pairs)
            all_pairs = self.dedupe_undirected_pairs(sorted(candidate_pairs))
            print(f"[✓] Range mode {range_str} → {len(all_pairs)} unique (undirected) pairs in DB.")

        elif specific:
            candidate_pairs = self.build_pairs_from_specific(specific)
            candidate_pairs = self.filter_pairs_to_db(candidate_pairs)
            all_pairs = self.dedupe_undirected_pairs(sorted(candidate_pairs))
            print(f"[✓] Specific mode → {len(all_pairs)} unique (undirected) pairs in DB: {all_pairs}")

        elif specific_multiple:
            fixed_pair_options = self.build_specific_multiple_map(hosts, opt)
            print(f"[✓] specific_multiple mode → {len(fixed_pair_options)} fixed mappings loaded.")

        else:
            all_pairs = self.dedupe_undirected_pairs(db_pairs)
            print(f"[✓] Random mode → will sample from {len(all_pairs)} unique (undirected) DB pairs.")

        if not all_pairs and not fixed_pair_options:
            print("[✗] No valid pairs available after applying your selection.")
            return False

        print("\n=== 🔄 One Route Mutation Cycle ===")

        all_rules = []

        if specific_multiple:
            print(f"[*] Using fixed mappings: {fixed_pair_options}")

            for (src, dst, chosen_opt) in fixed_pair_options:
                rules = self.get_rules(src, dst, chosen_opt)
                if not rules:
                    print(f"[!] No rules found for {src}->{dst} opt{chosen_opt}")
                    continue
                all_rules.extend(rules)
                print(f"[+] {src}->{dst} opt{chosen_opt}: {len(rules)} rules")

        else:
            if random_k is not None:
                k = random_k
                if len(all_pairs) <= k:
                    chosen_pairs = all_pairs
                else:
                    chosen_pairs = random.sample(all_pairs, k)
            else:
                chosen_pairs = all_pairs

            print(f"[*] Selected {len(chosen_pairs)} pairs: {chosen_pairs}")

            for (src, dst) in chosen_pairs:
                opts = self.get_available_options(src, dst)
                if not opts:
                    print(f"[!] No path options for {src}->{dst}")
                    continue
                chosen_opt = random.choice(opts)
                rules = self.get_rules(src, dst, chosen_opt)
                all_rules.extend(rules)
                print(f"[+] {src}->{dst} opt{chosen_opt}: {len(rules)} rules")

        self.clear_fwd_flows()

        with open(self.log_file, "w") as f:
            for r in all_rules:
                f.write(r.strip('"').strip() + "\n")
        print(f"[✓] Wrote {len(all_rules)} clean rules → {self.log_file}")

        if trigger_learning:
            self.trigger_relearning()

        return True


def route_shuffle_endpoint(**kwargs):
    mutator = RouteMutator(
        csv_file=kwargs.pop("csv_file", None),
        log_file=kwargs.pop("log_file", None),
    )
    return mutator.run_once(**kwargs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Callable Route Mutator")

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--random", type=int, metavar="K")
    mode.add_argument("--specific", type=str, metavar="PAIRS")
    mode.add_argument("--specific_multiple", action="store_true")
    mode.add_argument("--range", dest="range_str", type=str, metavar="A,B")

    parser.add_argument("--interval", type=int, default=20)
    parser.add_argument("--hosts", type=str)
    parser.add_argument("--opt", type=str)
    parser.add_argument("--csv-file", dest="csv_file", default="hop_list.csv")
    parser.add_argument("--log-file", dest="log_file", default="/tmp/path_match_log.txt")
    parser.add_argument("--trigger-learning", action="store_true")

    args = parser.parse_args()

    route_shuffle_endpoint(
        random_k=args.random,
        specific=args.specific,
        specific_multiple=args.specific_multiple,
        range_str=args.range_str,
        interval=args.interval,
        hosts=args.hosts,
        opt=args.opt,
        csv_file=args.csv_file,
        log_file=args.log_file,
        trigger_learning=args.trigger_learning,
    )