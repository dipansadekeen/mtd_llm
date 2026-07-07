# # benchmark_route_reroute_time.py

# import time
# import csv
# from datetime import datetime

# from proactive_new_scoring import decide_ilp
# from proactive_new_mitigation_route import run_route_ilp

# SIZES = [10, 20, 30, 40]
# REPEATS = 5
# OUT_CSV = "route_reroute_timing.csv"


# def log_row(row):
#     write_header = False
#     try:
#         open(OUT_CSV, "r").close()
#     except FileNotFoundError:
#         write_header = True

#     with open(OUT_CSV, "a", newline="") as f:
#         w = csv.DictWriter(f, fieldnames=row.keys())
#         if write_header:
#             w.writeheader()
#         w.writerow(row)


# def unique_pairs_from_candidates(route_candidates):
#     seen = set()
#     pairs = []

#     for r in route_candidates:
#         p = (r["src"], r["dst"])

#         if p not in seen:
#             seen.add(p)
#             pairs.append(p)

#     return pairs


# def main():
#     # Build current route candidates once
#     action, hosts, routes, details = decide_ilp()

#     route_candidates = details.get("route_candidates", [])
#     candidate_pairs = unique_pairs_from_candidates(route_candidates)

#     print(f"[INFO] available route pairs = {len(candidate_pairs)}")

#     for n in SIZES:
#         if len(candidate_pairs) < n:
#             print(f"[SKIP] requested {n}, but only {len(candidate_pairs)} route pairs available")
#             continue

#         selected_pairs = candidate_pairs[:n]

#         for rep in range(1, REPEATS + 1):
#             t0 = time.perf_counter()
#             run_route_ilp(selected_pairs)
#             elapsed = time.perf_counter() - t0

#             row = {
#                 "timestamp": datetime.now().isoformat(timespec="seconds"),
#                 "n_routes": n,
#                 "repeat": rep,
#                 "reroute_time_s": round(elapsed, 6),
#                 "avg_time_per_route_s": round(elapsed / n, 6),
#                 "selected_pairs": "|".join(f"{a}-{b}" for a, b in selected_pairs),
#             }

#             log_row(row)

#             print(
#                 f"[DONE] routes={n} rep={rep} "
#                 f"time={elapsed:.6f}s avg={elapsed/n:.6f}s/route"
#             )


# if __name__ == "__main__":
#     main()



# benchmark_ip_shuffle_time.py

import time
import csv
from datetime import datetime

from proactive_new_scoring import decide_ilp
from proactive_new_mitigation import run_ip_ilp

SIZES = [10, 20, 30, 39]   # use 39 if h1 is excluded
REPEATS = 5
OUT_CSV = "ip_shuffle_timing.csv"


def log_row(row):
    try:
        open(OUT_CSV, "r").close()
        write_header = False
    except FileNotFoundError:
        write_header = True

    with open(OUT_CSV, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=row.keys())
        if write_header:
            w.writeheader()
        w.writerow(row)


def main():
    action, hosts, routes, details = decide_ilp()

    ip_candidates = details.get("ip_candidates", [])
    candidate_hosts = [c["host"] for c in ip_candidates]

    print(f"[INFO] available IP candidates = {len(candidate_hosts)}")
    print("[INFO] candidates:", candidate_hosts)

    for n in SIZES:
        if len(candidate_hosts) < n:
            print(f"[SKIP] requested {n}, but only {len(candidate_hosts)} hosts available")
            continue

        selected_hosts = candidate_hosts[:n]

        for rep in range(1, REPEATS + 1):
            t0 = time.perf_counter()
            run_ip_ilp(selected_hosts)
            elapsed = time.perf_counter() - t0

            row = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "n_hosts": n,
                "repeat": rep,
                "ip_shuffle_time_s": round(elapsed, 6),
                "avg_time_per_host_s": round(elapsed / n, 6),
                "selected_hosts": "|".join(selected_hosts),
            }

            log_row(row)

            print(
                f"[DONE] hosts={n} rep={rep} "
                f"time={elapsed:.6f}s avg={elapsed/n:.6f}s/host"
            )


if __name__ == "__main__":
    main()