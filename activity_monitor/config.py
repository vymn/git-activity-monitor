"""
Configuration management for Activity Monitor
"""

import os
import yaml
from pathlib import Path

DEFAULT_CONFIG = {
    "log_dir": "~/Desktop/notes/time_log",
    "idle_threshold": 300,
    "scan_interval": 3,
    "monitor_path": "~/development",
    "database": {"backup_interval": 86400, "max_backups": 7},  # 24 hours
    "notifications": {"enabled": True, "sound": True, "show_productivity": True},
    "productivity": {
        "minimum_session_time": 60,  # seconds
        "file_change_weight": 5,
        "line_change_weight": 0.1,
    },
    "goals": {"daily_hours": 8, "weekly_commits": 20, "monthly_repos": 2},
}


def load_config():
    """Load configuration from file or create default."""
    config_paths = [
        Path.home() / ".config" / "activity-monitor" / "config.yaml",
        Path(__file__).parent.parent / "config.yaml",
    ]

    for config_path in config_paths:
        if config_path.exists():
            with open(config_path) as f:
                user_config = yaml.safe_load(f)


            # Merge with defaults
            config = DEFAULT_CONFIG.copy()
            config.update(user_config)
            return config

    # No config found, return defaults
    return DEFAULT_CONFIG


def save_config(config, path=None):
    """Save configuration to file."""
    if path is None:
        config_dir = Path.home() / ".config" / "activity-monitor"
        config_dir.mkdir(parents=True, exist_ok=True)
        path = config_dir / "config.yaml"

    with open(path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, indent=2)
