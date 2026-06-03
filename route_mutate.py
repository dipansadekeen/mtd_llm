#this one is the absolute code
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dynamic Random Route Mutation for ONOS (Quote-Safe Version)
------------------------------------------------------------
Fully self-contained script:
 • loads hop_list.csv as path database
 • strips any extra quotes
 • randomly selects host pairs each cycle
 • generates bidirectional path rules
 • clears ONOS flows
 • writes clean rules to /tmp/path_match_log.txt
"""


"""
USAGE EXAMPLES
--------------
1) Random K host-pairs per cycle (sampled from hop_list.csv):
   python3 rrm.py --random 10

2) Random K host-pairs per cycle with a fixed interval:
   python3 rrm.py --random 10 --interval 15

3) Use specific host pairs only (path option is still randomized each cycle):
   python3 rrm.py --specific "h1,h2;h3,h6"

4) Use a contiguous range of hosts (all ordered pairs within the range):
   python3 rrm.py --range "h1,h20"

5) Same as above, but with deterministic randomness (reproducible runs):
   python3 rrm.py --range "h1,h20" --seed 42

NOTES
-----
• hop_list.csv must contain paths for the selected (src,dst) pairs.
• For --range mode, the number of generated pairs grows as N×(N−1).
  Example: h1..h20 → 20×19 = 380 pairs.
• Each cycle randomly selects one available path option per (src,dst) pair.
• Both forward and reverse rules are generated automatically.
• Flow rules are written (without quotes) to /tmp/path_match_log.txt
• Existing ONOS fwd flows are cleared once per cycle before rule installation.
"""



import argparse
import re
import csv
import time
import random
import requests
import subprocess

# ==============================================================
# --- ONOS SETTINGS ---
# ==============================================================
ONOS = "http://127.0.0.1:8181/onos/v1"
AUTH = ("onos", "rocks")

LOG_FILE = "/tmp/path_match_log.txt"
CSV_FILE = "hop_list.csv"

CYCLE_INTERVAL = 20        # seconds between shuffles
PAIR_COUNT_PER_CYCLE = 10  # number of host pairs per cycle

# ==============================================================
# --- PATH DATABASE UTILITIES ---
# ==============================================================

# def load_path_database_from_csv(csv_file):
#     """Load hop_list.csv into {(src,dst,opt): line} dict (auto-strip quotes)."""
#     path_db = {}
#     try:
#         with open(csv_file, 'r') as f:
#             reader = csv.reader(f)
#             for row in reader:
#                 if not row or not row[0].strip():
#                     continue
#                 line = row[0].strip().strip('"').strip()  # remove any quotes
#                 parts = [p.strip() for p in line.split(',')]
#                 if len(parts) < 7:
#                     continue
#                 src, dst = parts[0], parts[1]
#                 try:
#                     opt = int(parts[2])
#                 except ValueError:
#                     opt = 1
#                 path_db[(src, dst, opt)] = line
#         print(f"[✓] Loaded {len(path_db)} paths from {csv_file}")
#     except FileNotFoundError:
#         print(f"[✗] CSV file '{csv_file}' not found.")
#     return path_db

def load_path_database_from_csv(csv_file):
    """
    Load hop_list.csv into {(src,dst,opt): line} dict.
    Supports BOTH formats:
      (A) proper CSV columns
      (B) single quoted string in column 0
    """
    path_db = {}
    try:
        with open(csv_file, 'r', newline='') as f:
            reader = csv.reader(f)
            for row in reader:
                if not row:
                    continue

                # If it's a real multi-column CSV: use row directly
                # If it's a single mega-string: split it once using csv again
                if len(row) >= 7:
                    parts = [c.strip().strip('"') for c in row]
                else:
                    line = row[0].strip().strip('"')
                    parts = [p.strip().strip('"') for p in line.split(',')]

                if len(parts) < 7:
                    continue

                src, dst = parts[0], parts[1]
                try:
                    opt = int(parts[2])
                except ValueError:
                    opt = 1

                # store a normalized line (no surrounding quotes)
                normalized = ", ".join(parts[:6] + parts[6:])
                path_db[(src, dst, opt)] = normalized

        print(f"[✓] Loaded {len(path_db)} paths from {csv_file}")
    except FileNotFoundError:
        print(f"[✗] CSV file '{csv_file}' not found.")
    return path_db



# def generate_path_rules(path_data):
#     """Create forward/reverse path rules from one CSV line (clean, no quotes)."""
#     parts = [p.strip() for p in path_data.strip().strip('"').split(',')]
#     src_host, dst_host, path_option = parts[:3]
#     hop_count = int(parts[3])
#     src_mac, dst_mac = parts[4], parts[5]
#     links = parts[6:]

#     rules = []
#     # forward
#     for i in range(len(links)):
#         sub = ', '.join(links[i:])
#         hops = len(links) - i
#         rules.append(f"{src_mac}, {dst_mac}, {sub}, {float(hops)}")
#     # reverse
#     rev_links = []
#     for l in links:
#         if '->' not in l:
#             continue
#         a,b = [x.strip() for x in l.split('->')]
#         rev_links.append(f"{b} -> {a}")
#     rev_links.reverse()
#     for i in range(len(rev_links)):
#         sub = ', '.join(rev_links[i:])
#         hops = len(rev_links) - i
#         rules.append(f"{dst_mac}, {src_mac}, {sub}, {float(hops)}")
#     return rules

def generate_path_rules(path_data):
    """Create forward/reverse path rules from one CSV line (clean, normalized spacing)."""
    parts = [p.strip() for p in path_data.strip().strip('"').split(',')]
    src_host, dst_host, path_option = parts[:3]
    # hop_count = int(parts[3])
    hop_count = int(float(parts[3]))
    src_mac, dst_mac = parts[4], parts[5]
    raw_links = parts[6:]

    # --- Normalize link format ---
    links = []
    for l in raw_links:
        l = l.strip().replace(' ', '')  # remove all stray spaces
        if '->' in l:
            a, b = l.split('->')
            links.append(f"{a.strip()} -> {b.strip()}")  # enforce correct spacing
        else:
            links.append(l.strip())

    rules = []
    # forward
    for i in range(len(links)):
        sub = ', '.join(links[i:])
        hops = len(links) - i
        rules.append(f"{src_mac}, {dst_mac}, {sub}, {float(hops)}")
    # reverse
    rev_links = []
    for l in links:
        if '->' not in l:
            continue
        a,b = [x.strip() for x in l.split('->')]
        rev_links.append(f"{b} -> {a}")
    rev_links.reverse()
    for i in range(len(rev_links)):
        sub = ', '.join(rev_links[i:])
        hops = len(rev_links) - i
        rules.append(f"{dst_mac}, {src_mac}, {sub}, {float(hops)}")
    return rules

def get_rules(src, dst, option, path_db):
    key = (src, dst, option)
    if key not in path_db:
        return []
    return generate_path_rules(path_db[key])


def get_available_options(src, dst, path_db):
    return sorted([opt for (s,d,opt) in path_db.keys() if s==src and d==dst])


def get_all_host_pairs(path_db):
    return sorted(list({(s,d) for (s,d,_) in path_db.keys()}))


# ==============================================================
# --- ONOS CONTROL HELPERS ---
# ==============================================================

def clear_fwd_flows():
    url = f"{ONOS}/flows/application/org.onosproject.fwd"
    r = requests.delete(url, auth=AUTH)
    print(f"[ONOS] Cleared fwd flows: HTTP {r.status_code}")

def clear_all_flows():
    devices_url = f"{ONOS}/devices"
    r = requests.get(devices_url, auth=AUTH)
    if r.status_code != 200:
        print(f"[ERROR] Could not get device list: {r.status_code}")
        return
    devices = [d["id"] for d in r.json().get("devices", [])]
    for dev in devices:
        url = f"{ONOS}/flows/{dev}"
        r2 = requests.delete(url, auth=AUTH)
        print(f"  Cleared flows on {dev}: HTTP {r2.status_code}")

def trigger_relearning():
    print("[*] Triggering ONOS re-learning (ARP+ping)")
    try:
        subprocess.run("mnexec -a $(cat /var/run/mininet/h1.pid) arping -c1 -A -I h1-eth0 10.0.0.1", shell=True)
        subprocess.run("mnexec -a $(cat /var/run/mininet/h1.pid) ping -c1 10.0.0.2", shell=True)
    except Exception as e:
        print(f"[!] Could not send ping/arp: {e}")

def parse_host_token(tok):
    """
    Accepts 'h20' (or '20') and returns ('h', 20) as (prefix, index).
    """
    tok = tok.strip()
    m = re.match(r'^([a-zA-Z]+)?(\d+)$', tok)
    if not m:
        raise ValueError(f"Invalid host token: {tok}")
    prefix = m.group(1) if m.group(1) else "h"
    idx = int(m.group(2))
    return prefix, idx

def build_pairs_from_range(range_str):
    """
    '--range "h1,h20"' -> all ordered pairs among h1..h20, excluding (hX,hX)
    """
    parts = [p.strip() for p in range_str.split(',') if p.strip()]
    if len(parts) != 2:
        raise ValueError(f"--range expects 'hA,hB' (example: h1,h20). Got: {range_str}")

    p1, a = parse_host_token(parts[0])
    p2, b = parse_host_token(parts[1])
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

def build_pairs_from_specific(spec_str):
    """
    '--specific "h1,h2;h3,h6"' -> [(h1,h2),(h3,h6)]
    Supports separators ';' between pairs, and ',' inside a pair.
    """
    spec_str = spec_str.strip().strip('"').strip("'")
    if not spec_str:
        return []

    pairs = []
    chunks = [c.strip() for c in spec_str.split(';') if c.strip()]
    for ch in chunks:
        ab = [x.strip() for x in ch.split(',') if x.strip()]
        if len(ab) != 2:
            raise ValueError(f"Invalid pair '{ch}'. Use format: h1,h2;h3,h6")
        pairs.append((ab[0], ab[1]))
    return pairs

def filter_pairs_to_db(pairs, path_db):
    """
    Keep only pairs that exist in hop_list.csv DB (have at least one option).
    """
    kept = []
    for (s, d) in pairs:
        if get_available_options(s, d, path_db):
            kept.append((s, d))
    return kept


def dedupe_undirected_pairs(pairs):
    """
    Remove reverse duplicates:
      keeps only one of (a,b) or (b,a).
    Order in output is stable (first occurrence wins).
    """
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

def build_specific_multiple_map(hosts_str, opt_str, path_db):
    """
    Example:
      --hosts "h1,h2;h1,h7"
      --opt   "3;4"

    Returns:
      [(h1, h2, 3), (h1, h7, 4)]
    """
    if not hosts_str or not opt_str:
        raise ValueError("--specific_multiple requires both --hosts and --opt")

    hosts_str = hosts_str.strip().strip('"').strip("'")
    opt_str = opt_str.strip().strip('"').strip("'")

    pair_chunks = [x.strip() for x in hosts_str.split(';') if x.strip()]
    opt_chunks = [x.strip() for x in opt_str.split(';') if x.strip()]

    if len(pair_chunks) != len(opt_chunks):
        raise ValueError(
            f"Host-pair count ({len(pair_chunks)}) must match option count ({len(opt_chunks)})"
        )

    result = []
    for pair_str, opt_val in zip(pair_chunks, opt_chunks):
        ab = [x.strip() for x in pair_str.split(',') if x.strip()]
        if len(ab) != 2:
            raise ValueError(f"Invalid host pair: {pair_str}")

        src, dst = ab[0], ab[1]

        try:
            opt = int(opt_val)
        except ValueError:
            raise ValueError(f"Invalid option number: {opt_val}")

        if (src, dst, opt) not in path_db:
            raise ValueError(f"No hop_list.csv entry for ({src}, {dst}, {opt})")

        result.append((src, dst, opt))

    return result


# ==============================================================
# --- MAIN RRM LOOP ---
# ==============================================================

if __name__ == "__main__":
    print("\n" + "="*70)
    print("🧠 Dynamic Random Route Mutation (Clean Quotes Version)")
    print("="*70)

    parser = argparse.ArgumentParser(
        description="Dynamic Random Route Mutation: choose pairs via --random, --specific, or --range"
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--random", type=int, metavar="K",
                      help="Pick K random host pairs per cycle (from DB). Example: --random 10")
    mode.add_argument("--specific", type=str, metavar="PAIRS",
                      help="Use exact pairs. Example: --specific 'h1,h2;h3,h6'")
    mode.add_argument("--specific_multiple", action="store_true",
                  help="Use exact host-pairs with exact path options from --hosts and --opt")
    mode.add_argument("--range", type=str, metavar="A,B",
                      help="Use all ordered pairs in range. Example: --range 'h1,h20'")

    parser.add_argument("--interval", type=int, default=CYCLE_INTERVAL,
                        help="Seconds between shuffles (default: 30)")

    parser.add_argument("--hosts", type=str,
                        help='For --specific_multiple. Example: "h1,h2;h1,h7"')

    parser.add_argument("--opt", type=str,
                        help='For --specific_multiple. Example: "3;4"')

    args = parser.parse_args()

    # override interval from CLI
    CYCLE_INTERVAL = args.interval



    PATH_DB = load_path_database_from_csv(CSV_FILE)
    if not PATH_DB:
        exit(1)

    # all_pairs = get_all_host_pairs(PATH_DB)
    # print(f"[✓] Found {len(all_pairs)} host pairs in DB.")



    db_pairs = get_all_host_pairs(PATH_DB)
    print(f"[✓] Found {len(db_pairs)} host pairs in DB.")

    fixed_pair_options = []
    all_pairs = []

    # Build the candidate pair list from CLI mode
    if args.range:
        candidate_pairs = build_pairs_from_range(args.range)
        candidate_pairs = filter_pairs_to_db(candidate_pairs, PATH_DB)
        all_pairs = dedupe_undirected_pairs(sorted(candidate_pairs))
        print(f"[✓] Range mode {args.range} → {len(all_pairs)} unique (undirected) pairs in DB.")

    elif args.specific:
        candidate_pairs = build_pairs_from_specific(args.specific)
        candidate_pairs = filter_pairs_to_db(candidate_pairs, PATH_DB)
        all_pairs = dedupe_undirected_pairs(sorted(candidate_pairs))
        print(f"[✓] Specific mode → {len(all_pairs)} unique (undirected) pairs in DB: {all_pairs}")

    elif args.specific_multiple:
        fixed_pair_options = build_specific_multiple_map(args.hosts, args.opt, PATH_DB)
        print(f"[✓] specific_multiple mode → {len(fixed_pair_options)} fixed mappings loaded.")

    else:
        all_pairs = dedupe_undirected_pairs(db_pairs)
        print(f"[✓] Random mode → will sample from {len(all_pairs)} unique (undirected) DB pairs.")

    if not all_pairs and not fixed_pair_options:
        print("[✗] No valid pairs available after applying your selection.")
        exit(1)

    cycle = 0
    while True:
        cycle += 1
        print(f"\n=== 🔄 Cycle {cycle} ===")

        # 1️⃣ Build rules based on mode
        all_rules = []

        if args.specific_multiple:
            print(f"[*] Using fixed mappings: {fixed_pair_options}")

            for (src, dst, opt) in fixed_pair_options:
                rules = get_rules(src, dst, opt, PATH_DB)
                if not rules:
                    print(f"[!] No rules found for {src}->{dst} opt{opt}")
                    continue
                all_rules.extend(rules)
                print(f"[+] {src}->{dst} opt{opt}: {len(rules)} rules")

        else:
            if args.random is not None:
                k = args.random
                if len(all_pairs) <= k:
                    chosen_pairs = all_pairs
                else:
                    chosen_pairs = random.sample(all_pairs, k)
            else:
                chosen_pairs = all_pairs

            print(f"[*] Selected {len(chosen_pairs)} pairs: {chosen_pairs}")

            for (src, dst) in chosen_pairs:
                opts = get_available_options(src, dst, PATH_DB)
                if not opts:
                    print(f"[!] No path options for {src}->{dst}")
                    continue
                opt = random.choice(opts)
                rules = get_rules(src, dst, opt, PATH_DB)
                all_rules.extend(rules)
                print(f"[+] {src}->{dst} opt{opt}: {len(rules)} rules")
            

        # 3️⃣ Clear flows in ONOS
        clear_fwd_flows()

        # 4️⃣ Write new rules (no quotes)
        with open(LOG_FILE,"w") as f:
            for r in all_rules:
                f.write(r.strip('"').strip() + "\n")
        print(f"[✓] Wrote {len(all_rules)} clean rules → {LOG_FILE}")

        # 5️⃣ Optional relearning
        # trigger_relearning()

        # 6️⃣ Wait before next cycle
        # print(f"[*] Sleeping {CYCLE_INTERVAL}s …")
        time.sleep(CYCLE_INTERVAL)
        # break
