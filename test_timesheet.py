#!/usr/bin/env python3
"""
Test the task extraction and markdown generation
"""

import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from activity_monitor.enhanced_tracker import (
    extract_task_name,
    EnhancedActivityTracker,
    DatabaseManager,
)



def test_task_extraction():
    """Test the task extraction function."""
    print("🧪 Testing Task Extraction...")

    test_commits = [
        "feat: Add user authentication system",
        "fix: Resolve database connection timeout issue",
        "PROJ-123: Implement payment gateway integration",
        "bug: Fix memory leak in image processing",
        "[FEAT-456] Create responsive dashboard layout",
        "Update login form validation rules",
        "Implement real-time chat functionality",
        "Fix bug in file upload component",
        "closes #42: Add dark mode support",
        "ABC-789: Refactor user management system",
        "chore: Update dependencies to latest versions",
        "Random commit message without structure",
    ]

    for commit in test_commits:
        task = extract_task_name(commit)
        print(f"  '{commit[:40]}...' -> '{task}'")


def test_markdown_generation():
    """Test generating a markdown session entry."""
    print("\n📝 Testing Markdown Generation...")

    # Get some real data from the database
    db = DatabaseManager()
    recent_sessions = db.get_sessions(1)  # Get recent sessions

    if recent_sessions.empty:
        print("❌ No recent sessions found in database")
        return

    # Test with the first session
    session = recent_sessions.iloc[0]
    print(
        f"Testing with session: {session['repo_name']} - {session['commit_message'][:50]}..."
    )

    # Create a test tracker
    tracker = EnhancedActivityTracker()

    # Simulate saving a session
    try:
        tracker.save_session_to_markdown(
            repo_path=session["repo_path"],
            duration=session["duration_seconds"],
            commit_info=(session["commit_hash"], session["commit_message"]),
        )
        print("✅ Markdown generation completed successfully")

        # Show the created file
        today_file = (
            f"/Users/vymn/Desktop/notes/time_log/{session['created_at'][:10]}.md"
        )
        if os.path.exists(today_file):
            print(f"📄 Generated file: {today_file}")
            print("\n📄 Sample content:")
            with open(today_file, "r") as f:
                lines = f.readlines()
                for i, line in enumerate(lines[:15]):  # Show first 15 lines
                    print(f"  {i+1:2d}: {line.rstrip()}")

    except Exception as e:
        print(f"❌ Error generating markdown: {e}")
        import traceback

        traceback.print_exc()


def main():
    """Main test function."""
    print("🚀 Task Extraction & Markdown Generation Test")
    print("=" * 50)

    test_task_extraction()
    test_markdown_generation()

    print("\n✨ Test complete!")


if __name__ == "__main__":
    main()
