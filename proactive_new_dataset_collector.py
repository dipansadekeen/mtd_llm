#!/usr/bin/env python3
"""Collect supervised MTD samples from proactive_new_scoring.py.

The collector stores three tabular datasets in one SQLite database:

1. snapshots: one row per complete network decision (the independent sample)
2. host_candidates: one row per eligible host in that snapshot
3. route_candidates: one row per ACTIVE source-destination pair only

The final column of each candidate table is the binary selection label.  Writes
are transactional, so a crash cannot commit only part of a snapshot.

Minimal integration in the existing decision loop
-------------------------------------------------

    from proactive_new_dataset_collector import MTDDatasetCollector

    collector = MTDDatasetCollector(
        db_path="mtd_training_10000.sqlite",
        target_snapshots=10_000,
    )

    action, hosts, routes, details = decide_ilp(...)

    result = collector.record(
        action=action,
        selected_hosts=hosts,
        selected_routes=routes,
        details=details,
        run_id="run_001",
        scenario_id="mixed_load_seed_17",
    )
    print(result)

    if result["complete"]:
        collector.export_csv("mtd_training_csv")
        # Stop the data-collection experiment cleanly here if desired.

The existing build_route_candidates() already filters by active_pairs.  Thus,
details["route_candidates"] contains only active route pairs and this collector
does not expand the route universe to all 780 possible host pairs.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ACTION_TO_ID = {
    "no_mtd": 0,
    "do_nothing": 0,
    "ip_shuffle": 1,
    "ip": 1,
    "route_mutation": 2,
    "rrm": 2,
}


SNAPSHOT_COLUMNS = (
    "snapshot_id",
    "run_id",
    "scenario_id",
    "decision_index",
    "decision_timestamp_utc",
    "decision_solver_time_s",
    "action_name",
    "action_label",
    "n_ip_candidates",
    "n_active_route_candidates",
    "n_selected_hosts",
    "n_selected_routes",
    "rule_control_alpha",
    "rule_observability_required",
    "rule_ip_operation_allowed",
    "rule_route_operation_allowed",
    "rule_defense_budget",
    "rule_k_ip",
    "rule_k_route",
    "execution_attempted",
    "execution_success",
    "execution_time_s",
    "execution_error",
)


# `selected_ip_label` is deliberately the final column.
HOST_COLUMNS = (
    "snapshot_id",
    "host",
    "rx_pps",
    "tx_pps",
    "rx_mbps",
    "tx_mbps",
    "traffic_risk",
    "monitor_score",
    "ip_exposure",
    "grid_priority",
    "flow_suspicion",
    "short_flow_ratio",
    "unique_sender_mac_count",
    "sender_mac_diversity",
    "unique_flow_count",
    "short_lived_flow_count",
    "ip_capable",
    "latency_ok",
    "frequency_ok",
    "teacher_p_host",
    "teacher_score",
    "teacher_benefit",
    "teacher_cost",
    "selected_ip_label",
)


# `selected_route_label` is deliberately the final column.
ROUTE_COLUMNS = (
    "snapshot_id",
    "src",
    "dst",
    "current_option",
    "route_exposure",
    "link_usage",
    "link_monitor",
    "current_hop_count",
    "hop_penalty",
    "route_grid_priority",
    "max_flow_overlap",
    "overlap_pressure",
    "path",
    "route_capable",
    "latency_ok",
    "frequency_ok",
    "teacher_p_route",
    "teacher_score",
    "teacher_benefit",
    "teacher_cost",
    "teacher_hop_cost",
    "selected_route_label",
)


def _value(row: Mapping[str, Any], key: str, default: Any = 0.0) -> Any:
    value = row.get(key, default)
    return default if value is None else value


def _selected_pair_set(selected_routes: Iterable[Mapping[str, Any]]) -> set[tuple[str, str]]:
    return {
        (str(route.get("src", "")), str(route.get("dst", "")))
        for route in selected_routes
    }


class MTDDatasetCollector:
    """Append complete MTD decisions until a target snapshot count is reached."""

    def __init__(
        self,
        db_path: str | Path = "mtd_training_10000.sqlite",
        target_snapshots: int = 10_000,
    ) -> None:
        if target_snapshots <= 0:
            raise ValueError("target_snapshots must be positive")

        self.db_path = Path(db_path)
        self.target_snapshots = int(target_snapshots)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_database()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30.0)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    def _initialize_database(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS snapshots (
                    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    decision_index INTEGER,
                    decision_timestamp_utc TEXT NOT NULL,
                    decision_solver_time_s REAL,
                    action_name TEXT NOT NULL,
                    action_label INTEGER NOT NULL CHECK(action_label IN (0, 1, 2)),
                    n_ip_candidates INTEGER NOT NULL,
                    n_active_route_candidates INTEGER NOT NULL,
                    n_selected_hosts INTEGER NOT NULL,
                    n_selected_routes INTEGER NOT NULL,
                    rule_control_alpha REAL NOT NULL DEFAULT 0.5,
                    rule_observability_required INTEGER NOT NULL DEFAULT 1,
                    rule_ip_operation_allowed INTEGER NOT NULL DEFAULT 1,
                    rule_route_operation_allowed INTEGER NOT NULL DEFAULT 1,
                    rule_defense_budget REAL NOT NULL DEFAULT 0.5,
                    rule_k_ip INTEGER NOT NULL DEFAULT 10,
                    rule_k_route INTEGER NOT NULL DEFAULT 10,
                    execution_attempted INTEGER NOT NULL DEFAULT 0,
                    execution_success INTEGER NOT NULL DEFAULT 1,
                    execution_time_s REAL,
                    execution_error TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS host_candidates (
                    snapshot_id INTEGER NOT NULL,
                    host TEXT NOT NULL,
                    rx_pps REAL,
                    tx_pps REAL,
                    rx_mbps REAL,
                    tx_mbps REAL,
                    traffic_risk REAL,
                    monitor_score REAL,
                    ip_exposure REAL,
                    grid_priority REAL,
                    flow_suspicion REAL,
                    short_flow_ratio REAL,
                    unique_sender_mac_count REAL,
                    sender_mac_diversity REAL,
                    unique_flow_count REAL,
                    short_lived_flow_count REAL,
                    ip_capable INTEGER NOT NULL DEFAULT 1,
                    latency_ok INTEGER NOT NULL DEFAULT 1,
                    frequency_ok INTEGER NOT NULL DEFAULT 1,
                    teacher_p_host REAL,
                    teacher_score REAL,
                    teacher_benefit REAL,
                    teacher_cost REAL,
                    selected_ip_label INTEGER NOT NULL CHECK(selected_ip_label IN (0, 1)),
                    PRIMARY KEY(snapshot_id, host),
                    FOREIGN KEY(snapshot_id) REFERENCES snapshots(snapshot_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS route_candidates (
                    snapshot_id INTEGER NOT NULL,
                    src TEXT NOT NULL,
                    dst TEXT NOT NULL,
                    current_option INTEGER,
                    route_exposure REAL,
                    link_usage REAL,
                    link_monitor REAL,
                    current_hop_count REAL,
                    hop_penalty REAL,
                    route_grid_priority REAL,
                    max_flow_overlap REAL,
                    overlap_pressure REAL,
                    path TEXT,
                    route_capable INTEGER NOT NULL DEFAULT 1,
                    latency_ok INTEGER NOT NULL DEFAULT 1,
                    frequency_ok INTEGER NOT NULL DEFAULT 1,
                    teacher_p_route REAL,
                    teacher_score REAL,
                    teacher_benefit REAL,
                    teacher_cost REAL,
                    teacher_hop_cost REAL,
                    selected_route_label INTEGER NOT NULL CHECK(selected_route_label IN (0, 1)),
                    PRIMARY KEY(snapshot_id, src, dst),
                    FOREIGN KEY(snapshot_id) REFERENCES snapshots(snapshot_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_snapshots_action
                    ON snapshots(action_label);
                CREATE INDEX IF NOT EXISTS idx_hosts_label
                    ON host_candidates(selected_ip_label);
                CREATE INDEX IF NOT EXISTS idx_routes_label
                    ON route_candidates(selected_route_label);
                """
            )
            # Allow a database created by an earlier prototype version to resume.
            existing_snapshot_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(snapshots)")
            }
            migration_columns = {
                "execution_attempted": "INTEGER NOT NULL DEFAULT 0",
                "execution_success": "INTEGER NOT NULL DEFAULT 1",
                "execution_time_s": "REAL",
                "execution_error": "TEXT NOT NULL DEFAULT ''",
            }
            for column, declaration in migration_columns.items():
                if column not in existing_snapshot_columns:
                    connection.execute(
                        f"ALTER TABLE snapshots ADD COLUMN {column} {declaration}"
                    )
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
                ("target_snapshots", str(self.target_snapshots)),
            )

    @property
    def snapshot_count(self) -> int:
        with self._connect() as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM snapshots WHERE execution_success = 1"
                ).fetchone()[0]
            )

    @property
    def complete(self) -> bool:
        return self.snapshot_count >= self.target_snapshots

    def status(self) -> dict[str, Any]:
        with self._connect() as connection:
            logged_snapshots = int(
                connection.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
            )
            snapshots = int(
                connection.execute(
                    "SELECT COUNT(*) FROM snapshots WHERE execution_success = 1"
                ).fetchone()[0]
            )
            hosts = int(connection.execute("SELECT COUNT(*) FROM host_candidates").fetchone()[0])
            routes = int(connection.execute("SELECT COUNT(*) FROM route_candidates").fetchone()[0])
            action_counts = {
                int(label): int(count)
                for label, count in connection.execute(
                    "SELECT action_label, COUNT(*) FROM snapshots "
                    "WHERE execution_success = 1 GROUP BY action_label"
                )
            }

        return {
            "database": str(self.db_path),
            "snapshots": snapshots,
            "logged_snapshots": logged_snapshots,
            "failed_execution_snapshots": logged_snapshots - snapshots,
            "target_snapshots": self.target_snapshots,
            "remaining": max(0, self.target_snapshots - snapshots),
            "host_candidate_rows": hosts,
            "active_route_candidate_rows": routes,
            "action_counts": {
                "no_mtd": action_counts.get(0, 0),
                "ip_shuffle": action_counts.get(1, 0),
                "route_mutation": action_counts.get(2, 0),
            },
            "complete": snapshots >= self.target_snapshots,
        }

    def record(
        self,
        *,
        action: str,
        selected_hosts: Sequence[str] | None,
        selected_routes: Sequence[Mapping[str, Any]] | None,
        details: Mapping[str, Any],
        run_id: str,
        scenario_id: str = "unspecified",
        decision_index: int | None = None,
        decision_timestamp_utc: str | None = None,
        rules: Mapping[str, Any] | None = None,
        execution_attempted: bool = False,
        execution_success: bool = True,
        execution_time_s: float | None = None,
        execution_error: str = "",
    ) -> dict[str, Any]:
        """Record one snapshot and every candidate label in one transaction."""

        action_name = str(action).strip().lower()
        if action_name not in ACTION_TO_ID:
            raise ValueError(f"Unknown action {action!r}; valid names: {sorted(ACTION_TO_ID)}")

        ip_candidates = list(details.get("ip_candidates", []))
        route_candidates = list(details.get("route_candidates", []))
        selected_host_set = {str(host) for host in (selected_hosts or [])}
        selected_routes = list(selected_routes or [])
        selected_pairs = _selected_pair_set(selected_routes)

        timestamp = decision_timestamp_utc or datetime.now(timezone.utc).isoformat()
        solver_time = details.get("decision_solver_time_s")
        rules = dict(rules or {})

        with self._connect() as connection:
            current_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM snapshots WHERE execution_success = 1"
                ).fetchone()[0]
            )
            if current_count >= self.target_snapshots:
                return self.status()

            cursor = connection.execute(
                """
                INSERT INTO snapshots (
                    run_id, scenario_id, decision_index, decision_timestamp_utc,
                    decision_solver_time_s, action_name, action_label,
                    n_ip_candidates, n_active_route_candidates,
                    n_selected_hosts, n_selected_routes,
                    rule_control_alpha, rule_observability_required,
                    rule_ip_operation_allowed, rule_route_operation_allowed,
                    rule_defense_budget, rule_k_ip, rule_k_route,
                    execution_attempted, execution_success,
                    execution_time_s, execution_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(run_id),
                    str(scenario_id),
                    decision_index,
                    timestamp,
                    solver_time,
                    action_name,
                    ACTION_TO_ID[action_name],
                    len(ip_candidates),
                    len(route_candidates),
                    len(selected_host_set),
                    len(selected_pairs),
                    float(rules.get("control_alpha", 0.5)),
                    int(bool(rules.get("observability_required", True))),
                    int(bool(rules.get("ip_operation_allowed", True))),
                    int(bool(rules.get("route_operation_allowed", True))),
                    float(rules.get("defense_budget", 0.50)),
                    int(rules.get("k_ip", 10)),
                    int(rules.get("k_route", 10)),
                    int(bool(execution_attempted)),
                    int(bool(execution_success)),
                    execution_time_s,
                    str(execution_error or "")[:1000],
                ),
            )
            snapshot_id = int(cursor.lastrowid)

            host_rows = []
            for candidate in ip_candidates:
                host = str(candidate["host"])
                host_rows.append(
                    (
                        snapshot_id,
                        host,
                        _value(candidate, "rx_pps"),
                        _value(candidate, "tx_pps"),
                        _value(candidate, "rx_mbps"),
                        _value(candidate, "tx_mbps"),
                        _value(candidate, "traffic_risk"),
                        _value(candidate, "monitor_score"),
                        _value(candidate, "ip_exposure"),
                        _value(candidate, "grid_priority"),
                        _value(candidate, "flow_suspicion"),
                        _value(candidate, "short_flow_ratio"),
                        _value(candidate, "unique_sender_mac_count"),
                        _value(candidate, "sender_mac_diversity"),
                        _value(candidate, "unique_flow_count"),
                        _value(candidate, "short_lived_flow_count"),
                        int(bool(_value(candidate, "ip_capable", True))),
                        int(bool(_value(candidate, "latency_ok", True))),
                        int(bool(_value(candidate, "frequency_ok", True))),
                        _value(candidate, "p_host"),
                        _value(candidate, "score"),
                        _value(candidate, "benefit"),
                        _value(candidate, "cost"),
                        int(host in selected_host_set),
                    )
                )

            connection.executemany(
                f"INSERT INTO host_candidates ({','.join(HOST_COLUMNS)}) "
                f"VALUES ({','.join('?' for _ in HOST_COLUMNS)})",
                host_rows,
            )

            route_rows = []
            for candidate in route_candidates:
                src = str(candidate["src"])
                dst = str(candidate["dst"])
                route_rows.append(
                    (
                        snapshot_id,
                        src,
                        dst,
                        _value(candidate, "current_option", 0),
                        _value(candidate, "route_exposure"),
                        _value(candidate, "link_usage"),
                        _value(candidate, "link_monitor"),
                        _value(candidate, "current_hop_count"),
                        _value(candidate, "hop_penalty"),
                        _value(candidate, "route_grid_priority"),
                        _value(candidate, "max_flow_overlap"),
                        _value(candidate, "overlap_pressure"),
                        str(_value(candidate, "path", "")),
                        int(bool(_value(candidate, "route_capable", True))),
                        int(bool(_value(candidate, "latency_ok", True))),
                        int(bool(_value(candidate, "frequency_ok", True))),
                        _value(candidate, "p_route"),
                        _value(candidate, "score"),
                        _value(candidate, "benefit"),
                        _value(candidate, "cost"),
                        _value(candidate, "hop_cost"),
                        int((src, dst) in selected_pairs),
                    )
                )

            connection.executemany(
                f"INSERT INTO route_candidates ({','.join(ROUTE_COLUMNS)}) "
                f"VALUES ({','.join('?' for _ in ROUTE_COLUMNS)})",
                route_rows,
            )

        count = current_count + int(bool(execution_success))
        return {
            "snapshot_id": snapshot_id,
            "snapshots": count,
            "target_snapshots": self.target_snapshots,
            "remaining": max(0, self.target_snapshots - count),
            "complete": count >= self.target_snapshots,
        }

    def export_csv(self, output_directory: str | Path = "mtd_training_csv") -> list[str]:
        """Export all three tables to ordinary CSV files for inspection/training."""

        output_directory = Path(output_directory)
        output_directory.mkdir(parents=True, exist_ok=True)
        exported: list[str] = []

        table_columns = {
            "snapshots": SNAPSHOT_COLUMNS,
            "host_candidates": HOST_COLUMNS,
            "route_candidates": ROUTE_COLUMNS,
        }

        with self._connect() as connection:
            for table, columns in table_columns.items():
                path = output_directory / f"{table}.csv"
                with path.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.writer(handle)
                    writer.writerow(columns)
                    query = f"SELECT {','.join(columns)} FROM {table} ORDER BY snapshot_id"
                    writer.writerows(connection.execute(query))
                exported.append(str(path))

        return exported


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect or export an MTD dataset")
    parser.add_argument("command", choices=("status", "export"))
    parser.add_argument("--db", default="mtd_training_10000.sqlite")
    parser.add_argument("--target", type=int, default=10_000)
    parser.add_argument("--output-dir", default="mtd_training_csv")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    collector = MTDDatasetCollector(args.db, args.target)
    if args.command == "status":
        print(json.dumps(collector.status(), indent=2))
    else:
        print(json.dumps({"exported": collector.export_csv(args.output_dir)}, indent=2))


if __name__ == "__main__":
    main()