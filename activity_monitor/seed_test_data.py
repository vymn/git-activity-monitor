import sqlite3
from datetime import datetime, timedelta
import random

# Path to the test database
test_db_path = "/Users/vymn/Desktop/notes/time_log/activity_monitor_test.db"


# Create and seed the test database
def seed_test_database():
    conn = sqlite3.connect(test_db_path)
    cursor = conn.cursor()

    # Create tables if they don't exist
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

    # Clear existing data first
    cursor.execute("DELETE FROM activity_sessions")
    cursor.execute("DELETE FROM daily_stats")

    # Seed activity_sessions with random data spread across 30 days
    now = datetime.now()
    for _ in range(150):  # Generate 150 sessions (5 per day average)
        # Pick a random day in the last 30 days
        days_ago = random.randint(0, 29)
        session_date = now - timedelta(days=days_ago)

        # Create session times within that specific day
        start_time = session_date.replace(
            hour=random.randint(8, 20),  # Work hours 8 AM to 8 PM
            minute=random.randint(0, 59),
            second=0,
            microsecond=0,
        )
        end_time = start_time + timedelta(
            minutes=random.randint(15, 180)
        )  # 15 min to 3 hours
        duration_seconds = int((end_time - start_time).total_seconds())

        repo_name = f"repo_{random.randint(1, 5)}"
        repo_path = f"/path/to/{repo_name}"
        commit_hash = f"{random.randint(1000000, 9999999):x}"

        # More realistic commit messages with task names
        task_types = [
            "feat: Add user authentication system",
            "fix: Resolve database connection timeout issue",
            "PROJ-123: Implement payment gateway integration",
            "bug: Fix memory leak in image processing",
            "chore: Update dependencies to latest versions",
            "docs: Add API documentation for user endpoints",
            "refactor: Optimize database query performance",
            "test: Add unit tests for user service",
            "[FEAT-456] Create responsive dashboard layout",
            "Update login form validation rules",
            "Implement real-time chat functionality",
            "Fix bug in file upload component",
            "Add dark mode theme support",
            "Optimize image compression algorithm",
            "Create user profile management page",
            "Fix responsive design on mobile devices",
            "Implement search functionality",
            "Update API error handling",
            "Add email notification system",
            "Refactor authentication middleware",
        ]
        commit_message = random.choice(task_types)
        files_changed = random.randint(1, 15)
        lines_added = random.randint(5, 300)
        lines_deleted = random.randint(0, 150)
        productivity_score = random.uniform(40, 100)

        cursor.execute(
            """
            INSERT INTO activity_sessions 
            (repo_path, repo_name, start_time, end_time, duration_seconds, 
             commit_hash, commit_message, files_changed, lines_added, lines_deleted, productivity_score, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                repo_path,
                repo_name,
                start_time,
                end_time,
                duration_seconds,
                commit_hash,
                commit_message,
                files_changed,
                lines_added,
                lines_deleted,
                productivity_score,
                start_time,  # Use start_time as created_at to spread across dates
            ),
        )

    # Remove the daily_stats seeding since it will be calculated from activity_sessions
    # The analytics functions will calculate this on-the-fly from the session data

    print(f"✅ Seeded {150} sessions across {30} days")
    print(f"📅 Date range: {(now - timedelta(days=29)).date()} to {now.date()}")

    # Show sample of what was created
    cursor.execute(
        """
        SELECT DATE(created_at) as date, COUNT(*) as sessions, SUM(duration_seconds)/3600.0 as hours
        FROM activity_sessions 
        GROUP BY DATE(created_at) 
        ORDER BY date DESC 
        LIMIT 5
    """
    )
    sample_data = cursor.fetchall()
    print("\n📊 Sample daily data:")
    for date, sessions, hours in sample_data:
        print(f"  {date}: {sessions} sessions, {hours:.1f} hours")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    seed_test_database()
    print(f"Test database seeded successfully at {test_db_path}")
