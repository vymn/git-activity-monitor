#!/usr/bin/env python3
"""
Enhanced Activity Monitor - Advanced Git Repository Time Tracking
Features:
- SQLite database for persistent storage
- Rich CLI with colored output and tables
- Analytics and visualizations
- Export capabilities (JSON, CSV, PDF reports)
- Real-time monitoring with system resources
- Productivity insights and statistics
"""

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
from rich.layout import Layout
from rich.live import Live
import psutil
import threading
import signal
import sys

# Optional PDF dependencies - import with error handling
PDF_AVAILABLE = False
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import (
        SimpleDocTemplate,
        Table as RLTable,
        TableStyle,
        Paragraph,
        Spacer,
        Image,
        PageBreak,
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.graphics.shapes import Drawing
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.charts.linecharts import HorizontalLineChart
    from reportlab.graphics.charts.piecharts import Pie
    from reportlab.lib.colors import HexColor

    PDF_AVAILABLE = True
except ImportError:
    pass  # PDF functionality will be disabled

from .config import load_config

# Load config using the config module
config = load_config()

IDLE_THRESHOLD = config.get("idle_threshold", 300)
SCAN_INTERVAL = config.get("scan_interval", 3)
LOG_DIR = os.path.expanduser(config.get("log_dir", "~/Desktop/notes/time_log"))
MONITOR_PATH = os.path.expanduser(config.get("monitor_path", "~/developement"))
DB_PATH = os.path.join(LOG_DIR, "activity_monitor_test.db")

console = Console()
VERBOSE = False  # Global verbose flag


def set_verbose(verbose=True):
    """Set global verbose flag."""
    global VERBOSE
    VERBOSE = verbose


def verbose_print(msg, style="dim"):
    """Print verbose messages only if VERBOSE is True."""
    if VERBOSE:
        console.print(f"[{style}][VERBOSE][/{style}] {msg}")


def debug_print(msg):
    """Print debug messages."""
    if VERBOSE:
        console.print(f"[cyan][DEBUG][/cyan] {msg}")


def info_print(msg):
    """Print info messages."""
    console.print(f"[green][INFO][/green] {msg}")


def error_print(msg):
    """Print error messages."""
    console.print(f"[red][ERROR][/red] {msg}")


class DatabaseManager:
    """Manages SQLite database operations for activity tracking."""

    def __init__(self):
        self.init_database()

    def init_database(self):
        """Initialize SQLite database."""
        os.makedirs(LOG_DIR, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Main activity sessions table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS activity_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo_path TEXT NOT NULL,
                repo_name TEXT NOT NULL,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                duration_seconds INTEGER,
                commit_hash TEXT,
                commit_message TEXT,
                files_changed INTEGER DEFAULT 0,
                lines_added INTEGER DEFAULT 0,
                lines_deleted INTEGER DEFAULT 0,
                productivity_score REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Daily statistics table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_stats (
                date TEXT PRIMARY KEY,
                total_time_seconds INTEGER,
                repos_worked_on INTEGER,
                commits_made INTEGER,
                files_changed INTEGER,
                lines_changed INTEGER,
                avg_session_duration REAL,
                productivity_score REAL
            )
        """
        )

        # Goals and targets table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal_type TEXT NOT NULL,
                target_value INTEGER,
                current_value INTEGER DEFAULT 0,
                date_set TEXT,
                deadline TEXT,
                completed BOOLEAN DEFAULT FALSE
            )
        """
        )

        conn.commit()
        conn.close()

    def save_session(self, session_data):
        """Save a completed session to database."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO activity_sessions 
            (repo_path, repo_name, start_time, end_time, duration_seconds, 
             commit_hash, commit_message, files_changed, lines_added, lines_deleted, productivity_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            session_data,
        )

        conn.commit()
        conn.close()

    def get_sessions(self, days=7):
        """Get recent sessions."""
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query(
            """
            SELECT * FROM activity_sessions 
            WHERE created_at >= datetime('now', '-{} days')
            ORDER BY created_at DESC
        """.format(
                days
            ),
            conn,
        )
        conn.close()
        return df

    def get_daily_stats(self, days=30):
        """Get daily statistics."""
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query(
            """
            SELECT 
                DATE(created_at) as date,
                SUM(duration_seconds) as total_time,
                COUNT(DISTINCT repo_path) as repos_count,
                COUNT(*) as sessions_count,
                SUM(files_changed) as files_changed,
                SUM(lines_added + lines_deleted) as lines_changed,
                AVG(duration_seconds) as avg_session_duration,
                AVG(productivity_score) as avg_productivity
            FROM activity_sessions 
            WHERE created_at >= datetime('now', '-{} days')
            GROUP BY DATE(created_at)
            ORDER BY date DESC
        """.format(
                days
            ),
            conn,
        )
        conn.close()
        return df


class EnhancedActivityTracker:
    """Enhanced activity tracker with advanced features."""

    def __init__(self):
        self.db = DatabaseManager()
        self.active_sessions = {}
        self.accumulated_time = {}
        self.last_commits = {}
        self.file_changes = {}  # Will store sets of changed file paths
        self.running = False
        self.observer = None

    def calculate_productivity_score(self, duration, files_changed, lines_changed):
        """Calculate a productivity score based on various metrics."""
        if duration == 0:
            return 0.0

        # Base score from time spent
        base_score = min(duration / 3600, 1.0) * 40  # Max 40 points for time

        # File activity score
        file_score = min(files_changed * 5, 30)  # Max 30 points for files

        # Lines changed score
        lines_score = min(lines_changed / 10, 30)  # Max 30 points for lines

        return base_score + file_score + lines_score

    def get_git_stats(self, repo_path):
        """Get detailed git statistics from both staged and unstaged changes."""
        try:
            lines_added = lines_deleted = 0
            files_changed = 0

            # Get stats from both unstaged and staged changes
            for cmd_name, cmd in [
                ("unstaged", ["git", "-C", repo_path, "diff", "--stat"]),
                ("staged", ["git", "-C", repo_path, "diff", "--cached", "--stat"]),
            ]:
                result = subprocess.run(cmd, capture_output=True, text=True)

                if result.returncode == 0 and result.stdout.strip():
                    lines = result.stdout.strip().split("\n")
                    verbose_print(f"Git {cmd_name} diff output:")
                    for line in lines:
                        verbose_print(f"  {line}")

                    # Parse the summary line (last line if multiple files)
                    summary_found = False
                    for line in lines:
                        if "file changed" in line or "files changed" in line:
                            # Format: "X file(s) changed, Y insertion(s)(+), Z deletion(s)(-)"
                            parts = line.split(",")
                            verbose_print(f"Parsing summary line: {line}")
                            summary_found = True

                            # Extract files changed
                            if "file" in parts[0]:
                                try:
                                    file_count = int(parts[0].split()[0])
                                    files_changed += file_count
                                    verbose_print(f"Found {file_count} files changed")
                                except (ValueError, IndexError) as e:
                                    verbose_print(f"Error parsing file count: {e}")

                            # Extract insertions
                            for part in parts:
                                if "insertion" in part:
                                    try:
                                        added = int(part.strip().split()[0])
                                        lines_added += added
                                        verbose_print(f"Found {added} lines added")
                                    except (ValueError, IndexError) as e:
                                        verbose_print(f"Error parsing insertions: {e}")
                                elif "deletion" in part:
                                    try:
                                        deleted = int(part.strip().split()[0])
                                        lines_deleted += deleted
                                        verbose_print(f"Found {deleted} lines deleted")
                                    except (ValueError, IndexError) as e:
                                        verbose_print(f"Error parsing deletions: {e}")

                    # Only count individual files if no summary was found
                    if not summary_found:
                        for line in lines:
                            if " | " in line and (
                                "++" in line or "--" in line or "+-" in line
                            ):
                                # Individual file line format: "filename | 5 +++--"
                                files_changed += 1
                                verbose_print(f"Found individual file change: {line}")

            verbose_print(
                f"Final git stats: {lines_added} added, {lines_deleted} deleted, {files_changed} files"
            )
            return lines_added, lines_deleted, files_changed
        except Exception as e:
            verbose_print(f"Error getting git stats: {e}")
            return 0, 0, 0

    def start_monitoring(self):
        """Start the file system monitoring."""
        self.running = True
        handler = EnhancedChangeHandler(self)
        self.observer = Observer()
        self.observer.schedule(handler, MONITOR_PATH, recursive=True)
        self.observer.start()

        info_print(f"🚀 Activity Monitor Started")
        verbose_print(f"Monitoring directory: {MONITOR_PATH}")
        verbose_print(f"Database location: {DB_PATH}")
        verbose_print(f"Idle threshold: {IDLE_THRESHOLD} seconds")
        verbose_print(f"Scan interval: {SCAN_INTERVAL} seconds")

        console.print(
            Panel.fit(
                f"[bold green]🚀 Activity Monitor Started[/bold green]\n"
                f"📁 Monitoring: {MONITOR_PATH}\n"
                f"💾 Database: {DB_PATH}\n"
                f"⏱️  Idle threshold: {IDLE_THRESHOLD}s\n"
                f"🔍 Verbose mode: {'ON' if VERBOSE else 'OFF'}",
                border_style="green",
            )
        )

        # Check if monitoring path exists and contains git repos
        if not os.path.exists(MONITOR_PATH):
            error_print(f"Monitoring path does not exist: {MONITOR_PATH}")
            return None

        # Look for git repositories in the monitoring path
        git_repos = []
        try:
            for root, dirs, files in os.walk(MONITOR_PATH):
                if ".git" in dirs:
                    git_repos.append(root)
        except Exception as e:
            error_print(f"Error scanning for git repos: {e}")

        if git_repos:
            info_print(f"Found {len(git_repos)} Git repositories:")
            for repo in git_repos[:5]:  # Show first 5
                verbose_print(f"  - {os.path.basename(repo)} ({repo})")
            if len(git_repos) > 5:
                verbose_print(f"  ... and {len(git_repos) - 5} more repositories")
        else:
            console.print(
                "[yellow]⚠️  No Git repositories found in monitoring path[/yellow]"
            )
            verbose_print(
                "Make sure you have Git repositories in the monitored directory"
            )

        # Start the monitoring loop in a separate thread
        monitor_thread = threading.Thread(target=self._monitor_loop)
        monitor_thread.daemon = True
        monitor_thread.start()

        return self.observer

    def _monitor_loop(self):
        """Main monitoring loop."""
        status_counter = 0

        try:
            while self.running:
                time.sleep(SCAN_INTERVAL)
                self._check_idle_sessions()
                self._check_commits()

                status_counter += 1
                if status_counter >= 20:  # Every ~1 minute
                    self._show_live_status()
                    status_counter = 0

        except KeyboardInterrupt:
            self.stop_monitoring()

    def _check_idle_sessions(self):
        """Check for idle sessions and accumulate time."""
        now = time.time()
        verbose_print(f"Checking for idle sessions (threshold: {IDLE_THRESHOLD}s)")

        idle_count = 0
        for repo_path, (start, last) in list(self.active_sessions.items()):
            if start and (now - last > IDLE_THRESHOLD):
                duration = last - start
                self.accumulated_time[repo_path] = (
                    self.accumulated_time.get(repo_path, 0) + duration
                )
                self.active_sessions[repo_path] = (None, None)

                repo_name = os.path.basename(repo_path)
                info_print(f"⏸️  Session paused: {repo_name} ({duration/60:.1f}min)")
                verbose_print(
                    f"Moved to accumulated time: {self.accumulated_time[repo_path]/60:.1f}min total"
                )
                idle_count += 1

        if idle_count == 0 and len(self.active_sessions) > 0:
            verbose_print("No idle sessions found")

    def _check_commits(self):
        """Check for new commits and save completed sessions."""
        all_repos = set(self.active_sessions.keys()) | set(self.accumulated_time.keys())
        verbose_print(f"Checking commits in {len(all_repos)} repositories")

        for repo_path in all_repos:
            try:
                commit_hash = (
                    subprocess.check_output(
                        ["git", "-C", repo_path, "rev-parse", "HEAD"]
                    )
                    .decode()
                    .strip()
                )
                verbose_print(
                    f"Current commit in {os.path.basename(repo_path)}: {commit_hash[:7]}"
                )
            except subprocess.CalledProcessError as e:
                verbose_print(f"Failed to get commit hash for {repo_path}: {e}")
                continue

            if repo_path not in self.last_commits:
                self.last_commits[repo_path] = commit_hash
                debug_print(
                    f"Initialized commit tracking for {os.path.basename(repo_path)}"
                )
                continue

            if commit_hash != self.last_commits[repo_path]:
                info_print(f"🔄 New commit detected in {os.path.basename(repo_path)}")
                verbose_print(f"Old commit: {self.last_commits[repo_path][:7]}")
                verbose_print(f"New commit: {commit_hash[:7]}")
                self._handle_new_commit(repo_path, commit_hash)
            else:
                verbose_print(f"No new commits in {os.path.basename(repo_path)}")

    def _handle_new_commit(self, repo_path, commit_hash):
        """Handle a new commit by saving the session."""
        repo_name = os.path.basename(repo_path)
        verbose_print(f"Processing new commit in {repo_name}")

        # Add current active session to accumulated time
        start, last = self.active_sessions.get(repo_path, (None, None))
        if start:
            session_duration = last - start
            self.accumulated_time[repo_path] = (
                self.accumulated_time.get(repo_path, 0) + session_duration
            )
            self.active_sessions[repo_path] = (None, None)
            debug_print(
                f"Added active session to accumulated: {session_duration/60:.1f}min"
            )

        total_duration = self.accumulated_time.get(repo_path, 0)
        verbose_print(
            f"Total accumulated time for {repo_name}: {total_duration/60:.1f}min"
        )

        if total_duration > 0:
            # Get commit info and git stats
            commit_message = self._get_commit_message(repo_path)
            lines_added, lines_deleted, git_files_changed = self.get_git_stats(
                repo_path
            )

            # Use the larger of file change counter or git stats for files changed
            files_changed = max(
                len(self.file_changes.get(repo_path, set())), git_files_changed
            )

            verbose_print(f"Commit details:")
            verbose_print(f"  - Hash: {commit_hash[:7]}")
            verbose_print(f"  - Message: {commit_message[:50]}...")
            verbose_print(f"  - Files changed: {files_changed}")
            verbose_print(f"  - Lines added: {lines_added}, deleted: {lines_deleted}")

            # Calculate productivity score
            productivity_score = self.calculate_productivity_score(
                total_duration, files_changed, lines_added + lines_deleted
            )

            # Save to database
            session_data = (
                repo_path,
                repo_name,
                datetime.now() - timedelta(seconds=total_duration),
                datetime.now(),
                total_duration,
                commit_hash,
                commit_message,
                files_changed,
                lines_added,
                lines_deleted,
                productivity_score,
            )

            try:
                self.db.save_session(session_data)
                verbose_print("✅ Session saved to database")
            except Exception as e:
                error_print(f"Failed to save session to database: {e}")

            # Save session to Markdown log
            try:
                self.save_session_to_markdown(
                    repo_path, total_duration, (commit_hash, commit_message)
                )
                verbose_print("✅ Session saved to Markdown")
            except Exception as e:
                error_print(f"Failed to save session to Markdown: {e}")

            # Show commit notification
            console.print(
                Panel.fit(
                    f"[bold green]✨ Commit Logged![/bold green]\n"
                    f"📦 {repo_name}\n"
                    f"⏱️  {total_duration/60:.1f} minutes\n"
                    f"📝 {commit_message[:50]}...\n"
                    f"📊 Productivity: {productivity_score:.1f}/100",
                    border_style="green",
                )
            )

            # Reset counters
            self.accumulated_time[repo_path] = 0
            self.file_changes[repo_path] = set()  # Reset to empty set
        else:
            verbose_print("No accumulated time found - session not saved")

        self.last_commits[repo_path] = commit_hash

    def _get_commit_message(self, repo_path):
        """Get the latest commit message."""
        try:
            result = subprocess.check_output(
                ["git", "-C", repo_path, "log", "-1", "--pretty=%B"],
                stderr=subprocess.DEVNULL,
            )
            message = result.decode().strip()
            verbose_print(f"Retrieved commit message: {message[:50]}...")
            return message
        except subprocess.CalledProcessError as e:
            verbose_print(f"Failed to get commit message: {e}")
            return "No commit message available"
        except Exception as e:
            verbose_print(f"Unexpected error getting commit message: {e}")
            return "Error retrieving commit message"

    def _show_live_status(self):
        """Show live status of active sessions."""
        active_count = len([k for k, (s, l) in self.active_sessions.items() if s])
        accumulated_count = len([k for k, v in self.accumulated_time.items() if v > 0])

        if active_count > 0 or accumulated_count > 0:
            table = Table(title="📊 Current Activity Status")
            table.add_column("Repository", style="cyan")
            table.add_column("Status", style="green")
            table.add_column("Time", style="yellow")
            table.add_column("Files Changed", style="magenta")

            # Show active sessions
            for repo_path, (start, last) in self.active_sessions.items():
                if start:
                    duration = time.time() - start
                    files = len(self.file_changes.get(repo_path, set()))
                    table.add_row(
                        os.path.basename(repo_path),
                        "🟢 Active",
                        f"{duration/60:.1f}m",
                        str(files),
                    )

            # Show accumulated time
            for repo_path, duration in self.accumulated_time.items():
                if duration > 0:
                    files = len(self.file_changes.get(repo_path, set()))
                    table.add_row(
                        os.path.basename(repo_path),
                        "🟡 Accumulated",
                        f"{duration/60:.1f}m",
                        str(files),
                    )

            console.print(table)

    def stop_monitoring(self):
        """Stop the monitoring process."""
        self.running = False
        if self.observer:
            self.observer.stop()
            self.observer.join()
        console.print("[red]🛑 Activity Monitor Stopped[/red]")

    def save_session_to_markdown(self, repo_path, duration, commit_info=None):
        """Save session data to daily Markdown file (legacy format + enhanced)."""
        repo_name = os.path.basename(repo_path)
        today_file = os.path.join(LOG_DIR, f"{datetime.now().date()}.md")

        # Create daily file if it doesn't exist
        if not os.path.exists(today_file):
            with open(today_file, "w") as f:
                f.write(f"# Daily Timesheet - {datetime.now().date()}\n\n")
                f.write("## 📋 Task Summary\n\n")
                f.write(
                    "| Time | Task/Project | Repository | Duration | Files | Lines | Productivity | Status |\n"
                )
                f.write(
                    "|------|-------------|------------|----------|-------|-------|--------------|--------|\n\n"
                )

        # Read existing content to check for task sections
        with open(today_file, "r") as f:
            content = f.read()

        # Get session details
        commit_hash, commit_message = (
            commit_info if commit_info else (None, "Work in progress")
        )

        # Extract task name from commit message
        task_name = extract_task_name(commit_message)

        lines_added, lines_deleted, git_files_changed = self.get_git_stats(repo_path)
        # Use the larger of file change counter or git stats for files changed
        files_changed = max(
            len(self.file_changes.get(repo_path, set())), git_files_changed
        )
        total_lines = lines_added + lines_deleted
        productivity_score = self.calculate_productivity_score(
            duration, files_changed, total_lines
        )

        now = datetime.now()
        time_str = now.strftime("%H:%M")
        duration_str = f"{duration/60:.1f}min"
        status = "Committed" if commit_hash else "In Progress"

        # Add to summary table (insert after the table header)
        summary_line = f"| {time_str} | {task_name} | {repo_name} | {duration_str} | {files_changed} | {total_lines} | {productivity_score:.1f}/100 | {status} |\n"

        # Insert summary line after table header
        lines = content.split("\n")
        table_end_idx = -1
        for i, line in enumerate(lines):
            if line.startswith("|------|"):
                table_end_idx = i + 1
                break

        if table_end_idx > 0:
            lines.insert(table_end_idx, summary_line.rstrip())
            with open(today_file, "w") as f:
                f.write("\n".join(lines))

        # Add task section if it doesn't exist
        if f"## {task_name}" not in content:
            with open(today_file, "a") as f:
                f.write(f"\n## 📝 {task_name}\n\n")
                f.write(f"**Repository:** {repo_name}  \n")
                f.write(f"**Total Time:** {duration_str}  \n")
                f.write(f"**Status:** {status}  \n\n")

        # Add detailed entry to task section
        with open(today_file, "a") as f:
            f.write(f"### {now.strftime('%H:%M')} - Work Session ({duration_str})\n\n")

            # Task details box
            f.write(f"**📋 Task:** {task_name}  \n")
            f.write(f"**📁 Repository:** {repo_name}  \n")

            if commit_hash:
                f.write(f"**🔄 Commit:** `{commit_hash[:7]}` - {commit_message}  \n")
            else:
                f.write(f"**💼 Work:** {commit_message}  \n")

            f.write(f"**⏱️ Duration:** {duration_str}  \n")
            f.write(f"**📊 Productivity:** {productivity_score:.1f}/100  \n")
            f.write(f"**📁 Files changed:** {files_changed}  \n")
            f.write(f"**➕ Lines added:** {lines_added}  \n")
            f.write(f"**➖ Lines deleted:** {lines_deleted}  \n")
            f.write(f"**✅ Status:** {status}  \n\n")

            if files_changed > 0:
                # Try to get list of changed files
                try:
                    result = subprocess.run(
                        ["git", "-C", repo_path, "diff", "--name-only"],
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        f.write("**Files modified:**\n")
                        for file_name in result.stdout.strip().split("\n"):
                            if file_name:
                                f.write(f"- `{file_name}`\n")
                        f.write("\n")
                except:
                    pass

            f.write("---\n\n")

        console.print(f"[green]📝 Markdown log updated: {today_file}")

    def generate_markdown_summary(self, period="week"):
        """Generate weekly or monthly Markdown summary reports."""
        if period == "week":
            days = 7
            title = "Weekly"
        elif period == "month":
            days = 30
            title = "Monthly"
        else:
            days = 7
            title = "Weekly"

        # Get data from database
        df = self.db.get_daily_stats(days)
        sessions_df = self.db.get_sessions(days)

        if df.empty:
            console.print(
                f"[yellow]No data available for {title.lower()} summary[/yellow]"
            )
            return

        # Create summary file
        now = datetime.now()
        if period == "week":
            filename = f"weekly_summary_{now.strftime('%Y_W%U')}.md"
        else:
            filename = f"monthly_summary_{now.strftime('%Y_%m')}.md"

        summary_file = os.path.join(LOG_DIR, "summaries", filename)
        os.makedirs(os.path.dirname(summary_file), exist_ok=True)

        with open(summary_file, "w") as f:
            f.write(f"# {title} Coding Summary - {now.strftime('%B %d, %Y')}\n\n")

            # Overview statistics
            total_hours = df["total_time"].sum() / 3600
            total_sessions = df["sessions_count"].sum()
            total_repos = (
                len(sessions_df["repo_name"].unique()) if not sessions_df.empty else 0
            )
            avg_productivity = df["avg_productivity"].mean()

            f.write("## 📊 Overview\n\n")
            f.write(f"- **Total coding time:** {total_hours:.1f} hours\n")
            f.write(f"- **Total sessions:** {total_sessions}\n")
            f.write(f"- **Repositories worked on:** {total_repos}\n")
            f.write(f"- **Average productivity:** {avg_productivity:.1f}/100\n")
            f.write(f"- **Average daily time:** {total_hours/len(df):.1f} hours\n\n")

            # Daily breakdown table
            f.write("## 📅 Daily Breakdown\n\n")
            f.write(
                "| Date | Hours | Sessions | Repos | Productivity | Top Repository |\n"
            )
            f.write(
                "|------|-------|----------|-------|--------------|----------------|\n"
            )

            for _, row in df.iterrows():
                # Find top repo for this date
                day_sessions = sessions_df[
                    sessions_df["created_at"].str.contains(str(row["date"]))
                ]
                top_repo = "N/A"
                if not day_sessions.empty:
                    repo_times = day_sessions.groupby("repo_name")[
                        "duration_seconds"
                    ].sum()
                    top_repo = repo_times.idxmax() if not repo_times.empty else "N/A"

                f.write(
                    f"| {row['date']} | {row['total_time']/3600:.1f}h | {row['sessions_count']} | {row['repos_count']} | {row['avg_productivity']:.1f} | {top_repo} |\n"
                )

            f.write("\n")

            # Repository analysis
            if not sessions_df.empty:
                f.write("## 📦 Repository Analysis\n\n")
                repo_stats = (
                    sessions_df.groupby("repo_name")
                    .agg(
                        {
                            "duration_seconds": "sum",
                            "id": "count",
                            "productivity_score": "mean",
                            "files_changed": "sum",
                            "lines_added": "sum",
                            "lines_deleted": "sum",
                        }
                    )
                    .round(2)
                )

                repo_stats["hours"] = repo_stats["duration_seconds"] / 3600
                repo_stats = repo_stats.sort_values("hours", ascending=False)

                f.write(
                    "| Repository | Hours | Sessions | Avg Productivity | Files | Lines Changed |\n"
                )
                f.write(
                    "|------------|-------|----------|------------------|-------|---------------|\n"
                )

                for repo, stats in repo_stats.iterrows():
                    total_lines = stats["lines_added"] + stats["lines_deleted"]
                    f.write(
                        f"| {repo} | {stats['hours']:.1f}h | {stats['id']} | {stats['productivity_score']:.1f} | {stats['files_changed']} | {total_lines} |\n"
                    )

                f.write("\n")

            # Productivity insights
            f.write("## 🎯 Productivity Insights\n\n")

            if len(df) > 1:
                best_day = df.loc[df["avg_productivity"].idxmax()]
                worst_day = df.loc[df["avg_productivity"].idxmin()]
                most_active_day = df.loc[df["total_time"].idxmax()]

                f.write(
                    f"- **Most productive day:** {best_day['date']} ({best_day['avg_productivity']:.1f}/100)\n"
                )
                f.write(
                    f"- **Most active day:** {most_active_day['date']} ({most_active_day['total_time']/3600:.1f} hours)\n"
                )
                f.write(
                    f"- **Room for improvement:** {worst_day['date']} ({worst_day['avg_productivity']:.1f}/100)\n\n"
                )

            # Goals and recommendations
            f.write("## 🎯 Goals & Recommendations\n\n")

            if total_hours < 40:  # Assuming 40 hours/week target
                f.write(
                    "- 📈 **Increase coding time:** Consider setting daily time goals\n"
                )
            if avg_productivity < 70:
                f.write(
                    "- 🎯 **Improve productivity:** Focus on fewer projects at a time\n"
                )
            if total_repos > 5:
                f.write(
                    "- 🎯 **Focus more:** Working on many projects can reduce productivity\n"
                )

            f.write("\n---\n")
            f.write(
                f"*Generated by Activity Monitor on {now.strftime('%Y-%m-%d %H:%M:%S')}*\n"
            )

        console.print(f"[green]📊 {title} summary created: {summary_file}[/green]")
        return summary_file


class EnhancedChangeHandler(FileSystemEventHandler):
    """Enhanced file system event handler with verbose logging."""

    def __init__(self, tracker):
        self.tracker = tracker
        verbose_print(f"File system handler initialized for: {MONITOR_PATH}")

    def on_modified(self, event):
        if event.is_directory:
            verbose_print(f"Directory change ignored: {event.src_path}")
            return

        verbose_print(f"File change detected: {event.src_path}")

        # Skip certain file types
        skip_extensions = {".pyc", ".log", ".tmp", ".swp", ".DS_Store"}
        skip_paths = {".git", "__pycache__", "node_modules", ".vscode"}

        if any(event.src_path.endswith(ext) for ext in skip_extensions):
            verbose_print(
                f"Skipped file (extension): {os.path.basename(event.src_path)}"
            )
            return

        if any(path_part in event.src_path for path_part in skip_paths):
            verbose_print(f"Skipped file (path): {event.src_path}")
            return

        repo_path = get_repo_root(event.src_path)
        if not repo_path:
            verbose_print(f"Not in git repo: {event.src_path}")
            return

        debug_print(f"Processing change in repo: {os.path.basename(repo_path)}")

        now = time.time()
        start, last = self.tracker.active_sessions.get(repo_path, (None, None))

        # Update file change set to track unique files
        if repo_path not in self.tracker.file_changes:
            self.tracker.file_changes[repo_path] = set()
        self.tracker.file_changes[repo_path].add(event.src_path)

        if start is None:
            self.tracker.active_sessions[repo_path] = (now, now)
            info_print(f"🟢 Started session: {os.path.basename(repo_path)}")
            verbose_print(
                f"Session start time: {datetime.fromtimestamp(now).strftime('%H:%M:%S')}"
            )
        else:
            self.tracker.active_sessions[repo_path] = (start, now)
            session_duration = now - start
            verbose_print(
                f"Updated session: {os.path.basename(repo_path)} (active for {session_duration/60:.1f}min)"
            )

    def on_created(self, event):
        if not event.is_directory and VERBOSE:
            verbose_print(f"File created: {event.src_path}")

    def on_deleted(self, event):
        if not event.is_directory and VERBOSE:
            verbose_print(f"File deleted: {event.src_path}")

    def on_moved(self, event):
        if not event.is_directory and VERBOSE:
            verbose_print(f"File moved: {event.src_path} -> {event.dest_path}")


# Utility functions
def get_repo_root(path):
    """Get git repository root path."""
    try:
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


def extract_task_name(commit_message):
    """Extract task name from commit message."""
    # Ensure we have a string
    if commit_message is None or commit_message is False:
        return "Unknown Task"

    # Convert to string if it's not already
    if not isinstance(commit_message, str):
        commit_message = str(commit_message)

    if not commit_message or commit_message.strip() == "":
        return "Unknown Task"

    # Common task patterns to look for
    patterns = [
        # JIRA-style: ABC-123, PROJ-456 (keep the full identifier)
        r"([A-Z]+-\d+)(?::\s*(.+))?",
        # GitHub issues: #123, fixes #456, closes #789 (with description)
        r"(?:fix(?:es)?|close(?:s)?|resolve(?:s)?)?\s*#(\d+)(?::\s*(.+))?",
        # Square brackets: [TASK-123], [Feature], [Bug Fix]
        r"\[([^\]]+)\](?::\s*(.+))?",
        # Feature/bug prefixes: feat: something, fix: something, bug: something
        r"(?:feat(?:ure)?|fix|bug|chore|docs?|refactor|style|test):\s*([^,\n]+)",
        # Common verbs at start: Add, Fix, Update, Implement, etc.
        r"^((?:Add|Fix|Update|Implement|Create|Remove|Delete|Refactor|Optimize|Improve)[^,\n]*)",
    ]

    import re

    for pattern in patterns:
        match = re.search(pattern, commit_message, re.IGNORECASE)
        if match:
            groups = match.groups()

            # For JIRA-style, GitHub issues, or bracketed items
            if len(groups) >= 2 and groups[1]:
                # Use the description part if available
                task = groups[1].strip()
            elif groups[0]:
                # Use the first group (ID or main content)
                task = groups[0].strip()
            else:
                continue

            # Clean up the task name
            task = task.replace("_", " ").replace("-", " ")
            # Capitalize first letter of each word, but preserve acronyms
            words = task.split()
            cleaned_words = []
            for word in words:
                if word.isupper() and len(word) > 1:
                    cleaned_words.append(word)  # Keep acronyms as-is
                elif len(word) == 1:
                    cleaned_words.append(word.upper())  # Single letters uppercase
                else:
                    cleaned_words.append(word.capitalize())

            task = " ".join(cleaned_words)
            return task[:60]  # Increased length limit

    # Fallback: use first few words of commit message
    words = commit_message.split()
    if len(words) >= 3:
        return " ".join(words[:3]).strip(".,!?:").title()
    elif len(words) >= 1:
        return words[0].capitalize()

    return "General Work"


# Analytics and Visualization Functions
class Analytics:
    """Analytics and visualization for activity data."""

    def __init__(self):
        self.db = DatabaseManager()

    def generate_daily_report(self, days=7):
        """Generate a daily activity report."""
        df = self.db.get_daily_stats(days)

        if df.empty:
            console.print("[yellow]No data available for report[/yellow]")
            return

        table = Table(title=f"📊 Daily Activity Report (Last {days} days)")
        table.add_column("Date", style="cyan")
        table.add_column("Time Spent", style="green")
        table.add_column("Repos", style="yellow")
        table.add_column("Sessions", style="blue")
        table.add_column("Files", style="magenta")
        table.add_column("Lines", style="red")
        table.add_column("Productivity", style="bright_green")

        for _, row in df.iterrows():
            table.add_row(
                str(row["date"]),
                f"{row['total_time']/3600:.1f}h",
                str(row["repos_count"]),
                str(row["sessions_count"]),
                str(row["files_changed"]),
                str(row["lines_changed"]),
                f"{row['avg_productivity']:.1f}/100",
            )

        console.print(table)

    def generate_productivity_chart(self, days=30):
        """Generate productivity visualization."""
        df = self.db.get_daily_stats(days)

        if df.empty:
            console.print("[yellow]No data available for charts[/yellow]")
            return

        # Create plotly chart
        fig = go.Figure()

        fig.add_trace(
            go.Scatter(
                x=df["date"],
                y=df["total_time"] / 3600,
                mode="lines+markers",
                name="Hours Worked",
                line=dict(color="blue"),
            )
        )

        fig.add_trace(
            go.Scatter(
                x=df["date"],
                y=df["avg_productivity"],
                mode="lines+markers",
                name="Productivity Score",
                yaxis="y2",
                line=dict(color="green"),
            )
        )

        fig.update_layout(
            title="📈 Productivity Trends",
            xaxis_title="Date",
            yaxis_title="Hours Worked",
            yaxis2=dict(title="Productivity Score", overlaying="y", side="right"),
        )

        # Save chart
        chart_path = os.path.join(LOG_DIR, "productivity_chart.html")
        fig.write_html(chart_path)
        console.print(f"[green]📊 Chart saved to: {chart_path}[/green]")

    def export_data(self, format="csv", days=30):
        """Export activity data in various formats."""
        df = self.db.get_sessions(days)

        if df.empty:
            console.print("[yellow]No data to export[/yellow]")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if format.lower() == "csv":
            filepath = os.path.join(LOG_DIR, f"activity_export_{timestamp}.csv")
            df.to_csv(filepath, index=False)
        elif format.lower() == "json":
            filepath = os.path.join(LOG_DIR, f"activity_export_{timestamp}.json")
            df.to_json(filepath, orient="records", date_format="iso")
        else:
            console.print("[red]Unsupported export format[/red]")
            return

        console.print(f"[green]📄 Data exported to: {filepath}[/green]")

    def generate_pdf_report(self, days=30, report_type="comprehensive"):
        """Generate a comprehensive PDF report."""
        if not PDF_AVAILABLE:
            console.print("[red]❌ PDF libraries not available. Install with:[/red]")
            console.print("pip install reportlab Pillow kaleido")
            return None

        return PDFReportGenerator(self.db).generate_report(days, report_type)


class PDFReportGenerator:
    """Generate PDF reports from activity data."""

    def __init__(self, db_manager):
        self.db = db_manager

    def _get_cell_style(self):
        """Return a ParagraphStyle for table cells."""
        return ParagraphStyle(
            "cell",
            fontSize=8,
            alignment=0,  # LEFT
            leading=10,
            spaceAfter=2,
        )

    def generate_report(self, days=30, report_type="comprehensive"):
        """Generate PDF report with charts and tables."""
        # Get data
        df = self.db.get_daily_stats(days)
        sessions_df = self.db.get_sessions(days)

        if df.empty:
            console.print("[yellow]No data available for PDF report[/yellow]")
            return None

        # Create filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"activity_{report_type}_report_{timestamp}.pdf"
        pdf_path = os.path.join(LOG_DIR, filename)

        # Create PDF document
        doc = SimpleDocTemplate(pdf_path, pagesize=letter)
        story = []
        styles = getSampleStyleSheet()

        # Add content
        self._add_title_and_summary(story, styles, df, sessions_df, days)
        self._add_daily_breakdown(story, styles, df, sessions_df)

        if report_type == "comprehensive" and not sessions_df.empty:
            self._add_repository_analysis(story, styles, sessions_df)

        self._add_productivity_insights(story, styles, df, sessions_df)
        self._add_footer(story, styles)

        # Build PDF
        try:
            doc.build(story)
            console.print(f"[green]📄 PDF report generated: {pdf_path}[/green]")
            return pdf_path
        except Exception as e:
            error_print(f"Error generating PDF: {e}")
            return None

    def _add_title_and_summary(self, story, styles, df, sessions_df, days):
        """Add title and executive summary."""
        # Custom styles
        title_style = ParagraphStyle(
            "CustomTitle",
            parent=styles["Heading1"],
            fontSize=24,
            spaceAfter=30,
            textColor=HexColor("#2E86C1"),
        )

        # Title
        story.append(Paragraph("📊 Activity Monitor Report", title_style))
        story.append(
            Paragraph(
                f"Report Period: {days} days (Generated: {datetime.now().strftime('%B %d, %Y')})",
                styles["Normal"],
            )
        )
        story.append(Spacer(1, 20))

        # Executive Summary
        heading_style = ParagraphStyle(
            "CustomHeading",
            parent=styles["Heading2"],
            fontSize=16,
            spaceBefore=20,
            spaceAfter=10,
            textColor=HexColor("#1B4F72"),
        )

        story.append(Paragraph("📋 Executive Summary", heading_style))

        # Calculate metrics
        total_hours = df["total_time"].sum() / 3600
        total_sessions = df["sessions_count"].sum()
        total_repos = (
            len(sessions_df["repo_name"].unique()) if not sessions_df.empty else 0
        )
        avg_productivity = df["avg_productivity"].mean()
        total_files = df["files_changed"].sum()
        total_lines = df["lines_changed"].sum()

        # Create summary table
        summary_data = [
            ["Metric", "Value"],
            ["Total Coding Time", f"{total_hours:.1f} hours"],
            ["Total Sessions", f"{total_sessions}"],
            ["Repositories Worked On", f"{total_repos}"],
            ["Average Productivity Score", f"{avg_productivity:.1f}/100"],
            ["Files Modified", f"{total_files}"],
            ["Lines Changed", f"{total_lines}"],
            ["Average Daily Time", f"{total_hours/len(df):.1f} hours"],
        ]

        summary_table = RLTable(summary_data)
        summary_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), HexColor("#3498DB")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 12),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                    ("BACKGROUND", (0, 1), (-1, -1), HexColor("#F8F9FA")),
                    ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ]
            )
        )

        story.append(summary_table)
        story.append(Spacer(1, 20))

    def _add_daily_breakdown(self, story, styles, df, sessions_df):
        """Add daily activity breakdown table."""
        heading_style = ParagraphStyle(
            "CustomHeading",
            parent=styles["Heading2"],
            fontSize=16,
            spaceBefore=20,
            spaceAfter=10,
            textColor=HexColor("#1B4F72"),
        )

        story.append(Paragraph("📅 Daily Activity Breakdown", heading_style))

        daily_data = [
            ["Date", "Hours", "Sessions", "Repos", "Productivity", "Top Repository"]
        ]
        for _, row in df.iterrows():
            # Find top repo for this date
            day_sessions = sessions_df[
                sessions_df["created_at"].str.contains(str(row["date"]))
            ]
            top_repo = "N/A"
            if not day_sessions.empty:
                repo_times = day_sessions.groupby("repo_name")["duration_seconds"].sum()
                top_repo = repo_times.idxmax() if not repo_times.empty else "N/A"

            daily_data.append(
                [
                    str(row["date"]),
                    f"{row['total_time']/3600:.1f}h",
                    str(row["sessions_count"]),
                    str(row["repos_count"]),
                    f"{row['avg_productivity']:.1f}/100",
                    top_repo,
                ]
            )

        daily_table = RLTable(daily_data)
        daily_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), HexColor("#E74C3C")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                    ("FONTSIZE", (0, 1), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                    ("BACKGROUND", (0, 1), (-1, -1), HexColor("#FDEDEC")),
                    ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ]
            )
        )

        story.append(daily_table)
        story.append(Spacer(1, 20))

    def _add_repository_analysis(self, story, styles, sessions_df):
        """Add repository analysis section."""
        heading_style = ParagraphStyle(
            "CustomHeading",
            parent=styles["Heading2"],
            fontSize=16,
            spaceBefore=20,
            spaceAfter=10,
            textColor=HexColor("#1B4F72"),
        )

        story.append(Paragraph("📦 Repository Analysis", heading_style))

        repo_stats = (
            sessions_df.groupby("repo_name")
            .agg(
                {
                    "duration_seconds": "sum",
                    "id": "count",
                    "productivity_score": "mean",
                    "files_changed": "sum",
                    "lines_added": "sum",
                    "lines_deleted": "sum",
                }
            )
            .round(2)
        )

        repo_stats["hours"] = repo_stats["duration_seconds"] / 3600
        repo_stats = repo_stats.sort_values("hours", ascending=False)

        repo_data = [
            [
                "Repository",
                "Hours",
                "Sessions",
                "Avg Productivity",
                "Files",
                "Lines Changed",
            ]
        ]
        for repo, stats in repo_stats.head(10).iterrows():  # Top 10 repositories
            total_lines = stats["lines_added"] + stats["lines_deleted"]
            repo_data.append(
                [
                    repo[:20]
                    + ("..." if len(repo) > 20 else ""),  # Truncate long names
                    f"{stats['hours']:.1f}h",
                    str(stats["id"]),
                    f"{stats['productivity_score']:.1f}",
                    str(stats["files_changed"]),
                    str(int(total_lines)),
                ]
            )

        repo_table = RLTable(repo_data)
        repo_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), HexColor("#27AE60")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                    ("FONTSIZE", (0, 1), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                    ("BACKGROUND", (0, 1), (-1, -1), HexColor("#E8F8F5")),
                    ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ]
            )
        )

        story.append(repo_table)
        story.append(Spacer(1, 20))

    def _add_productivity_insights(self, story, styles, df, sessions_df):
        """Add productivity insights and recommendations."""
        heading_style = ParagraphStyle(
            "CustomHeading",
            parent=styles["Heading2"],
            fontSize=16,
            spaceBefore=20,
            spaceAfter=10,
            textColor=HexColor("#1B4F72"),
        )

        story.append(Paragraph("🎯 Productivity Insights", heading_style))

        insights = []
        if len(df) > 1:
            best_day = df.loc[df["avg_productivity"].idxmax()]
            worst_day = df.loc[df["avg_productivity"].idxmin()]
            most_active_day = df.loc[df["total_time"].idxmax()]

            insights.extend(
                [
                    f"• Most productive day: {best_day['date']} ({best_day['avg_productivity']:.1f}/100)",
                    f"• Most active day: {most_active_day['date']} ({most_active_day['total_time']/3600:.1f} hours)",
                    f"• Room for improvement: {worst_day['date']} ({worst_day['avg_productivity']:.1f}/100)",
                ]
            )

        # Add recommendations
        total_hours = df["total_time"].sum() / 3600
        avg_productivity = df["avg_productivity"].mean()
        total_repos = (
            len(sessions_df["repo_name"].unique()) if not sessions_df.empty else 0
        )

        if total_hours < 40:
            insights.append(
                "• Consider setting daily time goals to increase coding time"
            )
        if avg_productivity < 70:
            insights.append(
                "• Focus on fewer projects at a time to improve productivity"
            )
        if total_repos > 5:
            insights.append(
                "• Working on many projects can reduce overall productivity"
            )

        for insight in insights:
            story.append(Paragraph(insight, styles["Normal"]))

        story.append(Spacer(1, 20))

    def _add_footer(self, story, styles):
        """Add report footer."""
        story.append(Spacer(1, 30))
        story.append(Paragraph("---", styles["Normal"]))
        story.append(
            Paragraph(
                f"Generated by Activity Monitor on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                styles["Normal"],
            )
        )

    def generate_repo_timesheet(self, days=30, repo=None):
        """Generate a PDF timesheet grouped by repository, showing task names."""
        df = self.db.get_sessions(days)
        if repo:
            df = df[df["repo_name"] == repo]
        if df.empty:
            console.print("[yellow]No data available for repo timesheet PDF[/yellow]")
            return None
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"repo_timesheet_{repo or 'all'}_{timestamp}.pdf"
        pdf_path = os.path.join(LOG_DIR, filename)
        doc = SimpleDocTemplate(pdf_path, pagesize=letter)
        story = []
        styles = getSampleStyleSheet()
        title = f"Repository Timesheet{' for ' + repo if repo else ''}"
        story.append(Paragraph(title, styles["Title"]))
        story.append(Spacer(1, 20))
        # Table header
        data = [
            [
                "Repository",
                "Date",
                "Start",
                "End",
                "Duration (min)",
                "Task Name",
                "Commit",
            ]
        ]
        cell_style = self._get_cell_style()

        for _, row in df.iterrows():
            start = (
                pd.to_datetime(row["start_time"]).strftime("%Y-%m-%d %H:%M")
                if row["start_time"]
                else ""
            )
            end = (
                pd.to_datetime(row["end_time"]).strftime("%Y-%m-%d %H:%M")
                if row["end_time"]
                else ""
            )
            duration = (
                f"{row['duration_seconds']/60:.1f}" if row["duration_seconds"] else ""
            )
            # Extract task name from commit message
            commit_msg = row.get("commit_message", "")
            task_name = extract_task_name(
                str(commit_msg) if pd.notna(commit_msg) else "General Work"
            )
            data.append(
                [
                    Paragraph(row["repo_name"], cell_style),
                    Paragraph(
                        pd.to_datetime(row["created_at"]).strftime("%Y-%m-%d"),
                        cell_style,
                    ),
                    Paragraph(start, cell_style),
                    Paragraph(end, cell_style),
                    Paragraph(duration, cell_style),
                    Paragraph(task_name, cell_style),
                    Paragraph(
                        str(row["commit_hash"])[0:7] if row["commit_hash"] else "",
                        cell_style,
                    ),
                ]
            )
        table = RLTable(data)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), HexColor("#2980B9")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                    ("FONTSIZE", (0, 1), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                    ("BACKGROUND", (0, 1), (-1, -1), HexColor("#EBF5FB")),
                    ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 20))
        story.append(
            Paragraph(
                f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                styles["Normal"],
            )
        )
        try:
            doc.build(story)
            console.print(f"[green]📄 Repo timesheet PDF generated: {pdf_path}[/green]")
            return pdf_path
        except Exception as e:
            import traceback

            error_print(f"Error generating repo timesheet PDF: {e}")
            error_print(f"Full traceback: {traceback.format_exc()}")
            return None

    def generate_daily_timesheet(self, days=30, repo=None):
        """Generate a PDF timesheet grouped by day, showing task names."""
        df = self.db.get_sessions(days)
        if repo:
            df = df[df["repo_name"] == repo]
        if df.empty:
            console.print("[yellow]No data available for daily timesheet PDF[/yellow]")
            return None
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"daily_timesheet_{repo or 'all'}_{timestamp}.pdf"
        pdf_path = os.path.join(LOG_DIR, filename)
        doc = SimpleDocTemplate(pdf_path, pagesize=letter)
        story = []
        styles = getSampleStyleSheet()
        title = f"Daily Timesheet{' for ' + repo if repo else ''}"
        story.append(Paragraph(title, styles["Title"]))
        story.append(Spacer(1, 20))
        # Group by date
        df["date"] = pd.to_datetime(df["created_at"]).dt.date
        grouped = df.groupby("date")
        data = [["Date", "Total Time (h)", "Tasks", "Repositories"]]
        cell_style = self._get_cell_style()

        for date, group in grouped:
            total_time = group["duration_seconds"].sum() / 3600
            # Aggregate unique task names for the day
            tasks = sorted(
                set(
                    extract_task_name(str(msg) if pd.notna(msg) else "General Work")
                    for msg in group["commit_message"]
                )
            )
            tasks_str = ", ".join(tasks)
            repos = ", ".join(sorted(group["repo_name"].unique()))
            data.append(
                [
                    Paragraph(str(date), cell_style),
                    Paragraph(f"{total_time:.2f}", cell_style),
                    Paragraph(tasks_str, cell_style),
                    Paragraph(repos, cell_style),
                ]
            )
        table = RLTable(data)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), HexColor("#16A085")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                    ("FONTSIZE", (0, 1), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                    ("BACKGROUND", (0, 1), (-1, -1), HexColor("#E8F8F5")),
                    ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 20))
        story.append(
            Paragraph(
                f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                styles["Normal"],
            )
        )
        try:
            doc.build(story)
            console.print(
                f"[green]📄 Daily timesheet PDF generated: {pdf_path}[/green]"
            )
            return pdf_path
        except Exception as e:
            import traceback

            error_print(f"Error generating daily timesheet PDF: {e}")
            error_print(f"Full traceback: {traceback.format_exc()}")
            return None

    def generate_monthly_timesheet(self, repo=None):
        """Generate a PDF timesheet grouped by month, showing task names."""
        df = self.db.get_sessions(365)  # Get up to a year
        if repo:
            df = df[df["repo_name"] == repo]
        if df.empty:
            console.print(
                "[yellow]No data available for monthly timesheet PDF[/yellow]"
            )
            return None
        df["month"] = pd.to_datetime(df["created_at"]).dt.to_period("M")
        grouped = df.groupby("month")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"monthly_timesheet_{repo or 'all'}_{timestamp}.pdf"
        pdf_path = os.path.join(LOG_DIR, filename)
        doc = SimpleDocTemplate(pdf_path, pagesize=letter)
        story = []
        styles = getSampleStyleSheet()
        title = f"Monthly Timesheet{' for ' + repo if repo else ''}"
        story.append(Paragraph(title, styles["Title"]))
        story.append(Spacer(1, 20))
        data = [["Month", "Total Time (h)", "Tasks", "Repositories"]]
        cell_style = self._get_cell_style()

        for month, group in grouped:
            total_time = group["duration_seconds"].sum() / 3600
            # Aggregate unique task names for the month
            tasks = sorted(
                set(
                    extract_task_name(str(msg) if pd.notna(msg) else "General Work")
                    for msg in group["commit_message"]
                )
            )
            tasks_str = ", ".join(tasks)
            repos = ", ".join(sorted(group["repo_name"].unique()))
            data.append(
                [
                    Paragraph(str(month), cell_style),
                    Paragraph(f"{total_time:.2f}", cell_style),
                    Paragraph(tasks_str, cell_style),
                    Paragraph(repos, cell_style),
                ]
            )
        table = RLTable(data)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), HexColor("#8E44AD")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                    ("FONTSIZE", (0, 1), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                    ("BACKGROUND", (0, 1), (-1, -1), HexColor("#F5EEF8")),
                    ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 20))
        story.append(
            Paragraph(
                f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                styles["Normal"],
            )
        )
        try:
            doc.build(story)
            console.print(
                f"[green]📄 Monthly timesheet PDF generated: {pdf_path}[/green]"
            )
            return pdf_path
        except Exception as e:
            import traceback

            error_print(f"Error generating monthly timesheet PDF: {e}")
            error_print(f"Full traceback: {traceback.format_exc()}")
            return None


# CLI Commands
def cmd_start(verbose=False):
    """Start activity monitoring."""
    set_verbose(verbose)
    info_print("Initializing Activity Monitor...")
    verbose_print("Setting up database and tracker...")

    tracker = EnhancedActivityTracker()
    observer = tracker.start_monitoring()

    if observer is None:
        error_print("Failed to start monitoring")
        return

    info_print("Press Ctrl+C to stop monitoring")
    verbose_print("Monitoring loop starting...")

    try:
        while tracker.running:
            time.sleep(1)
    except KeyboardInterrupt:
        info_print("Stopping monitor...")
        tracker.stop_monitoring()


def cmd_status():
    """Show current status and recent activity."""
    info_print("📊 Activity Monitor Status")
    analytics = Analytics()

    try:
        db = DatabaseManager()
        recent_sessions = db.get_sessions(1)  # Last 1 day

        if not recent_sessions.empty:
            info_print(f"Found {len(recent_sessions)} recent sessions")

            # Show recent commits table
            table = Table(title="🔄 Recent Activity")
            table.add_column("Time", style="cyan")
            table.add_column("Repository", style="green")
            table.add_column("Duration", style="yellow")
            table.add_column("Commit Message", style="blue")
            table.add_column("Productivity", style="magenta")

            for _, session in recent_sessions.head(10).iterrows():
                duration = f"{session['duration_seconds']/60:.1f}min"
                commit_msg = (
                    session["commit_message"][:40] + "..."
                    if len(str(session["commit_message"])) > 40
                    else str(session["commit_message"])
                )
                productivity = f"{session['productivity_score']:.1f}/100"
                created_time = pd.to_datetime(session["created_at"]).strftime("%H:%M")

                table.add_row(
                    created_time,
                    session["repo_name"],
                    duration,
                    commit_msg,
                    productivity,
                )

            console.print(table)
        else:
            console.print("[yellow]⚠️  No recent activity found[/yellow]")

    except Exception as e:
        error_print(f"Error retrieving status: {e}")

    # Show daily report
    analytics.generate_daily_report(7)


def cmd_test():
    """Test if file monitoring is working."""
    info_print("🧪 Testing file monitoring...")

    if not os.path.exists(MONITOR_PATH):
        error_print(f"Monitor path doesn't exist: {MONITOR_PATH}")
        return

    info_print(f"✅ Monitor path exists: {MONITOR_PATH}")

    # Check for git repos
    git_repos = []
    for root, dirs, files in os.walk(MONITOR_PATH):
        if ".git" in dirs:
            git_repos.append(root)

    if git_repos:
        info_print(f"✅ Found {len(git_repos)} Git repositories:")
        for repo in git_repos[:3]:
            console.print(f"   - {os.path.basename(repo)}")
    else:
        console.print("⚠️  No Git repositories found")


def cmd_debug():
    """Debug command to check system status."""
    info_print("🔧 Debug Information")

    # Check database
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM activity_sessions")
        session_count = cursor.fetchone()[0]
        conn.close()
        info_print(f"✅ Database sessions: {session_count}")
    except Exception as e:
        error_print(f"Database error: {e}")

    info_print(f"📁 Monitor path: {MONITOR_PATH}")
    info_print(f"💾 Log directory: {LOG_DIR}")
    info_print(f"⏱️  Idle threshold: {IDLE_THRESHOLD}s")


def cmd_summary(period="week"):
    """Generate markdown summary reports."""
    tracker = EnhancedActivityTracker()
    tracker.generate_markdown_summary(period)


def cmd_report(days=30):
    """Generate detailed analytics report."""
    analytics = Analytics()
    analytics.generate_daily_report(days)
    analytics.generate_productivity_chart(days)


def cmd_export(format="csv", days=30):
    """Export activity data."""
    analytics = Analytics()
    analytics.export_data(format, days)


def cmd_pdf(days=30, report_type="comprehensive", sheet="default", repo=None):
    """Generate PDF report or timesheet."""
    analytics = Analytics()
    pdfgen = PDFReportGenerator(analytics.db)
    if sheet == "repo":
        pdf_path = pdfgen.generate_repo_timesheet(days, repo)
    elif sheet == "daily":
        pdf_path = pdfgen.generate_daily_timesheet(days, repo)
    elif sheet == "monthly":
        pdf_path = pdfgen.generate_monthly_timesheet(repo)
    else:
        pdf_path = analytics.generate_pdf_report(days, report_type)
    if pdf_path:
        console.print(f"[green]📄 PDF report generated successfully![/green]")
        console.print(f"Location: {pdf_path}")
    else:
        console.print("[red]❌ Failed to generate PDF report[/red]")


# Main CLI
def main():
    """Main CLI interface."""
    parser = argparse.ArgumentParser(
        description="🚀 Enhanced Activity Monitor - Track your coding productivity with advanced Git integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
📋 COMMAND EXAMPLES:

🚀 MONITORING:
  %(prog)s start                          Start monitoring (basic mode)
  %(prog)s start --verbose               Start with detailed logging
  %(prog)s status                        Show current activity status
  %(prog)s test                          Test file monitoring setup
  %(prog)s debug                         Show system debug information

📊 REPORTS & ANALYTICS:
  %(prog)s report                        Generate 7-day activity report
  %(prog)s report --days 30              Generate 30-day activity report
  %(prog)s summary                       Generate weekly markdown summary
  %(prog)s summary --period month        Generate monthly markdown summary

📄 PDF REPORTS:
  %(prog)s pdf                           Generate comprehensive PDF report (30 days)
  %(prog)s pdf --days 7                  Generate 7-day comprehensive report
  %(prog)s pdf --type summary            Generate summary report (vs comprehensive)
  
📋 PDF TIMESHEETS:
  %(prog)s pdf --sheet repo              Repository-based timesheet
  %(prog)s pdf --sheet daily             Daily timesheet with task summaries
  %(prog)s pdf --sheet monthly           Monthly timesheet with task summaries
  %(prog)s pdf --sheet repo --repo myapp Timesheet for specific repository
  %(prog)s pdf --sheet daily --days 14   Daily timesheet for last 14 days

📤 DATA EXPORT:
  %(prog)s export                        Export last 30 days as CSV
  %(prog)s export --format json          Export as JSON format
  %(prog)s export --format csv --days 7  Export last 7 days as CSV

🎯 FEATURES:
  • Real-time Git repository monitoring
  • Automatic commit detection and session logging
  • Productivity scoring based on code changes
  • Task extraction from commit messages
  • Multiple output formats (PDF, CSV, JSON, Markdown)
  • Rich CLI with colored output and tables
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Start command
    start_parser = subparsers.add_parser(
        "start",
        help="Start real-time activity monitoring",
        description="🚀 Start monitoring file changes in Git repositories. Tracks coding sessions, detects commits, and logs productivity metrics in real-time.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s start                    Start monitoring in normal mode
  %(prog)s start -v                 Start with verbose logging output
  %(prog)s start --verbose          Same as -v, shows detailed debug info

The monitor will:
  • Track file changes in all Git repositories under the monitor path
  • Detect new commits and calculate session durations
  • Score productivity based on files changed and lines modified
  • Generate daily markdown logs with task summaries
  • Display real-time status updates in the terminal
        """,
    )
    start_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output with detailed logging and debug information",
    )

    # Test command
    test_parser = subparsers.add_parser(
        "test",
        help="Test file monitoring setup and configuration",
        description="🧪 Verify that the monitoring system can detect Git repositories and that all paths are configured correctly.",
        epilog="""
This command will check:
  • Monitor path exists and is accessible
  • Git repositories are found in the monitor path  
  • Database connection is working
  • Configuration is valid

Use this before running 'start' to ensure everything is set up properly.
        """,
    )

    # Status command
    status_parser = subparsers.add_parser(
        "status",
        help="Show current activity status and recent sessions",
        description="📊 Display current monitoring status, recent activity sessions, and a 7-day productivity overview with colorful tables.",
        epilog="""
Shows:
  • Recent coding sessions (last 24 hours)
  • Repository activity breakdown
  • Time spent per repository
  • Productivity scores and trends
  • Commit messages and task summaries

Perfect for a quick overview of your recent coding activity.
        """,
    )

    # Debug command
    debug_parser = subparsers.add_parser(
        "debug",
        help="Show system debug information and configuration",
        description="🔧 Display detailed system information for troubleshooting configuration issues, database status, and path settings.",
        epilog="""
Debug information includes:
  • Database path and session count
  • Monitor path configuration
  • Idle threshold settings
  • Log directory location
  • System configuration validation

Use this when troubleshooting issues with monitoring or data collection.
        """,
    )

    # Summary command
    summary_parser = subparsers.add_parser(
        "summary",
        help="Generate markdown summary reports",
        description="📝 Generate comprehensive markdown summary reports with productivity insights, repository analysis, and recommendations.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s summary                  Generate weekly summary (default)
  %(prog)s summary --period week    Generate weekly summary (last 7 days)
  %(prog)s summary --period month   Generate monthly summary (last 30 days)

Generated reports include:
  • Overview statistics (total time, sessions, repositories)
  • Daily activity breakdown table
  • Repository analysis with time spent per repo
  • Productivity insights and recommendations
  • Goals and improvement suggestions

Reports are saved as markdown files in the summaries/ directory.
        """,
    )
    summary_parser.add_argument(
        "--period",
        choices=["week", "month"],
        default="week",
        help="Summary period: 'week' for 7 days (default) or 'month' for 30 days",
    )

    # Report command
    report_parser = subparsers.add_parser(
        "report",
        help="Generate detailed analytics reports with charts",
        description="📊 Generate detailed activity reports with rich CLI tables and save productivity charts as HTML files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s report                   Generate 7-day report (default)
  %(prog)s report --days 30         Generate 30-day report
  %(prog)s report --days 1          Generate report for today only

Features:
  • Colorful CLI table with daily breakdown
  • Interactive productivity chart (saved as HTML)
  • Time spent, repository count, session count
  • Files changed and lines modified statistics
  • Productivity scores with visual indicators

Charts are saved to the log directory as 'productivity_chart.html'.
        """,
    )
    report_parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to include in report (default: 7)",
    )

    # Export command
    export_parser = subparsers.add_parser(
        "export",
        help="Export activity data in various formats",
        description="📤 Export your coding activity data to CSV or JSON files for further analysis, integration with other tools, or backup purposes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s export                           Export last 30 days as CSV (default)
  %(prog)s export --format csv              Export as CSV format
  %(prog)s export --format json             Export as JSON format  
  %(prog)s export --days 7                  Export last 7 days
  %(prog)s export --format json --days 14   Export last 14 days as JSON

Exported data includes:
  • Repository names and file paths
  • Session start/end times and durations
  • Commit hashes and messages
  • Files changed and lines added/deleted
  • Productivity scores and timestamps
  • Task names extracted from commit messages

Files are saved with timestamps in the log directory.
        """,
    )
    export_parser.add_argument(
        "--format",
        choices=["csv", "json"],
        default="csv",
        help="Export format: 'csv' for spreadsheet compatibility or 'json' for programmatic use",
    )
    export_parser.add_argument(
        "--days", type=int, default=30, help="Number of days to export (default: 30)"
    )

    # PDF Report command
    pdf_parser = subparsers.add_parser(
        "pdf",
        help="Generate professional PDF reports and timesheets",
        description="📄 Generate beautiful PDF reports with charts, tables, and analysis. Perfect for client reports, time tracking, or productivity reviews.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
🎯 REPORT TYPES:
  --type summary         Executive summary with key metrics
  --type comprehensive   Full report with detailed analysis (default)

📋 TIMESHEET FORMATS:
  --sheet default        Comprehensive PDF report (default)
  --sheet repo           Repository-based timesheet with sessions
  --sheet daily          Daily timesheet with task summaries  
  --sheet monthly        Monthly timesheet with task summaries

📊 EXAMPLES:

Basic Reports:
  %(prog)s pdf                              Comprehensive report (30 days)
  %(prog)s pdf --days 7                     Weekly comprehensive report
  %(prog)s pdf --type summary               Executive summary (30 days)
  %(prog)s pdf --days 14 --type summary     2-week executive summary

Timesheets:
  %(prog)s pdf --sheet repo                 Repository timesheet (30 days)
  %(prog)s pdf --sheet daily                Daily timesheet (30 days)
  %(prog)s pdf --sheet monthly              Monthly timesheet (365 days)
  %(prog)s pdf --sheet daily --days 7       Weekly daily timesheet

Repository-specific:
  %(prog)s pdf --sheet repo --repo myapp    Timesheet for 'myapp' repository
  %(prog)s pdf --sheet daily --repo myapp   Daily timesheet for 'myapp'

🎨 PDF FEATURES:
  • Professional styling with color-coded sections
  • Tables with proper text wrapping for long content
  • Executive summaries with key metrics
  • Repository analysis and productivity insights
  • Task extraction from commit messages
  • Productivity scoring and recommendations

All PDFs are saved with timestamps in your log directory.
        """,
    )
    pdf_parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to include in report (default: 30, monthly sheets use 365)",
    )
    pdf_parser.add_argument(
        "--type",
        choices=["summary", "comprehensive"],
        default="comprehensive",
        help="Report type: 'summary' for executive overview, 'comprehensive' for detailed analysis",
    )
    pdf_parser.add_argument(
        "--sheet",
        choices=["default", "repo", "daily", "monthly"],
        default="default",
        help="Output format: 'default' for reports, 'repo'/'daily'/'monthly' for timesheets",
    )
    pdf_parser.add_argument(
        "--repo",
        type=str,
        default=None,
        help="Filter by repository name (only for timesheet formats)",
    )

    args = parser.parse_args()

    if args.command == "start":
        cmd_start(args.verbose)
    elif args.command == "status":
        cmd_status()
    elif args.command == "test":
        cmd_test()
    elif args.command == "debug":
        cmd_debug()
    elif args.command == "summary":
        cmd_summary(args.period)
    elif args.command == "report":
        cmd_report(args.days)
    elif args.command == "export":
        cmd_export(args.format, args.days)
    elif args.command == "pdf":
        cmd_pdf(args.days, args.type, args.sheet, args.repo)
    elif args.command == "debug":
        cmd_debug()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
