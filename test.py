#!/usr/bin/env python3
"""
Test script for Activity Monitor
Run basic tests to ensure everything is working
"""

import os
import sys
import subprocess
from pathlib import Path


def test_imports():
    """Test if all required packages can be imported."""
    required_packages = [
        "watchdog",
        "yaml",
        "rich",
        "pandas",
        "matplotlib",
        "plotly",
        "psutil",
    ]

    failed_imports = []

    for package in required_packages:
        try:
            __import__(package)
            print(f"✅ {package}")
        except ImportError:
            failed_imports.append(package)
            print(f"❌ {package}")

    if failed_imports:
        print(f"\n⚠️  Missing packages: {', '.join(failed_imports)}")
        print("Run: pip install -r requirements.txt")
        return False

    print("\n🎉 All packages imported successfully!")
    return True


def test_config():
    """Test configuration loading."""
    try:
        from activity_monitor.config import load_config

        config = load_config()
        print("✅ Configuration loaded successfully")
        print(f"   Monitor path: {config.get('monitor_path', 'Not set')}")
        print(f"   Log directory: {config.get('log_dir', 'Not set')}")
        return True
    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        return False


def test_database():
    """Test database initialization."""
    try:
        from activity_monitor.enhanced_tracker import DatabaseManager

        db = DatabaseManager()
        print("✅ Database initialized successfully")
        return True
    except Exception as e:
        print(f"❌ Database test failed: {e}")
        return False


def test_git():
    """Test Git functionality."""
    try:
        result = subprocess.run(["git", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ Git available: {result.stdout.strip()}")
            return True
        else:
            print("❌ Git not available")
            return False
    except Exception as e:
        print(f"❌ Git test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("🧪 Testing Activity Monitor Setup...\n")

    tests = [
        ("Package Imports", test_imports),
        ("Configuration", test_config),
        ("Database", test_database),
        ("Git Availability", test_git),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n--- Testing {test_name} ---")
        if test_func():
            passed += 1

    print(f"\n📊 Test Results: {passed}/{total} passed")

    if passed == total:
        print("🎉 All tests passed! Activity Monitor is ready to use.")
        print("\nNext steps:")
        print("1. python main.py start    # Start monitoring")
        print("2. python main.py status   # Check status")
    else:
        print("⚠️  Some tests failed. Please fix the issues above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
