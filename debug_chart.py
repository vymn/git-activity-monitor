# #!/usr/bin/env python3
# """
# Debug script specifically for chart generation issues
# """

# import os
# import sys
# import sqlite3
# import pandas as pd
# from datetime import datetime, timedelta

# # Add current directory to path
# sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# from activity_monitor.config import load_config
# from activity_monitor.enhanced_tracker import DatabaseManager, EnhancedActivityTracker

# def debug_database_data():
#     """Check what data exists in the database."""
#     print("🔍 Debugging database data...")

#     db = DatabaseManager()

#     # Get DB path from config
#     from activity_monitor.enhanced_tracker import DB_PATH

#     print(f"📁 Database path: {DB_PATH}")

#     if not os.path.exists(DB_PATH):
#         print("❌ Database file doesn't exist!")
#         return False

#     # Check raw data
#     conn = sqlite3.connect(DB_PATH)

#     # Count total records
#     cursor = conn.cursor()
#     cursor.execute("SELECT COUNT(*) FROM activity_sessions")
#     total_count = cursor.fetchone()[0]
#     print(f"📊 Total records in database: {total_count}")

#     if total_count == 0:
#         print("❌ No data found in database!")
#         conn.close()
#         return False

#     # Check recent data
#     cursor.execute("""
#         SELECT created_at, repo_path, duration_seconds, productivity_score
#         FROM activity_sessions
#         ORDER BY created_at DESC
#         LIMIT 10
#     """)
#     recent_data = cursor.fetchall()

#     print(f"\n📅 Recent 10 records:")
#     for record in recent_data:
#         created_at, repo_path, duration, productivity = record
#         print(f"  {created_at} | {os.path.basename(repo_path)} | {duration}s | score: {productivity}")

#     # Check date range
#     cursor.execute("""
#         SELECT MIN(created_at) as earliest, MAX(created_at) as latest
#         FROM activity_sessions
#     """)
#     date_range = cursor.fetchone()
#     print(f"\n📅 Date range: {date_range[0]} to {date_range[1]}")

#     conn.close()
#     return True

# def debug_daily_stats():
#     """Test the get_daily_stats function."""
#     print("\n🔍 Testing get_daily_stats function...")

#     db = DatabaseManager()

#     # Test with different day ranges
#     for days in [7, 30, 90]:
#         print(f"\n📊 Testing {days} days:")
#         df = db.get_daily_stats(days)

#         if df.empty:
#             print(f"  ❌ No data returned for {days} days")
#             continue

#         print(f"  ✅ Found {len(df)} days of data")
#         print(f"  📅 Date range: {df['date'].min()} to {df['date'].max()}")

#         # Show sample data
#         print("  Sample data:")
#         for _, row in df.head(3).iterrows():
#             print(f"    {row['date']}: {row['total_time']/3600:.1f}h, productivity: {row['avg_productivity']:.2f}")

# def debug_chart_generation():
#     """Test chart generation step by step."""
#     print("\n🔍 Testing chart generation...")

#     # Use Analytics class instead of EnhancedActivityTracker
#     from activity_monitor.enhanced_tracker import Analytics
#     analytics = Analytics()

#     # Test with 30 days
#     df = analytics.db.get_daily_stats(30)

#     if df.empty:
#         print("❌ No data available for chart generation")
#         return

#     print(f"✅ Data retrieved: {len(df)} days")
#     print(f"📊 Columns: {list(df.columns)}")
#     print(f"📊 Data types:\n{df.dtypes}")

#     # Check for null values
#     print(f"\n🔍 Checking for null values:")
#     for col in df.columns:
#         null_count = df[col].isnull().sum()
#         if null_count > 0:
#             print(f"  ⚠️  {col}: {null_count} null values")

#     # Check data ranges
#     print(f"\n📊 Data ranges:")
#     print(f"  Total time: {df['total_time'].min()/3600:.1f}h - {df['total_time'].max()/3600:.1f}h")
#     print(f"  Productivity: {df['avg_productivity'].min():.2f} - {df['avg_productivity'].max():.2f}")

#     # Generate chart
#     try:
#         analytics.generate_productivity_chart(30)
#         print("✅ Chart generated successfully")

#         # Check file size
#         chart_path = os.path.join(os.path.expanduser("~/Desktop/notes/time_log"), "productivity_chart.html")
#         if os.path.exists(chart_path):
#             file_size = os.path.getsize(chart_path) / (1024 * 1024)  # MB
#             print(f"📊 Chart file size: {file_size:.2f} MB")

#             # Read first few lines to check content
#             with open(chart_path, 'r') as f:
#                 first_lines = [f.readline().strip() for _ in range(10)]

#             print("📄 Chart file starts with:")
#             for i, line in enumerate(first_lines[:5]):
#                 if line:
#                     print(f"  {i+1}: {line[:100]}...")
#         else:
#             print("❌ Chart file not found")

#     except Exception as e:
#         print(f"❌ Chart generation failed: {e}")
#         import traceback
#         traceback.print_exc()

# def main():
#     """Main debug function."""
#     print("🚀 Activity Monitor Chart Debug Tool")
#     print("=" * 50)

#     # Step 1: Check database data
#     if not debug_database_data():
#         return

#     # Step 2: Test daily stats function
#     debug_daily_stats()

#     # Step 3: Test chart generation
#     debug_chart_generation()

#     print("\n✨ Debug complete!")

# if __name__ == "__main__":
#     main()
