# proactive_new_mitigation.py

import pulp,time

from ip_shuffle_endpoint import ip_shuffle_endpoint
from mtd_utils import (
    all_hosts,
    SKIP_HOSTS,
    ROUTE_HISTORY_SIZE,
    HostIPQueueManager,
)



# //////////IP shuffle/////////////

GAP_HISTORY = 3      # distance from history IPs
GAP_ASSIGN = 8       # distance between final assigned IPs

def min_dist(ip, refs):
    return min(abs(ip - r) for r in refs) if refs else 254


def ip_octet(x):
    if x is None:
        return None
    return int(str(x).split(".")[-1])


def solve_ip_assignment(selected_hosts, ip_manager, pool=range(1, 255), avoid_recent=True):
    selected_hosts = [h for h in selected_hosts if h not in SKIP_HOSTS]

    if not selected_hosts:
        return {}

    current_ips = ip_manager.get_current_ips()

    history_by_host = {
        h: {
            ip_octet(x)
            for x in ip_manager.get_host_ips(h)
            if ip_octet(x) is not None
        }
        for h in all_hosts
    }

    all_history_ips = set().union(*history_by_host.values())

    # used_by_others = {
    #     ip_octet(ip)
    #     for h, ip in current_ips.items()
    #     if h not in selected_hosts and ip is not None
    # }

    # valid_pool = [ip for ip in pool if ip not in used_by_others]

    # ////////////////////////// constraint crash solving 
    all_current_ips = {
            ip_octet(ip)
            for ip in current_ips.values()
            if ip is not None
        }

    valid_pool = [ip for ip in pool if ip not in all_current_ips]
    # ////////////////////////// constraint crash solving 


    # C7: pool sufficiency
    if len(valid_pool) < len(selected_hosts):
        raise RuntimeError("Not enough valid unused IPs.")

    feasible = {}

    # for h in selected_hosts:
    #     current = ip_octet(current_ips.get(h))
    #     # recent = {ip_octet(x) for x in ip_manager.get_host_ips(h)}
    #     recent = history_by_host.get(h, set())

    #     cand = []

    #     for ip in valid_pool:
    #         if ip == current:          # C3
    #             continue
    #         if avoid_recent and ip in recent:   # C4
    #             continue

    #         # new constraint 
    #         # C8: avoid IPs close to any historical IP
    #         if min_dist(ip, all_history_ips) < GAP_HISTORY:
    #             continue

    #         cand.append(ip)

    #     if not cand:
    #         raise RuntimeError(f"No feasible IP for {h}")

    #     feasible[h] = cand


    # ////// relaxing for ip constraint conflict 
    for h in selected_hosts:
            recent = history_by_host.get(h, set())

            cand = []

            for ip in valid_pool:
                # C3 dropped: covered by all_current_ips pool filter above.
                if avoid_recent and ip in recent:   # C4
                    continue
                # C8 removed as hard filter — now soft, via the objective's
                # 0.3 * min_dist(ip, all_history_ips) term below.
                cand.append(ip)

            if not cand:
                raise RuntimeError(f"No feasible IP for {h}")

            feasible[h] = cand
    # ////// relaxing for ip constraint conflict 

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
    for ip in valid_pool:
        model += pulp.lpSum(
            x[h, ip] for h in selected_hosts if (h, ip) in x
        ) <= 1

    # C7/C9: avoid sequential or too-close assigned IPs
    for i, h1 in enumerate(selected_hosts):
        for h2 in selected_hosts[i + 1:]:
            for ip1 in feasible[h1]:
                for ip2 in feasible[h2]:
                    if abs(ip1 - ip2) < GAP_ASSIGN:
                        model += x[h1, ip1] + x[h2, ip2] <= 1

    # # Objective: maximize variation from current IP
    # model += pulp.lpSum(
    #     abs(ip - ip_octet(current_ips[h])) * x[h, ip]
    #     for h in selected_hosts
    #     for ip in feasible[h]
    # )

    # Objective: maximize distance from own current/history and global history | for new constraints
    # model += pulp.lpSum(
    #     (
    #         0.4 * abs(ip - ip_octet(current_ips[h]))
    #         + 0.3 * min_dist(ip, recent)
    #         + 0.3 * min_dist(ip, all_history_ips)
    #     ) * x[h, ip]
    #     for h in selected_hosts
    #     for ip in feasible[h]
    #     for recent in [{ip_octet(v) for v in ip_manager.get_host_ips(h) if ip_octet(v) is not None}]
    # )
    model += pulp.lpSum(
        (
            0.4 * abs(ip - ip_octet(current_ips[h]))
            + 0.3 * min_dist(ip, history_by_host[h])
            + 0.3 * min_dist(ip, all_history_ips)
        ) * x[h, ip]
        for h in selected_hosts
        for ip in feasible[h]
    )

    # model.solve(pulp.PULP_CBC_CMD(msg=False))

    # added solving time ///////
    t0 = time.perf_counter()
    model.solve(pulp.PULP_CBC_CMD(msg=False))
    solver_time_s = time.perf_counter() - t0

    print(f"[IP ILP SOLVER TIME] {solver_time_s:.6f}s | status={pulp.LpStatus[model.status]}")
    # added solving time ///////

    if pulp.LpStatus[model.status] != "Optimal":
        raise RuntimeError(f"IP ILP failed: {pulp.LpStatus[model.status]}")

    return {
        h: ip
        for h in selected_hosts
        for ip in feasible[h]
        if pulp.value(x[h, ip]) > 0.5
    }


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
        print("Retrying without recent-history constraint.")
        assignment = solve_ip_assignment(
            selected_hosts,
            ip_manager,
            avoid_recent=False,
        )

    if not assignment:
        update_ip_history(ip_manager, {})
        print("No IP assignment.")
        return

    # ip_shuffle_endpoint(
    #     host=",".join(assignment.keys()),
    #     ips=",".join(str(assignment[h]) for h in assignment),
    #     interval=30,
    #     no_block_pid=True,
    # )

    # update_ip_history(ip_manager, assignment)
    apply_ip_assignment(ip_manager, assignment)


# def run_once():
#     ip_manager = HostIPQueueManager(queue_size=ROUTE_HISTORY_SIZE)

#     for i in range(1, 41):
#         ip_manager.set_host_ips(f"h{i}", [i])

#     ip_manager.load_from_csv()

#     action, selected_hosts, selected_routes, details = decide_ilp()

#     print("Selected action:", action)
#     print("Selected IP hosts:", selected_hosts)

#     if action != "ip_shuffle" or not selected_hosts:
#         update_ip_history(ip_manager, {})
#         print("No IP shuffle. History repeated.")
#         return

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

#     print("IP assignment:", assignment)

#     ip_shuffle_endpoint(
#         host=",".join(assignment.keys()),
#         ips=",".join(str(assignment[h]) for h in assignment),
#         interval=30,
#         no_block_pid=True,
#     )

#     update_ip_history(ip_manager, assignment)
#     print("Done.")

# //////////IP shuffle/////////////


# if __name__ == "__main__":
#     run_once()