#!/usr/bin/env python3
"""Run MTD decision -> execution -> logging until 10,000 valid snapshots.

Place this file and proactive_new_dataset_collector.py beside
proactive_new_scoring.py,
then run:

    python3 proactive_new_data_collection.py \
        --module proactive_new_scoring \
        --target 10000 \
        --interval 30 \
        --run-id experiment_001 \
        --scenario-id mixed_proactive

The database is updated after every execution.  At the target, it exports:

    mtd_training_csv/snapshots.csv
    mtd_training_csv/host_candidates.csv
    mtd_training_csv/route_candidates.csv

Candidate measurements come from the pre-execution decision snapshot.  The
execution result and latency are stored with that snapshot.  Failed executions
are retained for auditing but do not count toward the 10,000 valid samples and
are excluded by the companion training prototype.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping, Sequence
import traceback
from proactive_new_dataset_collector import MTDDatasetCollector


NO_ACTION_NAMES = {"no_mtd", "do_nothing", "no_action"}
IP_ACTION_NAMES = {"ip_shuffle", "ip"}
ROUTE_ACTION_NAMES = {"route_mutation", "rrm"}


def load_strategy(module_name: str) -> ModuleType:
    strategy = importlib.import_module(module_name)
    required = ("decide_ilp", "run_ip_ilp", "run_route_ilp")
    missing = [name for name in required if not hasattr(strategy, name)]
    if missing:
        raise AttributeError(
            f"{module_name} is missing required functions: {', '.join(missing)}"
        )
    return strategy


def execute_selected_defense(
    strategy: ModuleType,
    action: str,
    hosts: Sequence[str],
    routes: Sequence[Mapping[str, Any]],
) -> tuple[bool, bool, float, str]:
    """Execute one selected action and return audit fields.

    Returns: attempted, success, elapsed_seconds, error_message
    """

    normalized = str(action).strip().lower()
    attempted = normalized not in NO_ACTION_NAMES
    started = time.perf_counter()

    try:
        if normalized in ROUTE_ACTION_NAMES:
            selected_pairs = [(str(r["src"]), str(r["dst"])) for r in routes]
            strategy.run_route_ilp(selected_pairs)
            if hasattr(strategy, "repeat_ip_history"):
                strategy.repeat_ip_history()

        elif normalized in IP_ACTION_NAMES:
            strategy.run_ip_ilp(list(hosts))
            if hasattr(strategy, "repeat_route_history"):
                strategy.repeat_route_history()

        elif normalized in NO_ACTION_NAMES:
            pass

        else:
            raise ValueError(f"Unsupported solver action: {action!r}")

        return attempted, True, time.perf_counter() - started, ""

    except Exception as exc:
        traceback.print_exc()
        return attempted, False, time.perf_counter() - started, traceback.format_exc()

def current_rules(strategy: ModuleType, control_alpha: float) -> dict[str, Any]:
    """Capture global rule settings used during this decision cycle."""

    return {
        "control_alpha": float(control_alpha),
        "observability_required": True,
        "ip_operation_allowed": True,
        "route_operation_allowed": True,
        "defense_budget": float(getattr(strategy, "DEFENSE_BUDGET", 0.50)),
        "k_ip": int(getattr(strategy, "K_IP", 10)),
        "k_route": int(getattr(strategy, "K_ROUTE", 10)),
    }


def run_collection(args: argparse.Namespace) -> int:
    strategy = load_strategy(args.module)
    collector = MTDDatasetCollector(args.db, target_snapshots=args.target)
    cycle_index = 0

    print(json.dumps({"starting": collector.status()}, indent=2))

    try:
        while not collector.complete:
            cycle_started = time.perf_counter()
            observed_time = args.start_observation_seconds + cycle_index * args.interval
            timestamp = datetime.now(timezone.utc).isoformat()

            action, hosts, routes, details = strategy.decide_ilp(
                obs_time_seconds=observed_time
            )

            attempted, success, execution_time, error = execute_selected_defense(
                strategy=strategy,
                action=action,
                hosts=hosts,
                routes=routes,
            )

            result = collector.record(
                action=action,
                selected_hosts=hosts,
                selected_routes=routes,
                details=details,
                run_id=args.run_id,
                scenario_id=args.scenario_id,
                decision_index=cycle_index,
                decision_timestamp_utc=timestamp,
                rules=current_rules(strategy, args.control_alpha),
                execution_attempted=attempted,
                execution_success=success,
                execution_time_s=execution_time,
                execution_error=error,
            )

            print(
                json.dumps(
                    {
                        "cycle": cycle_index,
                        "action": action,
                        "selected_hosts": list(hosts),
                        "selected_active_routes": [
                            f"{route['src']}->{route['dst']}" for route in routes
                        ],
                        "execution_success": success,
                        "execution_time_s": round(execution_time, 6),
                        "valid_snapshots": result.get("snapshots"),
                        "remaining": result.get("remaining"),
                        "error": error,
                    }
                ),
                flush=True,
            )

            cycle_index += 1

            if not success and not args.continue_on_execution_error:
                print(
                    "Execution failed; the failed snapshot was logged. "
                    "Stopping because --continue-on-execution-error was not supplied.",
                    file=sys.stderr,
                )
                return 2

            if collector.complete:
                break

            elapsed = time.perf_counter() - cycle_started
            time.sleep(max(0.0, args.interval - elapsed))

    except KeyboardInterrupt:
        print("\nCollection interrupted. The committed database can be resumed.")
        print(json.dumps(collector.status(), indent=2))
        return 130

    exported = collector.export_csv(args.export_dir)
    print(json.dumps({"complete": collector.status(), "exported": exported}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect MTD decisions, executions, features, and labels"
    )
    parser.add_argument("--module", default="proactive_new_scoring")
    parser.add_argument("--db", default="mtd_training_10000.sqlite")
    parser.add_argument("--export-dir", default="mtd_training_csv")
    parser.add_argument("--target", type=int, default=10_000)
    parser.add_argument("--interval", type=float, default=30.0)
    parser.add_argument("--start-observation-seconds", type=float, default=0.0)
    parser.add_argument(
        "--run-id",
        default=f"run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
    )
    parser.add_argument("--scenario-id", default="unspecified")
    parser.add_argument("--control-alpha", type=float, default=0.25)
    parser.add_argument("--continue-on-execution-error", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.interval < 0:
        raise ValueError("--interval cannot be negative")
    if not 0.0 <= args.control_alpha <= 1.0:
        raise ValueError("--control-alpha must be between 0 and 1")
    raise SystemExit(run_collection(args))


if __name__ == "__main__":
    main()