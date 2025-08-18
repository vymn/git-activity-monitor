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

# Load config
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
with open(CONFIG_PATH, "r") as f:
    config = yaml.safe_load(f)

IDLE_THRESHOLD = config.get("idle_threshold", 300)
SCAN_INTERVAL = config.get("scan_interval", 3)
LOG_DIR = os.path.expanduser(config.get("log_dir", "~/Desktop/notes/time_log"))
MONITOR_PATH = os.path.expanduser(config.get("monitor_path", "~/developement"))
DB_PATH = os.path.join(LOG_DIR, "activity_monitor.db")

console = Console()

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
        cursor.execute('''
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
        ''')
        
        # Daily statistics table
        cursor.execute('''
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
        ''')
        
        # Goals and targets table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal_type TEXT NOT NULL,
                target_value INTEGER,
                current_value INTEGER DEFAULT 0,
                date_set TEXT,
                deadline TEXT,
                completed BOOLEAN DEFAULT FALSE
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def save_session(self, session_data):
        """Save a completed session to database."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO activity_sessions 
            (repo_path, repo_name, start_time, end_time, duration_seconds, 
             commit_hash, commit_message, files_changed, lines_added, lines_deleted, productivity_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', session_data)
        
        conn.commit()
        conn.close()
    
    def get_sessions(self, days=7):
        """Get recent sessions."""
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query('''
            SELECT * FROM activity_sessions 
            WHERE created_at >= datetime('now', '-{} days')
            ORDER BY created_at DESC
        '''.format(days), conn)
        conn.close()
        return df
    
    def get_daily_stats(self, days=30):
        """Get daily statistics."""
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query('''
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
        '''.format(days), conn)
        conn.close()
        return df

class EnhancedActivityTracker:
    """Enhanced activity tracker with advanced features."""
    
    def __init__(self):
        self.db = DatabaseManager()
        self.active_sessions = {}
        self.accumulated_time = {}
        self.last_commits = {}
        self.file_changes = {}
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
        """Get detailed git statistics."""
        try:
            # Get lines added/deleted from unstaged changes
            result = subprocess.run([
                "git", "-C", repo_path, "diff", "--stat"
            ], capture_output=True, text=True)
            
            lines_added = lines_deleted = 0
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'insertion' in line:
                        try:
                            lines_added = int(line.split()[3])
                        except:
                            pass
                    if 'deletion' in line:
                        try:
                            lines_deleted = int(line.split()[5])
                        except:
                            pass
            
            return lines_added, lines_deleted
        except:
            return 0, 0
    
    def start_monitoring(self):
        """Start the file system monitoring."""
        self.running = True
        handler = EnhancedChangeHandler(self)
        self.observer = Observer()
        self.observer.schedule(handler, MONITOR_PATH, recursive=True)
        self.observer.start()
        
        console.print(Panel.fit(
            f"[bold green]🚀 Activity Monitor Started[/bold green]\n"
            f"📁 Monitoring: {MONITOR_PATH}\n"
            f"💾 Database: {DB_PATH}\n"
            f"⏱️  Idle threshold: {IDLE_THRESHOLD}s",
            border_style="green"
        ))
        
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
        for repo_path, (start, last) in list(self.active_sessions.items()):
            if start and (now - last > IDLE_THRESHOLD):
                duration = last - start
                self.accumulated_time[repo_path] = self.accumulated_time.get(repo_path, 0) + duration
                self.active_sessions[repo_path] = (None, None)
                
                repo_name = os.path.basename(repo_path)
                console.print(f"[yellow]⏸️  Session paused: {repo_name} ({duration/60:.1f}min)[/yellow]")
    
    def _check_commits(self):
        """Check for new commits and save completed sessions."""
        all_repos = set(self.active_sessions.keys()) | set(self.accumulated_time.keys())
        
        for repo_path in all_repos:
            try:
                commit_hash = subprocess.check_output([
                    "git", "-C", repo_path, "rev-parse", "HEAD"
                ]).decode().strip()
            except subprocess.CalledProcessError:
                continue
            
            if repo_path not in self.last_commits:
                self.last_commits[repo_path] = commit_hash
                continue
            
            if commit_hash != self.last_commits[repo_path]:
                # New commit detected
                self._handle_new_commit(repo_path, commit_hash)
    
    def _handle_new_commit(self, repo_path, commit_hash):
        """Handle a new commit by saving the session."""
        repo_name = os.path.basename(repo_path)
        
        # Add current active session to accumulated time
        start, last = self.active_sessions.get(repo_path, (None, None))
        if start:
            session_duration = last - start
            self.accumulated_time[repo_path] = self.accumulated_time.get(repo_path, 0) + session_duration
            self.active_sessions[repo_path] = (None, None)
        
        total_duration = self.accumulated_time.get(repo_path, 0)
        
        if total_duration > 0:
            # Get commit info and git stats
            commit_message = self._get_commit_message(repo_path)
            files_changed = self.file_changes.get(repo_path, 0)
            lines_added, lines_deleted = self.get_git_stats(repo_path)
            
            # Calculate productivity score
            productivity_score = self.calculate_productivity_score(
                total_duration, files_changed, lines_added + lines_deleted
            )
            
            # Save to database
            session_data = (
                repo_path, repo_name, 
                datetime.now() - timedelta(seconds=total_duration),
                datetime.now(),
                total_duration, commit_hash, commit_message,
                files_changed, lines_added, lines_deleted, productivity_score
            )
            
            self.db.save_session(session_data)
            
            # Show commit notification
            console.print(Panel.fit(
                f"[bold green]✨ Commit Logged![/bold green]\n"
                f"📦 {repo_name}\n"
                f"⏱️  {total_duration/60:.1f} minutes\n"
                f"📝 {commit_message[:50]}...\n"
                f"📊 Productivity: {productivity_score:.1f}/100",
                border_style="green"
            ))
            
            # Reset counters
            self.accumulated_time[repo_path] = 0
            self.file_changes[repo_path] = 0
        
        self.last_commits[repo_path] = commit_hash
    
    def _get_commit_message(self, repo_path):
        """Get the latest commit message."""
        try:
            return subprocess.check_output([
                "git", "-C", repo_path, "log", "-1", "--pretty=%B"
            ]).decode().strip()
        except:
            return "No commit message"
    
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
                    files = self.file_changes.get(repo_path, 0)
                    table.add_row(
                        os.path.basename(repo_path),
                        "🟢 Active",
                        f"{duration/60:.1f}m",
                        str(files)
                    )
            
            # Show accumulated time
            for repo_path, duration in self.accumulated_time.items():
                if duration > 0:
                    files = self.file_changes.get(repo_path, 0)
                    table.add_row(
                        os.path.basename(repo_path),
                        "🟡 Accumulated",
                        f"{duration/60:.1f}m",
                        str(files)
                    )
            
            console.print(table)
    
    def stop_monitoring(self):
        """Stop the monitoring process."""
        self.running = False
        if self.observer:
            self.observer.stop()
            self.observer.join()
        console.print("[red]🛑 Activity Monitor Stopped[/red]")

class EnhancedChangeHandler(FileSystemEventHandler):
    """Enhanced file system event handler."""
    
    def __init__(self, tracker):
        self.tracker = tracker
    
    def on_modified(self, event):
        if event.is_directory:
            return
        
        # Skip certain file types
        skip_extensions = {'.pyc', '.log', '.tmp', '.swp', '.DS_Store'}
        skip_paths = {'.git', '__pycache__', 'node_modules', '.vscode'}
        
        if any(event.src_path.endswith(ext) for ext in skip_extensions):
            return
        
        if any(path_part in event.src_path for path_part in skip_paths):
            return
        
        repo_path = get_repo_root(event.src_path)
        if not repo_path:
            return
        
        now = time.time()
        start, last = self.tracker.active_sessions.get(repo_path, (None, None))
        
        # Update file change counter
        self.tracker.file_changes[repo_path] = self.tracker.file_changes.get(repo_path, 0) + 1
        
        if start is None:
            self.tracker.active_sessions[repo_path] = (now, now)
            console.print(f"[green]▶️  Started: {os.path.basename(repo_path)}[/green]")
        else:
            self.tracker.active_sessions[repo_path] = (start, now)

# Utility functions
def get_repo_root(path):
    """Get git repository root path."""
    try:
        if os.path.isfile(path):
            path = os.path.dirname(path)
        
        repo_root = subprocess.check_output([
            "git", "-C", path, "rev-parse", "--show-toplevel"
        ], stderr=subprocess.DEVNULL).decode().strip()
        
        return repo_root
    except subprocess.CalledProcessError:
        return None

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
                str(row['date']),
                f"{row['total_time']/3600:.1f}h",
                str(row['repos_count']),
                str(row['sessions_count']),
                str(row['files_changed']),
                str(row['lines_changed']),
                f"{row['avg_productivity']:.1f}/100"
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
        
        fig.add_trace(go.Scatter(
            x=df['date'],
            y=df['total_time']/3600,
            mode='lines+markers',
            name='Hours Worked',
            line=dict(color='blue')
        ))
        
        fig.add_trace(go.Scatter(
            x=df['date'],
            y=df['avg_productivity'],
            mode='lines+markers',
            name='Productivity Score',
            yaxis='y2',
            line=dict(color='green')
        ))
        
        fig.update_layout(
            title='📈 Productivity Trends',
            xaxis_title='Date',
            yaxis_title='Hours Worked',
            yaxis2=dict(
                title='Productivity Score',
                overlaying='y',
                side='right'
            )
        )
        
        # Save chart
        chart_path = os.path.join(LOG_DIR, 'productivity_chart.html')
        fig.write_html(chart_path)
        console.print(f"[green]📊 Chart saved to: {chart_path}[/green]")
    
    def export_data(self, format='csv', days=30):
        """Export activity data in various formats."""
        df = self.db.get_sessions(days)
        
        if df.empty:
            console.print("[yellow]No data to export[/yellow]")
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if format.lower() == 'csv':
            filepath = os.path.join(LOG_DIR, f'activity_export_{timestamp}.csv')
            df.to_csv(filepath, index=False)
        elif format.lower() == 'json':
            filepath = os.path.join(LOG_DIR, f'activity_export_{timestamp}.json')
            df.to_json(filepath, orient='records', date_format='iso')
        else:
            console.print("[red]Unsupported export format[/red]")
            return
        
        console.print(f"[green]📄 Data exported to: {filepath}[/green]")

# CLI Commands
def cmd_start():
    """Start activity monitoring."""
    tracker = EnhancedActivityTracker()
    observer = tracker.start_monitoring()
    
    try:
        while tracker.running:
            time.sleep(1)
    except KeyboardInterrupt:
        tracker.stop_monitoring()

def cmd_status():
    """Show current status and recent activity."""
    analytics = Analytics()
    analytics.generate_daily_report(7)

def cmd_report(days=30):
    """Generate detailed analytics report."""
    analytics = Analytics()
    analytics.generate_daily_report(days)
    analytics.generate_productivity_chart(days)

def cmd_export(format='csv', days=30):
    """Export activity data."""
    analytics = Analytics()
    analytics.export_data(format, days)

# Main CLI
def main():
    """Main CLI interface."""
    parser = argparse.ArgumentParser(
        description="🚀 Enhanced Activity Monitor - Track your coding productivity",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s start              Start monitoring activity
  %(prog)s status             Show current status
  %(prog)s report --days 30   Generate 30-day report
  %(prog)s export --format csv Export data as CSV
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Start command
    start_parser = subparsers.add_parser('start', help='Start activity monitoring')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Show current status')
    
    # Report command
    report_parser = subparsers.add_parser('report', help='Generate analytics report')
    report_parser.add_argument('--days', type=int, default=30, help='Number of days to include')
    
    # Export command
    export_parser = subparsers.add_parser('export', help='Export activity data')
    export_parser.add_argument('--format', choices=['csv', 'json'], default='csv', help='Export format')
    export_parser.add_argument('--days', type=int, default=30, help='Number of days to export')
    
    args = parser.parse_args()
    
    if args.command == 'start':
        cmd_start()
    elif args.command == 'status':
        cmd_status()
    elif args.command == 'report':
        cmd_report(args.days)
    elif args.command == 'export':
        cmd_export(args.format, args.days)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
