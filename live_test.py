#!/usr/bin/env python3
"""
Live monitoring test - shows real-time file detection
"""

import os
import sys
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from activity_monitor.config import load_config

config = load_config()
MONITOR_PATH = os.path.expanduser(config.get("monitor_path", "~/developement"))


class TestHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if not event.is_directory:
            print(f"🔵 File modified: {event.src_path}")

    def on_created(self, event):
        if not event.is_directory:
            print(f"🟢 File created: {event.src_path}")

    def on_deleted(self, event):
        if not event.is_directory:
            print(f"🔴 File deleted: {event.src_path}")


def main():
    print(f"🔍 Live File Monitor Test")
    print(f"📁 Monitoring: {MONITOR_PATH}")
    print(f"✨ Edit any file in your git repositories to see detection...")
    print(f"⌨️  Press Ctrl+C to stop\n")

    if not os.path.exists(MONITOR_PATH):
        print(f"❌ Path doesn't exist: {MONITOR_PATH}")
        return

    observer = Observer()
    handler = TestHandler()
    observer.schedule(handler, MONITOR_PATH, recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Stopping monitor...")
        observer.stop()

    observer.join()
    print("✅ Monitor stopped")


if __name__ == "__main__":
    main()
