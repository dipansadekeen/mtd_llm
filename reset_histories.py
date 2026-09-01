#!/usr/bin/env python3
"""
Reset route/ip history last values and set the shuffle flag.

What it does:
1. Reads route_history.csv and sets the LAST value in every route history to 0.
2. Reads ip_history.csv and sets the LAST value in each host history to the host number:
      h1 -> 1, h2 -> 2, ..., h40 -> 40
3. Creates .bak backup files before overwriting.
4. Runs the same effect as:
      echo 1 | sudo tee /tmp/shuffle_flag.txt

Usage:
    python3 reset_histories.py

Optional:
    python3 reset_histories.py --route route_history.csv --ip ip_history.csv
    python3 reset_histories.py --skip-flag
"""

import argparse
import csv
import re
import shutil
import subprocess
from pathlib import Path


HOST_RE = re.compile(r"^h(\d+)$")


def split_history(history_text: str) -> list[str]:
    """Split comma-separated history values while tolerating blanks."""
    parts = [x.strip() for x in str(history_text).split(",") if x.strip() != ""]
    return parts


def join_history(parts: list[str]) -> str:
    return ",".join(str(x) for x in parts)


def backup_file(path: Path) -> Path:
    backup = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, backup)
    return backup


def reset_route_history(route_path: Path) -> int:
    """Set the last value of every route history row to 0."""
    with route_path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    if not fieldnames or "history" not in fieldnames:
        raise ValueError(f"{route_path} must contain a 'history' column")

    changed = 0
    for row in rows:
        parts = split_history(row.get("history", ""))
        if not parts:
            parts = ["0"]
        old_last = parts[-1]
        parts[-1] = "0"
        row["history"] = join_history(parts)
        if old_last != "0":
            changed += 1

    backup = backup_file(route_path)
    with route_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"[route] rows={len(rows)} changed_last_values={changed} backup={backup}")
    return len(rows)


def reset_ip_history(ip_path: Path) -> int:
    """Set the last value of each host history to its host number: h1->1, ..., h40->40."""
    with ip_path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    if not fieldnames or "host" not in fieldnames or "history" not in fieldnames:
        raise ValueError(f"{ip_path} must contain 'host' and 'history' columns")

    changed = 0
    for row in rows:
        host = row.get("host", "").strip()
        match = HOST_RE.match(host)
        if not match:
            raise ValueError(f"Invalid host name {host!r}; expected h1, h2, ..., h40")

        new_last = match.group(1)  # h15 -> "15"
        parts = split_history(row.get("history", ""))
        if not parts:
            parts = [new_last]

        old_last = parts[-1]
        parts[-1] = new_last
        row["history"] = join_history(parts)
        if old_last != new_last:
            changed += 1

    backup = backup_file(ip_path)
    with ip_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"[ip] rows={len(rows)} changed_last_values={changed} backup={backup}")
    return len(rows)


def set_shuffle_flag() -> None:
    """Equivalent to: echo 1 | sudo tee /tmp/shuffle_flag.txt"""
    subprocess.run(
        ["sudo", "tee", "/tmp/shuffle_flag.txt"],
        input="1\n",
        text=True,
        check=True,
    )
    print("[flag] wrote 1 to /tmp/shuffle_flag.txt")

def delete_path_match_log() -> None:
    """Delete /tmp/path_match_log.txt if it exists."""
    log_path = Path("/tmp/path_match_log.txt")

    try:
        log_path.unlink()
        print(f"[log] deleted {log_path}")
    except FileNotFoundError:
        print(f"[log] {log_path} does not exist; nothing to delete")
    except PermissionError:
        subprocess.run(["sudo", "rm", "-f", str(log_path)], check=True)
        print(f"[log] deleted {log_path} using sudo")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--route", default="route_history.csv", help="Path to route_history.csv")
    parser.add_argument("--ip", default="ip_history.csv", help="Path to ip_history.csv")
    parser.add_argument("--skip-flag", action="store_true", help="Do not run sudo tee shuffle flag command")
    args = parser.parse_args()

    route_path = Path(args.route)
    ip_path = Path(args.ip)

    if not route_path.exists():
        raise FileNotFoundError(f"Missing route history file: {route_path}")
    if not ip_path.exists():
        raise FileNotFoundError(f"Missing IP history file: {ip_path}")

    reset_route_history(route_path)
    reset_ip_history(ip_path)
    delete_path_match_log()
    if not args.skip_flag:
        set_shuffle_flag()

    print("[done] histories reset successfully")


if __name__ == "__main__":
    main()