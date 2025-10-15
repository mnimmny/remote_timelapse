#!/bin/bash
# Start camera preview in screen session

echo "🎥 Starting Camera Preview..."
echo "=" * 40

# Check if config.yaml exists
if [ ! -f "config.yaml" ]; then
    echo "❌ Error: config.yaml not found!"
    echo "Make sure you're running this from the timelapse directory"
    exit 1
fi

# Check if screen is available
if ! command -v screen &> /dev/null; then
    echo "❌ Error: screen not installed"
    echo "Install with: sudo apt install screen"
    exit 1
fi

# Check if Flask is installed
if ! python3 -c "import flask" &> /dev/null; then
    echo "📦 Installing Flask..."
    pip3 install flask
fi

# Check if OpenCV is installed
if ! python3 -c "import cv2" &> /dev/null; then
    echo "📦 Installing OpenCV..."
    pip3 install opencv-python
fi

# Kill existing preview session if running
screen -S camera-preview -X quit 2>/dev/null

# Start preview in screen session
echo "🚀 Starting preview in screen session..."
screen -dmS camera-preview python3 preview_web.py

# Wait a moment for startup
sleep 2

# Get Pi IP
PI_IP=$(hostname -I | awk '{print $1}')

echo "✅ Preview started successfully!"
echo ""
echo "🌐 Access at: http://$PI_IP:5000"
echo ""
echo "📋 Commands:"
echo "  screen -r camera-preview    # Reattach to preview"
echo "  screen -ls                  # List all sessions"
echo "  nano config.yaml            # Edit config"
echo ""
echo "📝 Workflow:"
echo "  1. Open http://$PI_IP:5000 in your browser"
echo "  2. Edit config.yaml with nano/vim/etc"
echo "  3. Save file - changes appear automatically!"
echo "  4. Detach from screen with Ctrl+A, D"
echo ""
echo "⏹️  To stop: screen -r camera-preview, then Ctrl+C"
