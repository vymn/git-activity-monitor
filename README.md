# Enhanced Activity Monitor

A powerful Python tool to automatically track coding productivity, analyze work patterns, and generate insightful reports from your Git repositories.

## 🌟 Features

### Core Monitoring

- **Real-time Activity Tracking**: Monitor file changes across multiple Git repositories
- **Smart Session Detection**: Automatically detect work sessions and idle periods
- **Git Integration**: Track commits, branches, and code statistics
- **Database Storage**: SQLite database for persistent data storage

### Analytics & Insights

- **Productivity Scoring**: Calculate productivity metrics based on time, files, and lines changed
- **Daily/Weekly Reports**: Detailed analytics with charts and visualizations
- **Goal Tracking**: Set and monitor coding goals (daily hours, weekly commits, etc.)
- **Trend Analysis**: Track productivity trends over time

### Rich CLI Interface

- **Colored Output**: Beautiful terminal interface with Rich library
- **Live Status**: Real-time monitoring dashboard
- **Multiple Commands**: start, status, report, export commands
- **Progress Tracking**: Visual progress bars and status updates

## 🚀 Installation

1. **Setup Script**:

   ```bash
   chmod +x setup.sh && ./setup.sh
   ```

2. **Manual Installation**:
   ```bash
   pip install -r requirements.txt
   ```

## 📊 Usage

### Start Monitoring

```bash
python main.py start
```

### Check Status

```bash
python main.py status
```

### Generate Reports

```bash
python main.py report --days 30
```

### Export Data

```bash
python main.py export --format csv
```

### Generate Markdown Summaries

```bash
python main.py summary --period week   # Weekly summary
python main.py summary --period month  # Monthly summary
```

- Creates comprehensive markdown reports
- Includes daily breakdowns and repository analysis
- Shows productivity insights and recommendations

## ⚙️ Configuration

- Edit `config.yaml` to change log directory, idle threshold, and scan interval.

## Requirements

See `requirements.txt` for Python dependencies.

## License

MIT
