# route_ilp_mutation_compact.py

import csv, pulp
from collections import defaultdict

from route_mutate_endpoint import route_shuffle_endpoint
from mtd_utils import RouteHistoryManager, all_hosts, ROUTE_HISTORY_SIZE

HOP_LIST_FILE = "hop_list.csv"
LINK_STATS_FILE = "link_stats_onos.csv"

CAPACITY_MBPS = 1.0
THETA = 0.8          # safety threshold: 80%
DEFAULT_DEMAND = 0.05


def pair_key(a, b):
    return tuple(sorted((a, b), key=lambda x: int(x[1:])))


def last_nonzero(xs):
    for x in reversed(xs):
        if int(x) != 0:
            return int(x)
    return None


def load_link_loads():
    rows = []
    with open(LINK_STATS_FILE, newline="") as f:
        for r in csv.DictReader(f):
            rows.append((r["timestamp"], r["link_id"].strip(), float(r["tx_mbps"])))
    if not rows:
        return {}
    latest = max(r[0] for r in rows)
    return {lid: mbps for ts, lid, mbps in rows if ts == latest}


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
                if "->" in part:
                    links.append(part)

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
        current = last_nonzero(hist)
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

    overload = {
        l: pulp.LpVariable(f"overload_{i}", lowBound=0)
        for i, l in enumerate(link_load.keys())
    }

    overlap = {
        l: pulp.LpVariable(f"overlap_{i}", lowBound=0)
        for i, l in enumerate(link_load.keys())
    }

    # C1: each selected route gets exactly one valid option
    for p in selected_pairs:
        model += pulp.lpSum(y[p, opt] for opt in feasible[p]) == 1

    # Link constraints C4, C5, C6, C7
    all_links = set(link_load.keys())

    for p in selected_pairs:
        for opt in feasible[p]:
            all_links.update(paths[p][opt]["links"])

    for l in all_links:
        current_load = link_load.get(l, 0.0)

        added_load = []
        used_count = []

        for p in selected_pairs:
            d = demand.get(p, DEFAULT_DEMAND)

            for opt in feasible[p]:
                if l in paths[p][opt]["links"]:
                    added_load.append(d * y[p, opt])
                    used_count.append(y[p, opt])

        final_load = current_load + pulp.lpSum(added_load)

        # C4/C5/C6: soft threshold/capacity
        model += final_load <= THETA * CAPACITY_MBPS + overload.get(
            l, pulp.LpVariable(f"overload_extra_{len(overload)}", lowBound=0)
        )

        # C7: overlap soft constraint
        if used_count:
            model += pulp.lpSum(used_count) <= 1 + overlap.get(
                l, pulp.LpVariable(f"overlap_extra_{len(overlap)}", lowBound=0)
            )

    # Objective: minimize overload + overlap + hop count + current load usage
    obj = []

    for p in selected_pairs:
        for opt in feasible[p]:
            info = paths[p][opt]
            hop_cost = info["hops"]
            load_cost = sum(link_load.get(l, 0.0) for l in info["links"])

            obj.append((0.30 * hop_cost + 1.00 * load_cost) * y[p, opt])

    obj += [100.0 * v for v in overload.values()]
    obj += [10.0 * v for v in overlap.values()]

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

    for (a, b), opt in assignment.items():
        hosts_arg.append(f"{a},{b}")
        opts_arg.append(str(opt))
        selected_for_history.append((a, b, opt))

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


if __name__ == "__main__":
    # Example only. Replace with selected route pairs from your decision ILP.
    run_route_ilp([
        ("h1", "h30"),
        ("h1", "h35"),
    ])