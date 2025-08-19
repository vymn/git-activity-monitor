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

    # Seed activity_sessions with random data
    now = datetime.now()
    for i in range(50):  # Generate 50 sessions
        start_time = now - timedelta(
            days=random.randint(0, 30),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
        )
        end_time = start_time + timedelta(minutes=random.randint(10, 120))
        duration_seconds = int((end_time - start_time).total_seconds())
        repo_name = f"repo_{random.randint(1, 5)}"
        repo_path = f"/path/to/{repo_name}"
        commit_hash = f"{random.randint(1000000, 9999999):x}"
        commit_message = f"Commit message {i}"
        files_changed = random.randint(0, 10)
        lines_added = random.randint(0, 500)
        lines_deleted = random.randint(0, 500)
        productivity_score = random.uniform(50, 100)

        cursor.execute(
            """
            INSERT INTO activity_sessions 
            (repo_path, repo_name, start_time, end_time, duration_seconds, 
             commit_hash, commit_message, files_changed, lines_added, lines_deleted, productivity_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )

    # Seed daily_stats with aggregated data
    for i in range(30):  # Generate stats for the last 30 days
        date = (now - timedelta(days=i)).date()
        total_time_seconds = random.randint(3600, 14400)  # Between 1 and 4 hours
        repos_worked_on = random.randint(1, 5)
        commits_made = random.randint(1, 10)
        files_changed = random.randint(5, 50)
        lines_changed = random.randint(100, 1000)
        avg_session_duration = random.uniform(
            600, 3600
        )  # Between 10 minutes and 1 hour
        productivity_score = random.uniform(50, 100)

        cursor.execute(
            """
            INSERT INTO daily_stats 
            (date, total_time_seconds, repos_worked_on, commits_made, files_changed, lines_changed, avg_session_duration, productivity_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                date,
                total_time_seconds,
                repos_worked_on,
                commits_made,
                files_changed,
                lines_changed,
                avg_session_duration,
                productivity_score,
            ),
        )

    conn.commit()
    conn.close()


if __name__ == "__main__":
    seed_test_database()
    print(f"Test database seeded successfully at {test_db_path}")
