#!/usr/bin/env python3
"""
Generate a sample timesheet from recent database data
"""

import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from activity_monitor.enhanced_tracker import EnhancedActivityTracker, DatabaseManager
from datetime import datetime, timedelta


def generate_sample_timesheet():
    """Generate a sample timesheet for testing."""
    print("📋 Generating Sample Daily Timesheet...")

    db = DatabaseManager()
    tracker = EnhancedActivityTracker()

    # Get some recent sessions to create a realistic timesheet
    sessions = db.get_sessions(30)

    if sessions.empty:
        print("❌ No sessions found")
        return

    # Take first 5 sessions to simulate a day's work
    sample_sessions = sessions.head(5)

    print(f"Creating timesheet with {len(sample_sessions)} sample sessions...")

    for _, session in sample_sessions.iterrows():
        print(
            f"  Processing: {session['repo_name']} - {session['commit_message'][:50]}..."
        )

        # Generate markdown for this session
        tracker.save_session_to_markdown(
            repo_path=session["repo_path"],
            duration=session["duration_seconds"],
            commit_info=(session["commit_hash"], session["commit_message"]),
        )

    # Show the final timesheet
    today_file = f"/Users/vymn/Desktop/notes/time_log/{datetime.now().date()}.md"
    if os.path.exists(today_file):
        print(f"\n📄 Generated timesheet: {today_file}")
        print("\n" + "=" * 60)
        print("SAMPLE TIMESHEET CONTENT:")
        print("=" * 60)

        with open(today_file, "r") as f:
            content = f.read()
            # Show first 40 lines
            lines = content.split("\n")
            for i, line in enumerate(lines[:40]):
                print(f"{i+1:2d}: {line}")

            if len(lines) > 40:
                print(f"    ... and {len(lines) - 40} more lines")

        print("\n" + "=" * 60)
        print("END OF SAMPLE")
        print("=" * 60)
    else:
        print("❌ Timesheet file not found")


def main():
    """Main function."""
    print("🚀 Daily Timesheet Generator")
    print("=" * 50)

    generate_sample_timesheet()

    print("\n✨ Complete! Check your log directory for the timesheet.")


if __name__ == "__main__":
    main()
