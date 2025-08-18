#!/usr/bin/env python3
import os
import time
import subprocess
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import yaml
import argparse
import pandas as pd
import matplotlib.pyplot as plt
import plotly.graph_objects as go
import plotly.express as px
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint
import psutil
import threading
import signal
import sys

# Load config from config.yaml
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
with open(CONFIG_PATH, "r") as f:
    config = yaml.safe_load(f)

IDLE_THRESHOLD = config.get("idle_threshold", 300)
SCAN_INTERVAL = config.get("scan_interval", 3)
LOG_DIR = os.path.expanduser(config.get("log_dir", "~/Desktop/notes/time_log"))
MONITOR_PATH = os.path.expanduser(config.get("monitor_path", "~/developement"))

# STATE
active_sessions = {}  # {repo_path: (start, last_active)}
accumulated_time = {}  # {repo_path: total_seconds_since_last_commit}
last_commits = {}  # {repo_path: last_commit_hash}

os.makedirs(LOG_DIR, exist_ok=True)

console = Console()


def print_debug(msg):
    console.print(f"[bold cyan][DEBUG][/bold cyan] {msg}")


def print_status(msg):
    console.print(f"[bold green][STATUS][/bold green] {msg}")


def print_log(msg):
    console.print(f"[bold yellow][LOGGED][/bold yellow] {msg}")


class ChangeHandler(FileSystemEventHandler):
    def on_modified(self, event):
        print_debug(f"File change detected: {event.src_path}")
        repo_path = get_repo_root(event.src_path)
        if not repo_path:
            print_debug(f"Not in a git repo: {event.src_path}")
            return
        print_debug(f"Git repo found: {repo_path}")
        now = time.time()
        start, last = active_sessions.get(repo_path, (None, None))
        if start is None:
            active_sessions[repo_path] = (now, now)
            print_debug(f"Started new session for {os.path.basename(repo_path)}")
        else:
            active_sessions[repo_path] = (start, now)
            print_debug(f"Updated session for {os.path.basename(repo_path)}")


def get_repo_root(path):
    """Return git repo root path if inside a repo, else None."""
    try:
        # If path is a file, use its directory
        if os.path.isfile(path):
            path = os.path.dirname(path)

        repo_root = (
            subprocess.check_output(
                ["git", "-C", path, "rev-parse", "--show-toplevel"],
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
        return repo_root
    except subprocess.CalledProcessError:
        return None


def get_last_commit_info(repo_path):
    """Return commit hash, message, and commit timestamp."""
    commit_hash = (
        subprocess.check_output(["git", "-C", repo_path, "rev-parse", "HEAD"])
        .decode()
        .strip()
    )
    commit_message = (
        subprocess.check_output(["git", "-C", repo_path, "log", "-1", "--pretty=%B"])
        .decode()
        .strip()
    )
    commit_time = (
        subprocess.check_output(["git", "-C", repo_path, "log", "-1", "--pretty=%ci"])
        .decode()
        .strip()
    )
    return commit_hash, commit_message, commit_time


def log_commit(repo_path, duration):
    """Write commit info and working time to daily Markdown file."""
    repo_name = os.path.basename(repo_path)
    commit_hash, commit_message, commit_time = get_last_commit_info(repo_path)
    today_file = os.path.join(LOG_DIR, f"{datetime.now().date()}.md")

    if not os.path.exists(today_file):
        with open(today_file, "w") as f:
            f.write(f"# Git Activity Log - {datetime.now().date()}\n\n")

    with open(today_file, "r") as f:
        content = f.read()

    if f"## {repo_name}" not in content:
        with open(today_file, "a") as f:
            f.write(f"\n## {repo_name}\n")

    with open(today_file, "a") as f:
        f.write(
            f"- **{commit_message}** ({commit_hash[:7]})\n"
            f"  - Time spent: {round(duration/60, 2)} min\n"
            f"  - Commit time: {commit_time}\n"
        )

    print_log(
        f"{repo_name} | {commit_message[:30]} | {round(duration/60, 2)} min -> {today_file}"
    )


def check_idle_sessions():
    """Accumulate time for sessions that are idle."""
    now = time.time()
    for repo_path, (start, last) in list(active_sessions.items()):
        if start and (now - last > IDLE_THRESHOLD):
            # Add last active period to accumulated time
            duration = last - start
            accumulated_time[repo_path] = accumulated_time.get(repo_path, 0) + duration
            active_sessions[repo_path] = (None, None)
            print_debug(
                f"Moved {round(duration/60, 2)} min from active to accumulated for {os.path.basename(repo_path)}"
            )


def check_commits():
    """Detect new commits and log accumulated time."""
    # Check all repos that have either active sessions or accumulated time
    all_repos = set(active_sessions.keys()) | set(accumulated_time.keys())

    for repo_path in all_repos:
        try:
            commit_hash = (
                subprocess.check_output(["git", "-C", repo_path, "rev-parse", "HEAD"])
                .decode()
                .strip()
            )
        except subprocess.CalledProcessError:
            continue

        if repo_path not in last_commits:
            last_commits[repo_path] = commit_hash
            print_debug(f"Initialized commit tracking for {os.path.basename(repo_path)}")
            continue

        if commit_hash != last_commits[repo_path]:
            print_debug(f"New commit detected in {os.path.basename(repo_path)}")

            # Add current active session to accumulated time (if any)
            start, last = active_sessions.get(repo_path, (None, None))
            if start:
                session_duration = last - start
                accumulated_time[repo_path] = (
                    accumulated_time.get(repo_path, 0) + session_duration
                )
                active_sessions[repo_path] = (None, None)
                print_debug(
                    f"Added {round(session_duration/60, 2)} min from active session"
                )

            duration = accumulated_time.get(repo_path, 0)
            print_debug(f"Total accumulated time: {round(duration/60, 2)} min")

            if duration > 0:  # Only log if there was active time
                log_commit(repo_path, duration)
            else:
                print_debug(f"No time accumulated, skipping log")

            accumulated_time[repo_path] = 0
            last_commits[repo_path] = commit_hash


def monitor():
    handler = ChangeHandler()
    observer = Observer()
    observer.schedule(handler, MONITOR_PATH, recursive=True)
    observer.start()
    print_status(f"Logging to {LOG_DIR}")
    print_status("Press Ctrl+C to stop.")
    status_counter = 0
    try:
        while True:
            time.sleep(SCAN_INTERVAL)
            check_idle_sessions()
            check_commits()
            status_counter += 1
            if status_counter >= 20:
                print_status(f"Active sessions: {len([k for k, (s, l) in active_sessions.items() if s])}")
                print_status(f"Accumulated time: {len([k for k, v in accumulated_time.items() if v > 0])}")
                for repo, time_val in accumulated_time.items():
                    if time_val > 0:
                        console.print(f"  - [bold]{os.path.basename(repo)}[/bold]: [yellow]{round(time_val/60, 2)} min[/yellow]")
                status_counter = 0
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

# CLI interface

def main():
    parser = argparse.ArgumentParser(description="Activity Monitor - Track time spent in git repos.")
    subparsers = parser.add_subparsers(dest="command")

    start_parser = subparsers.add_parser("start", help="Start monitoring activity.")
    status_parser = subparsers.add_parser("status", help="Show current status.")
    stop_parser = subparsers.add_parser("stop", help="Stop monitoring (Ctrl+C).")

    args = parser.parse_args()

    if args.command == "start":
        monitor()
    elif args.command == "status":
        print_status(f"Active sessions: {len([k for k, (s, l) in active_sessions.items() if s])}")
        print_status(f"Accumulated time: {len([k for k, v in accumulated_time.items() if v > 0])}")
        for repo, time_val in accumulated_time.items():
            if time_val > 0:
                console.print(f"  - [bold]{os.path.basename(repo)}[/bold]: [yellow]{round(time_val/60, 2)} min[/yellow]")
    elif args.command == "stop":
        print_status("To stop monitoring, press Ctrl+C in the running process.")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
