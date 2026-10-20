import csv
import time

ROUTE_OVERLAP_FILE = "onos_active_flow_route_overlap_v3.csv"
_PREV_ROUTE_BYTES = {}
_PREV_ROUTE_TIME = {}
_LAST_ROUTE_DEMAND = {}


def pair_key(a, b):
    # Match the lexicographic host-pair keys in the new path_selector.
    return tuple(sorted((str(a), str(b))))


def dpid_to_switch(x):
    x = str(x).strip()

    if x.startswith("of:"):
        return f"s{int(x[3:].split('/')[0].split(':')[0], 16)}"

    return x.split("/")[0].split(":")[0]


def normalize_link_id(x):
    x = str(x).strip()

    if "->" not in x:
        return x

    a, b = map(str.strip, x.split("->", 1))
    return tuple(sorted((dpid_to_switch(a), dpid_to_switch(b))))


def host_pair_from_flow_name(flow):
    try:
        a, b = map(str.strip, str(flow or "").split("->", 1))

        if a.startswith("h") and b.startswith("h"):
            return pair_key(a, b)

    except Exception:
        pass

    return None


def parse_route_link_set(row):
    text = (
        row.get("active_route_link_ids")
        or row.get("active_route_links")
        or ""
    )

    return {
        normalize_link_id(x)
        for x in str(text).split(";")
        if "->" in x
    }


def load_route_observations_from_v3():
    global _PREV_ROUTE_BYTES, _PREV_ROUTE_TIME, _LAST_ROUTE_DEMAND

    demands, observed = {}, {}

    try:
        with open(ROUTE_OVERLAP_FILE, newline="") as f:
            rows = [
                r for r in csv.DictReader(f)
                if r.get("timestamp")
            ]
    except Exception as e:
        print(f"[WARN] {ROUTE_OVERLAP_FILE}: {e}")
        return demands, observed

    if not rows:
        return demands, observed

    latest = max(r["timestamp"] for r in rows)

    try:
        now = time.mktime(
            time.strptime(latest, "%Y-%m-%d %H:%M:%S")
        )
    except Exception:
        now = time.time()

    for row in (r for r in rows if r["timestamp"] == latest):
        pair = host_pair_from_flow_name(row.get("flow"))

        if not pair:
            continue

        links = parse_route_link_set(row)

        if links:
            observed[pair] = links

        measured = None

        for column in ("route_demand_mbps", "demand_mbps"):
            try:
                if str(row.get(column, "")).strip():
                    measured = float(row[column])
                    break
            except ValueError:
                pass

        if measured is None:
            try:
                current_bytes = float(row.get("bytes", 0) or 0)
            except ValueError:
                current_bytes = 0.0

            previous_bytes = _PREV_ROUTE_BYTES.get(pair)
            previous_time = _PREV_ROUTE_TIME.get(pair)

            if (
                previous_bytes is not None
                and previous_time is not None
                and now > previous_time
            ):
                measured = (
                    max(0.0, current_bytes - previous_bytes)
                    * 8
                    / ((now - previous_time) * 1_000_000)
                )

            _PREV_ROUTE_BYTES[pair] = current_bytes
            _PREV_ROUTE_TIME[pair] = now

        if measured is None:
            measured = _LAST_ROUTE_DEMAND.get(pair)

        if measured is not None and measured > 0:
            demands[pair] = max(
                demands.get(pair, 0.0),
                measured,
            )
            _LAST_ROUTE_DEMAND[pair] = demands[pair]

    return demands, observed
