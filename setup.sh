#!/bin/bash
# Setup script for Activity Monitor

echo "🚀 Setting up Enhanced Activity Monitor..."

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip3 install -r requirements.txt

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p ~/.config/activity-monitor
mkdir -p ~/Desktop/notes/time_log

# Copy config if it doesn't exist
if [ ! -f ~/.config/activity-monitor/config.yaml ]; then
    echo "⚙️ Setting up configuration..."
    cp config.yaml ~/.config/activity-monitor/
    echo "   Config copied to ~/.config/activity-monitor/config.yaml"
    echo "   Edit this file to customize your settings"
fi

echo "✅ Setup complete!"
echo ""
echo "Usage:"
echo "  python main.py start    # Start monitoring"
echo "  python main.py status   # Check status"
echo "  python main.py report   # Generate reports"
echo "  python main.py export   # Export data"
