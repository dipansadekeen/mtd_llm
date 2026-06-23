
# proactive_new_mitigation_route.py

import csv, pulp
from collections import defaultdict

from route_mutate_endpoint import route_shuffle_endpoint
from mtd_utils import RouteHistoryManager, all_hosts, ROUTE_HISTORY_SIZE

HOP_LIST_FILE = "hop_list.csv"
LINK_STATS_FILE = "link_stats_onos.csv"

CAPACITY_MBPS = 1.0
THETA = 0.8          # safety threshold: 80%
DEFAULT_DEMAND = 0.05

HOP_WEIGHT = 0.30
LOAD_WEIGHT = 1.00
OLD_LINK_REUSE_WEIGHT = 2.00
OLD_LINK_LOAD_WEIGHT = 1.00
OVERLOAD_WEIGHT = 100.0
MULTI_FLOW_OVERLAP_WEIGHT = 10.0


def pair_key(a, b):
    return tuple(sorted((a, b), key=lambda x: int(x[1:])))


def latest_recorded_option(xs, default=0):
    """
    In this design:
        latest history value = currently active route option/state
        0 = default route / no custom route active for this pair
    """
    if not xs:
        return default

    try:
        return int(xs[-1])
    except Exception:
        return default


# def load_link_loads():
#     rows = []
#     with open(LINK_STATS_FILE, newline="") as f:
#         for r in csv.DictReader(f):
#             # rows.append((r["timestamp"], r["link_id"].strip(), float(r["tx_mbps"])))
#             rows.append((r["timestamp"], r["link_id"].strip(), max(rx, tx)))
#     if not rows:
#         return {}
#     latest = max(r[0] for r in rows)
#     return {lid: mbps for ts, lid, mbps in rows if ts == latest}

def load_link_loads():
    rows = []

    with open(LINK_STATS_FILE, newline="") as f:
        for r in csv.DictReader(f):
            rx = float(r.get("rx_mbps", 0.0) or 0.0)
            tx = float(r.get("tx_mbps", 0.0) or 0.0)
            mbps = max(rx, tx)

            # rows.append((r["timestamp"], r["link_id"].strip(), mbps))
            norm_link = normalize_link_id(r["link_id"].strip())
            rows.append((r["timestamp"], norm_link, mbps))

    if not rows:
        return {}

    latest = max(r[0] for r in rows)

    return {
        lid: mbps
        for ts, lid, mbps in rows
        if ts == latest
    }

def dpid_to_switch(device_id):
    dev = str(device_id).strip()

    if dev.startswith("of:"):
        body = dev.replace("of:", "")
        body = body.split("/")[0]
        body = body.split(":")[0]
        return f"s{int(body, 16)}"

    # If already like s1/1 or s1:1, keep only switch name
    dev = dev.split("/")[0]
    dev = dev.split(":")[0]

    return dev


def normalize_link_id(link_str):
    """
    Normalize ONOS link IDs into undirected switch-pair keys.

    Example:
        of:0000000000000001/1->of:0000000000000002/2
        becomes ('s1', 's2')
    """
    s = str(link_str).strip()

    if "->" not in s:
        return s

    left, right = [x.strip() for x in s.split("->", 1)]

    return tuple(sorted([
        dpid_to_switch(left),
        dpid_to_switch(right),
    ]))



def load_paths():
    """
    Returns:
      paths[(h1,h30)][option] = {"hops": 3, "links": [...]}
    """
    paths = defaultdict(dict)

    with open(HOP_LIST_FILE, newline="") as f:
        for r in csv.reader(f):
            if len(r) < 7:
                continue

            a, b = r[0].strip(), r[1].strip()
            opt = int(r[2])
            hops = float(r[3])
            path = r[6].strip()

            links = []
            for part in path.split(","):
                part = part.strip()
                # if "->" in part:
                #     links.append(part)
                if "->" in part:
                    links.append(normalize_link_id(part))

            paths[pair_key(a, b)][opt] = {
                "hops": hops,
                "links": links,
            }

    return paths


def recent_options(route_manager, a, b):
    return set(int(x) for x in route_manager.get_pair_history(a, b) if int(x) != 0)


def solve_route_assignment(selected_pairs, route_manager, demand=None, avoid_recent=True):
    """
    selected_pairs:
        [("h1","h30"), ("h1","h35")]

    demand:
        {("h1","h30"): 0.2, ...} in Mbps
    """

    current_option_map = {}
    current_links_map = {}

    demand = demand or {}
    paths = load_paths()
    link_load = load_link_loads()

    selected_pairs = [pair_key(a, b) for a, b in selected_pairs]

    if not selected_pairs:
        return {}

    feasible = {}

    for a, b in selected_pairs:
        p = pair_key(a, b)
        opts = list(paths.get(p, {}).keys())

        if not opts:
            raise RuntimeError(f"No path options for {p}")

        hist = route_manager.get_pair_history(a, b)
        # current = last_nonzero(hist)
        current = latest_recorded_option(hist, default=0)

        current_option_map[p] = current
        current_links_map[p] = set(paths[p].get(current, {}).get("links", []))

        recent = recent_options(route_manager, a, b)

        cand = []
        for opt in opts:
            if current is not None and opt == current:   # C3
                continue
            if avoid_recent and opt in recent:           # C8
                continue
            cand.append(opt)

        if not cand:
            raise RuntimeError(f"No feasible route option for {p}")

        feasible[p] = cand

    model = pulp.LpProblem("Route_Assignment", pulp.LpMinimize)

    y = {
        (p, opt): pulp.LpVariable(f"y_{p[0]}_{p[1]}_{opt}", cat="Binary")
        for p in selected_pairs
        for opt in feasible[p]
    }

    # overload = {
    #     l: pulp.LpVariable(f"overload_{i}", lowBound=0)
    #     for i, l in enumerate(link_load.keys())
    # }

    # overlap = {
    #     l: pulp.LpVariable(f"overlap_{i}", lowBound=0)
    #     for i, l in enumerate(link_load.keys())
    # }

    # # C1: each selected route gets exactly one valid option
    # for p in selected_pairs:
    #     model += pulp.lpSum(y[p, opt] for opt in feasible[p]) == 1

    # # Link constraints C4, C5, C6, C7
    # all_links = set(link_load.keys())

    # for p in selected_pairs:
    #     for opt in feasible[p]:
    #         all_links.update(paths[p][opt]["links"])

    # C1: each selected route gets exactly one valid option
    for p in selected_pairs:
        model += pulp.lpSum(y[p, opt] for opt in feasible[p]) == 1

    # Build all links first
    all_links = set(link_load.keys())

    for p in selected_pairs:
        all_links.update(current_links_map.get(p, set()))

        for opt in feasible[p]:
            all_links.update(paths[p][opt]["links"])

    overload = {
        l: pulp.LpVariable(f"overload_{i}", lowBound=0)
        for i, l in enumerate(sorted(all_links))
    }

    overlap = {
        l: pulp.LpVariable(f"overlap_{i}", lowBound=0)
        for i, l in enumerate(sorted(all_links))
    }

    # for l in all_links:
    #     current_load = link_load.get(l, 0.0)

    #     added_load = []
    #     used_count = []

    #     for p in selected_pairs:
    #         d = demand.get(p, DEFAULT_DEMAND)

    #         for opt in feasible[p]:
    #             if l in paths[p][opt]["links"]:
    #                 added_load.append(d * y[p, opt])
    #                 used_count.append(y[p, opt])

    #     final_load = current_load + pulp.lpSum(added_load)

    #     # C4/C5/C6: soft threshold/capacity
    #     model += final_load <= THETA * CAPACITY_MBPS + overload.get(
    #         l, pulp.LpVariable(f"overload_extra_{len(overload)}", lowBound=0)
    #     )

    #     # C7: overlap soft constraint
    #     if used_count:
    #         model += pulp.lpSum(used_count) <= 1 + overlap.get(
    #             l, pulp.LpVariable(f"overlap_extra_{len(overlap)}", lowBound=0)
    #         )

    for l in all_links:
        current_load = link_load.get(l, 0.0)

        removed_load = []
        added_load = []
        used_count = []

        for p in selected_pairs:
            d = demand.get(p, DEFAULT_DEMAND)

            # Remove selected flow demand from its current active path
            if l in current_links_map.get(p, set()):
                removed_load.append(d)

            # Add selected flow demand to its newly assigned path
            for opt in feasible[p]:
                if l in paths[p][opt]["links"]:
                    added_load.append(d * y[p, opt])
                    used_count.append(y[p, opt])

        final_load = (
            current_load
            - pulp.lpSum(removed_load)
            + pulp.lpSum(added_load)
        )

        # Capacity/safety threshold
        model += final_load <= THETA * CAPACITY_MBPS + overload[l]

        # Softly avoid putting many selected reroutes on the same link
        if used_count:
            model += pulp.lpSum(used_count) <= 1 + overlap[l]


    # Objective: minimize overload + overlap + hop count + current load usage
    # obj = []

    # for p in selected_pairs:
    #     for opt in feasible[p]:
    #         info = paths[p][opt]
    #         hop_cost = info["hops"]
    #         load_cost = sum(link_load.get(l, 0.0) for l in info["links"])

    #         obj.append((0.30 * hop_cost + 1.00 * load_cost) * y[p, opt])

    # obj += [100.0 * v for v in overload.values()]
    # obj += [10.0 * v for v in overlap.values()]

    # model += pulp.lpSum(obj)

    obj = []

    for p in selected_pairs:
        old_links = current_links_map.get(p, set())

        for opt in feasible[p]:
            info = paths[p][opt]

            new_links = set(info["links"])
            shared_old_links = new_links.intersection(old_links)

            hop_cost = info["hops"]

            # Prefer currently less-loaded new paths
            load_cost = sum(link_load.get(l, 0.0) for l in new_links)

            # Prefer new paths that reuse fewer links from the current active path
            old_link_reuse_ratio = len(shared_old_links) / max(1, len(old_links))

            # Extra penalty if reused old links are already loaded
            old_link_reuse_load = sum(link_load.get(l, 0.0) for l in shared_old_links)

            path_cost = (
                HOP_WEIGHT * hop_cost
                + LOAD_WEIGHT * load_cost
                + OLD_LINK_REUSE_WEIGHT * old_link_reuse_ratio
                + OLD_LINK_LOAD_WEIGHT * old_link_reuse_load
            )

            obj.append(path_cost * y[p, opt])

    obj += [OVERLOAD_WEIGHT * v for v in overload.values()]
    obj += [MULTI_FLOW_OVERLAP_WEIGHT * v for v in overlap.values()]

    model += pulp.lpSum(obj)

    model.solve(pulp.PULP_CBC_CMD(msg=False))

    if pulp.LpStatus[model.status] != "Optimal":
        raise RuntimeError(f"Route ILP failed: {pulp.LpStatus[model.status]}")

    assignment = {}

    for p in selected_pairs:
        for opt in feasible[p]:
            if pulp.value(y[p, opt]) > 0.5:
                assignment[p] = opt

    return assignment


def apply_route_assignment(route_manager, assignment):
    """
    Calls the existing route mutation endpoint and updates route history.
    """

    if not assignment:
        print("No route assignment.")
        return

    hosts_arg = []
    opts_arg = []
    selected_for_history = []

    # we got a bug, sometimes h1,h28 -opt 9 is not available but h28,h1 opt-9 exist
    # for (a, b), opt in assignment.items():
    #     hosts_arg.append(f"{a},{b}")
    #     opts_arg.append(str(opt))
    #     selected_for_history.append((a, b, opt))


    #///////////////////// to handle the  ||bug, sometimes h1,h28 -opt 9 is not available but h28,h1 opt-9 exist
    hop_rows = {
        (r[0].strip(), r[1].strip(), int(r[2]))
        for r in csv.reader(open(HOP_LIST_FILE))
        if len(r) >= 3
    }

    for (a, b), opt in assignment.items():
        hist_a, hist_b = a, b   # keep original/normalized pair for history

        if (a, b, opt) not in hop_rows and (b, a, opt) in hop_rows:
            print(f"[FLIP ROUTE APPLY] ({a},{b},{opt}) missing; using ({b},{a},{opt})")
            a, b = b, a

        hosts_arg.append(f"{a},{b}")
        opts_arg.append(str(opt))

        # keep history based on selected pair, not flipped endpoint direction
        selected_for_history.append((hist_a, hist_b, opt))
    #///////////////////// to handle the  ||bug, sometimes h1,h28 -opt 9 is not available but h28,h1 opt-9 exist

    route_shuffle_endpoint(
        specific_multiple=True,
        hosts=";".join(hosts_arg),
        opt=";".join(opts_arg),
    )
    
    route_manager.update_cycle(selected_for_history)
    route_manager.save_to_csv()

    print("[ROUTE ILP ASSIGNMENT]", assignment)


def run_route_ilp(selected_pairs):
    route_manager = RouteHistoryManager(all_hosts, queue_size=ROUTE_HISTORY_SIZE)
    route_manager.load_from_csv()

    try:
        assignment = solve_route_assignment(
            selected_pairs,
            route_manager,
            avoid_recent=True,
        )
    except RuntimeError as e:
        print("[WARN]", e)
        print("Retrying without recent-route restriction.")
        assignment = solve_route_assignment(
            selected_pairs,
            route_manager,
            avoid_recent=False,
        )

    apply_route_assignment(route_manager, assignment)


# if __name__ == "__main__":
#     # Example only. Replace with selected route pairs from your decision ILP.
#     run_route_ilp([
#         ("h1", "h30"),
#         ("h1", "h35"),
#     ])