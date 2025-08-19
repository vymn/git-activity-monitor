#!/usr/bin/env python3
"""
Test script to verify git stats parsing
"""

import subprocess
import sys
import os
import tempfile


def test_git_stats_parsing():
    """Test the git stats parsing logic"""

    # Test different git diff --stat outputs
    test_outputs = [
        # Single file, insertions only
        " test.py | 5 +++++\n 1 file changed, 5 insertions(+)",
        # Single file, deletions only
        " test.py | 3 ---\n 1 file changed, 3 deletions(-)",
        # Single file, mixed changes
        " test.py | 8 ++++----\n 1 file changed, 4 insertions(+), 4 deletions(-)",
        # Multiple files
        " file1.py | 10 ++++++++++\n file2.py | 5 ++---\n 2 files changed, 12 insertions(+), 3 deletions(-)",
        # No changes
        "",
    ]

    for i, output in enumerate(test_outputs):
        print(f"\nTest {i+1}: Testing output:")
        print(repr(output))

        lines_added = lines_deleted = files_changed = 0

        if output.strip():
            lines = output.strip().split("\n")

            for line in lines:
                if "file changed" in line or "files changed" in line:
                    parts = line.split(",")
                    print(f"  Parsing summary: {line}")

                    # Files changed
                    if "file" in parts[0]:
                        try:
                            files_changed = int(parts[0].split()[0])
                            print(f"    Files: {files_changed}")
                        except (ValueError, IndexError):
                            pass

                    # Insertions and deletions
                    for part in parts:
                        if "insertion" in part:
                            try:
                                lines_added = int(part.strip().split()[0])
                                print(f"    Added: {lines_added}")
                            except (ValueError, IndexError):
                                pass
                        elif "deletion" in part:
                            try:
                                lines_deleted = int(part.strip().split()[0])
                                print(f"    Deleted: {lines_deleted}")
                            except (ValueError, IndexError):
                                pass
                elif " | " in line and ("++" in line or "--" in line or "+-" in line):
                    if files_changed == 0:
                        files_changed += 1
                        print(f"  Found file line: {line}")

        print(
            f"  Result: {files_changed} files, {lines_added} added, {lines_deleted} deleted"
        )


if __name__ == "__main__":
    test_git_stats_parsing()
