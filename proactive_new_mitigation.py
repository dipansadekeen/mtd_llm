# # proactive_new_mitigation.py

# import pulp,time

# from ip_shuffle_endpoint import ip_shuffle_endpoint
# from mtd_utils import (
#     all_hosts,
#     SKIP_HOSTS,
#     ROUTE_HISTORY_SIZE,
#     HostIPQueueManager,
# )



# # //////////IP shuffle/////////////

# GAP_HISTORY = 3      # distance from history IPs
# GAP_ASSIGN = 8       # distance between final assigned IPs

# def min_dist(ip, refs):
#     return min(abs(ip - r) for r in refs) if refs else 254


# def ip_octet(x):
#     if x is None:
#         return None
#     return int(str(x).split(".")[-1])


# def solve_ip_assignment(selected_hosts, ip_manager, pool=range(1, 255), avoid_recent=True):
#     selected_hosts = [h for h in selected_hosts if h not in SKIP_HOSTS]

#     if not selected_hosts:
#         return {}

#     current_ips = ip_manager.get_current_ips()

#     history_by_host = {
#         h: {
#             ip_octet(x)
#             for x in ip_manager.get_host_ips(h)
#             if ip_octet(x) is not None
#         }
#         for h in all_hosts
#     }

#     all_history_ips = set().union(*history_by_host.values())

#     # used_by_others = {
#     #     ip_octet(ip)
#     #     for h, ip in current_ips.items()
#     #     if h not in selected_hosts and ip is not None
#     # }

#     # valid_pool = [ip for ip in pool if ip not in used_by_others]

#     # ////////////////////////// constraint crash solving 
#     all_current_ips = {
#             ip_octet(ip)
#             for ip in current_ips.values()
#             if ip is not None
#         }

#     valid_pool = [ip for ip in pool if ip not in all_current_ips]
#     # ////////////////////////// constraint crash solving 


#     # C7: pool sufficiency
#     if len(valid_pool) < len(selected_hosts):
#         raise RuntimeError("Not enough valid unused IPs.")

#     feasible = {}

#     # for h in selected_hosts:
#     #     current = ip_octet(current_ips.get(h))
#     #     # recent = {ip_octet(x) for x in ip_manager.get_host_ips(h)}
#     #     recent = history_by_host.get(h, set())

#     #     cand = []

#     #     for ip in valid_pool:
#     #         if ip == current:          # C3
#     #             continue
#     #         if avoid_recent and ip in recent:   # C4
#     #             continue

#     #         # new constraint 
#     #         # C8: avoid IPs close to any historical IP
#     #         if min_dist(ip, all_history_ips) < GAP_HISTORY:
#     #             continue

#     #         cand.append(ip)

#     #     if not cand:
#     #         raise RuntimeError(f"No feasible IP for {h}")

#     #     feasible[h] = cand


#     # ////// relaxing for ip constraint conflict 
#     for h in selected_hosts:
#             recent = history_by_host.get(h, set())

#             cand = []

#             for ip in valid_pool:
#                 # C3 dropped: covered by all_current_ips pool filter above.
#                 if avoid_recent and ip in recent:   # C4
#                     continue
#                 # C8 removed as hard filter — now soft, via the objective's
#                 # 0.3 * min_dist(ip, all_history_ips) term below.
#                 cand.append(ip)

#             if not cand:
#                 raise RuntimeError(f"No feasible IP for {h}")

#             feasible[h] = cand
#     # ////// relaxing for ip constraint conflict 

#     model = pulp.LpProblem("IP_Mutation_Assignment", pulp.LpMaximize)

#     x = {
#         (h, ip): pulp.LpVariable(f"x_{h}_{ip}", cat="Binary")
#         for h in selected_hosts
#         for ip in feasible[h]
#     }

#     # C1: each selected host gets exactly one IP
#     for h in selected_hosts:
#         model += pulp.lpSum(x[h, ip] for ip in feasible[h]) == 1

#     # C2: no duplicate IP among selected hosts
#     for ip in valid_pool:
#         model += pulp.lpSum(
#             x[h, ip] for h in selected_hosts if (h, ip) in x
#         ) <= 1

#     # C7/C9: avoid sequential or too-close assigned IPs
#     for i, h1 in enumerate(selected_hosts):
#         for h2 in selected_hosts[i + 1:]:
#             for ip1 in feasible[h1]:
#                 for ip2 in feasible[h2]:
#                     if abs(ip1 - ip2) < GAP_ASSIGN:
#                         model += x[h1, ip1] + x[h2, ip2] <= 1

#     # # Objective: maximize variation from current IP
#     # model += pulp.lpSum(
#     #     abs(ip - ip_octet(current_ips[h])) * x[h, ip]
#     #     for h in selected_hosts
#     #     for ip in feasible[h]
#     # )

#     # Objective: maximize distance from own current/history and global history | for new constraints
#     # model += pulp.lpSum(
#     #     (
#     #         0.4 * abs(ip - ip_octet(current_ips[h]))
#     #         + 0.3 * min_dist(ip, recent)
#     #         + 0.3 * min_dist(ip, all_history_ips)
#     #     ) * x[h, ip]
#     #     for h in selected_hosts
#     #     for ip in feasible[h]
#     #     for recent in [{ip_octet(v) for v in ip_manager.get_host_ips(h) if ip_octet(v) is not None}]
#     # )
#     model += pulp.lpSum(
#         (
#             0.4 * abs(ip - ip_octet(current_ips[h]))
#             + 0.3 * min_dist(ip, history_by_host[h])
#             + 0.3 * min_dist(ip, all_history_ips)
#         ) * x[h, ip]
#         for h in selected_hosts
#         for ip in feasible[h]
#     )

#     # model.solve(pulp.PULP_CBC_CMD(msg=False))

#     # added solving time ///////
#     t0 = time.perf_counter()
#     model.solve(pulp.PULP_CBC_CMD(msg=False))
#     solver_time_s = time.perf_counter() - t0

#     print(f"[IP ILP SOLVER TIME] {solver_time_s:.6f}s | status={pulp.LpStatus[model.status]}")
#     # added solving time ///////

#     if pulp.LpStatus[model.status] != "Optimal":
#         raise RuntimeError(f"IP ILP failed: {pulp.LpStatus[model.status]}")

#     return {
#         h: ip
#         for h in selected_hosts
#         for ip in feasible[h]
#         if pulp.value(x[h, ip]) > 0.5
#     }


# def update_ip_history(ip_manager, assignment):
#     current_ips = ip_manager.get_current_ips()

#     for h in all_hosts:
#         if h in assignment:
#             ip_manager.update_host_queue(h, assignment[h])
#         else:
#             ip_manager.update_host_queue(h, current_ips.get(h))

#     ip_manager.save_to_csv()


# def apply_ip_assignment(ip_manager, assignment):
#     """
#     Applies IP shuffle and updates IP history only after endpoint call.
#     """

#     if not assignment:
#         print("No IP assignment.")
#         update_ip_history(ip_manager, {})
#         return

#     result = ip_shuffle_endpoint(
#         host=",".join(assignment.keys()),
#         ips=",".join(str(assignment[h]) for h in assignment),
#         interval=30,
#         no_block_pid=True,
#     )

#     if result is False:
#         raise RuntimeError("IP shuffle failed. IP history was not updated.")

#     update_ip_history(ip_manager, assignment)

#     print("[IP ILP ASSIGNMENT]", assignment)


# def run_ip_ilp(selected_hosts):
#     ip_manager = HostIPQueueManager(queue_size=ROUTE_HISTORY_SIZE)

#     for i in range(1, 41):
#         ip_manager.set_host_ips(f"h{i}", [i])

#     ip_manager.load_from_csv()

#     try:
#         assignment = solve_ip_assignment(
#             selected_hosts,
#             ip_manager,
#             avoid_recent=True,
#         )
#     except RuntimeError as e:
#         print("[WARN]", e)
#         print("Retrying without recent-history constraint.")
#         assignment = solve_ip_assignment(
#             selected_hosts,
#             ip_manager,
#             avoid_recent=False,
#         )

#     if not assignment:
#         update_ip_history(ip_manager, {})
#         print("No IP assignment.")
#         return

#     # ip_shuffle_endpoint(
#     #     host=",".join(assignment.keys()),
#     #     ips=",".join(str(assignment[h]) for h in assignment),
#     #     interval=30,
#     #     no_block_pid=True,
#     # )

#     # update_ip_history(ip_manager, assignment)
#     apply_ip_assignment(ip_manager, assignment)


# # def run_once():
# #     ip_manager = HostIPQueueManager(queue_size=ROUTE_HISTORY_SIZE)

# #     for i in range(1, 41):
# #         ip_manager.set_host_ips(f"h{i}", [i])

# #     ip_manager.load_from_csv()

# #     action, selected_hosts, selected_routes, details = decide_ilp()

# #     print("Selected action:", action)
# #     print("Selected IP hosts:", selected_hosts)

# #     if action != "ip_shuffle" or not selected_hosts:
# #         update_ip_history(ip_manager, {})
# #         print("No IP shuffle. History repeated.")
# #         return

# #     try:
# #         assignment = solve_ip_assignment(
# #             selected_hosts,
# #             ip_manager,
# #             avoid_recent=True,
# #         )
# #     except RuntimeError as e:
# #         print("[WARN]", e)
# #         print("Retrying without recent-history constraint.")
# #         assignment = solve_ip_assignment(
# #             selected_hosts,
# #             ip_manager,
# #             avoid_recent=False,
# #         )

# #     print("IP assignment:", assignment)

# #     ip_shuffle_endpoint(
# #         host=",".join(assignment.keys()),
# #         ips=",".join(str(assignment[h]) for h in assignment),
# #         interval=30,
# #         no_block_pid=True,
# #     )

# #     update_ip_history(ip_manager, assignment)
# #     print("Done.")

# # //////////IP shuffle/////////////


# # if __name__ == "__main__":
# #     run_once()


# proactive_new_mitigation.py
#
# v2: sample-then-optimize randomized IP assignment.
#   - Hard constraints: one IP per host (C1), global uniqueness (C2),
#     not-currently-used pool filter (subsumes old C3), own recent
#     history (C4), min gap between assigned IPs (C7/C9) via the
#     window formulation (~250 constraints instead of ~400k pairwise).
#   - Variability: uniform random candidate sampling per host (K)
#     + i.i.d. Uniform(0,1) utility objective with a small normalized
#     distance-from-current bias.
#   - Entry point run_ip_ilp(selected_hosts) is unchanged, so
#     proactive_new_scoring.py / proactive_exp.py need no edits.

import random
import time

import pulp

from ip_shuffle_endpoint import ip_shuffle_endpoint
from mtd_utils import (
    all_hosts,
    SKIP_HOSTS,
    ROUTE_HISTORY_SIZE,
    HostIPQueueManager,
)


# //////////IP shuffle/////////////

GAP_ASSIGN = 3            # min distance between IPs assigned in the same cycle
CANDIDATES_PER_HOST = 40  # K: random sample size per host
DIST_WEIGHT = 0.15        # small bias away from current IP (0 disables)
SOLVER_TIME_LIMIT = 5     # seconds; safety cap, rarely hit
SOLVER_GAP_REL = 0.05     # accept within 5% of optimum


def ip_octet(x):
    if x is None:
        return None
    return int(str(x).split(".")[-1])


def solve_ip_assignment(
    selected_hosts,
    ip_manager,
    pool=range(1, 255),
    avoid_recent=True,
    k=CANDIDATES_PER_HOST,
    seed=None,
):
    """
    Randomized IP assignment (sample-then-optimize).

    Returns {host: octet} like the original. The per-cycle seed is
    printed in the [IP ILP SOLVER TIME] line for reproducibility.
    """
    selected_hosts = [h for h in selected_hosts if h not in SKIP_HOSTS]
    if not selected_hosts:
        return {}

    # --- Reproducible per-cycle randomness -------------------------------
    if seed is None:
        seed = random.SystemRandom().randrange(2**32)
    rng = random.Random(seed)

    current_ips = ip_manager.get_current_ips()

    history_by_host = {
        h: {
            ip_octet(x)
            for x in ip_manager.get_host_ips(h)
            if ip_octet(x) is not None
        }
        for h in all_hosts
    }

    # Pool filter: exclude every octet currently in use anywhere
    # (subsumes old C3; this was the infeasibility fix -- keep it).
    all_current_ips = {
        ip_octet(ip)
        for ip in current_ips.values()
        if ip is not None
    }
    valid_pool = [ip for ip in pool if ip not in all_current_ips]

    # C7: pool sufficiency
    if len(valid_pool) < len(selected_hosts):
        raise RuntimeError("Not enough valid unused IPs.")

    # --- Layer 1: per-host feasible set, then uniform random sample ------
    feasible = {}
    for h in selected_hosts:
        recent = history_by_host.get(h, set())

        cand = [
            ip for ip in valid_pool
            if not (avoid_recent and ip in recent)   # C4 (hard)
        ]

        if not cand:
            raise RuntimeError(f"No feasible IP for {h}")

        if len(cand) > k:
            cand = rng.sample(cand, k)

        feasible[h] = cand

    # --- Model ------------------------------------------------------------
    model = pulp.LpProblem("IP_Mutation_Assignment", pulp.LpMaximize)

    x = {
        (h, ip): pulp.LpVariable(f"x_{h}_{ip}", cat="Binary")
        for h in selected_hosts
        for ip in feasible[h]
    }

    # C1: each selected host gets exactly one IP
    for h in selected_hosts:
        model += pulp.lpSum(x[h, ip] for ip in feasible[h]) == 1

    # C2: no duplicate IP among selected hosts
    used_ips = {ip for cands in feasible.values() for ip in cands}
    for ip in used_ips:
        vars_ip = [x[h, ip] for h in selected_hosts if (h, ip) in x]
        if len(vars_ip) > 1:
            model += pulp.lpSum(vars_ip) <= 1

    # C7/C9: min-gap via sliding windows.
    # Any two IPs with |a - b| < GAP_ASSIGN share the window starting at
    # min(a, b), so "at most one assignment per window" is equivalent to
    # the old pairwise constraints -- with ~250 constraints, not ~400k.
    if used_ips:
        lo, hi = min(used_ips), max(used_ips)
        for v in range(lo, hi + 1):
            window = [
                x[h, ip]
                for h in selected_hosts
                for ip in feasible[h]
                if v <= ip < v + GAP_ASSIGN
            ]
            if len(window) > 1:
                model += pulp.lpSum(window) <= 1

    # --- Layer 2: randomized objective ------------------------------------
    # Dominant term: i.i.d. Uniform(0,1) utility per (host, ip)
    #   -> the ILP samples near-uniformly from the feasible assignment
    #      set (maximum-entropy selection subject to constraints), and
    #      random coefficients break the ties that made CBC branch.
    # Small term: normalized distance from current IP (mild bias only).
    def score(h, ip):
        u = rng.random()
        cur = ip_octet(current_ips.get(h))
        dist = abs(ip - cur) / 254.0 if cur is not None else 0.0
        return u + DIST_WEIGHT * dist

    model += pulp.lpSum(score(h, ip) * x[h, ip] for (h, ip) in x)

    # --- Solve with safety caps -------------------------------------------
    t0 = time.perf_counter()
    model.solve(
        pulp.PULP_CBC_CMD(
            msg=False,
            timeLimit=SOLVER_TIME_LIMIT,
            gapRel=SOLVER_GAP_REL,
        )
    )
    solver_time_s = time.perf_counter() - t0

    status = pulp.LpStatus[model.status]
    print(
        f"[IP ILP SOLVER TIME] {solver_time_s:.6f}s "
        f"| status={status} | seed={seed}"
    )

    assignment = {
        h: ip
        for h in selected_hosts
        for ip in feasible[h]
        if pulp.value(x[h, ip]) is not None and pulp.value(x[h, ip]) > 0.5
    }

    # Accept a time-limit incumbent as long as it is complete; a
    # suboptimal solution of a *random* objective is still a valid
    # random assignment. Only fail if no complete assignment exists.
    if len(assignment) != len(selected_hosts):
        if status == "Infeasible":
            raise RuntimeError("IP ILP infeasible with sampled candidates.")
        raise RuntimeError(f"IP ILP failed: {status}")

    return assignment


def update_ip_history(ip_manager, assignment):
    current_ips = ip_manager.get_current_ips()

    for h in all_hosts:
        if h in assignment:
            ip_manager.update_host_queue(h, assignment[h])
        else:
            ip_manager.update_host_queue(h, current_ips.get(h))

    ip_manager.save_to_csv()


def apply_ip_assignment(ip_manager, assignment):
    """
    Applies IP shuffle and updates IP history only after endpoint call.
    """

    if not assignment:
        print("No IP assignment.")
        update_ip_history(ip_manager, {})
        return

    result = ip_shuffle_endpoint(
        host=",".join(assignment.keys()),
        ips=",".join(str(assignment[h]) for h in assignment),
        interval=30,
        no_block_pid=True,
    )

    if result is False:
        raise RuntimeError("IP shuffle failed. IP history was not updated.")

    update_ip_history(ip_manager, assignment)

    print("[IP ILP ASSIGNMENT]", assignment)


def run_ip_ilp(selected_hosts):
    ip_manager = HostIPQueueManager(queue_size=ROUTE_HISTORY_SIZE)

    for i in range(1, 41):
        ip_manager.set_host_ips(f"h{i}", [i])

    ip_manager.load_from_csv()

    try:
        assignment = solve_ip_assignment(
            selected_hosts,
            ip_manager,
            avoid_recent=True,
        )
    except RuntimeError as e:
        print("[WARN]", e)
        print("Retrying with larger candidate sample.")
        try:
            assignment = solve_ip_assignment(
                selected_hosts,
                ip_manager,
                avoid_recent=True,
                k=60,
            )
        except RuntimeError as e:
            print("[WARN]", e)
            print("Retrying without recent-history constraint.")
            assignment = solve_ip_assignment(
                selected_hosts,
                ip_manager,
                avoid_recent=False,
                k=60,
            )

    if not assignment:
        update_ip_history(ip_manager, {})
        print("No IP assignment.")
        return

    apply_ip_assignment(ip_manager, assignment)

# //////////IP shuffle/////////////

