#!/usr/bin/env python3
"""
Debug script to test Activity Monitor functionality
"""

import os
import sys
import time
import subprocess
from pathlib import Path

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from activity_monitor.config import load_config

    print("✅ Config module imported successfully")
    config = load_config()
    print(f"✅ Config loaded: monitor_path = {config.get('monitor_path')}")

except Exception as e:
    print(f"❌ Config import failed: {e}")
    sys.exit(1)

try:
    from activity_monitor.enhanced_tracker import (
        DatabaseManager,
        EnhancedActivityTracker,
    )

    print("✅ Tracker modules imported successfully")
except Exception as e:
    print(f"❌ Tracker import failed: {e}")
    print("Let's check what's available...")
    try:
        import activity_monitor.enhanced_tracker as tracker

        print("Basic import works, checking attributes...")
        print(dir(tracker))
    except Exception as e2:
        print(f"❌ Even basic import failed: {e2}")
    sys.exit(1)

# Test database
try:
    db = DatabaseManager()
    print("✅ Database initialized successfully")

    # Check if there's any data
    sessions = db.get_sessions(7)
    print(f"📊 Sessions in last 7 days: {len(sessions)}")
    if not sessions.empty:
        print("Recent sessions:")
        print(sessions[["repo_name", "duration_seconds", "created_at"]].head())
    else:
        print("No sessions found in database")

except Exception as e:
    print(f"❌ Database test failed: {e}")

# Test git detection in current directory
print(f"\n🔍 Testing Git detection in current directory...")
current_dir = os.getcwd()
try:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        cwd=current_dir,
    )
    if result.returncode == 0:
        repo_root = result.stdout.strip()
        print(f"✅ Current directory is in git repo: {repo_root}")

        # Get current commit
        commit_result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=repo_root
        )
        if commit_result.returncode == 0:
            print(f"📝 Current commit: {commit_result.stdout.strip()[:8]}")

    else:
        print("❌ Current directory is not in a git repo")

except Exception as e:
    print(f"❌ Git detection failed: {e}")

print(f"\n🚀 Ready to test live monitoring!")
print("Edit a file in your git repository and I'll try to detect it...")

# Simple file monitoring test
monitor_path = config.get("monitor_path", "~/developement")
monitor_path = os.path.expanduser(monitor_path)
print(f"Monitoring: {monitor_path}")

if os.path.exists(monitor_path):
    print("✅ Monitor path exists")
    print("Try editing a file in one of your git repos and see if it gets detected!")
else:
    print(f"❌ Monitor path doesn't exist: {monitor_path}")
