#!/usr/bin/env python3
"""
Web-based camera preview with auto-reloading config
Perfect for headless Pi Zero W
"""

from flask import Flask, Response
import cv2
import os
import time
from datetime import datetime
import sys

# Import the existing PiCameraController from local_tp.py
from local_tp import PiCameraController

app = Flask(__name__)
controller = None
last_config_mtime = 0

def check_config_changes():
    """Check if config.yaml has been modified"""
    global last_config_mtime
    try:
        current_mtime = os.path.getmtime('config.yaml')
        if current_mtime != last_config_mtime:
            last_config_mtime = current_mtime
            return True
    except Exception as e:
        print(f"Error checking config file: {e}")
    return False

def initialize_controller():
    """Initialize the PiCameraController for preview mode"""
    global controller
    try:
        controller = PiCameraController()
        
        # Setup camera for preview (reuse existing _setup_camera method)
        if not controller._setup_camera():
            print("Failed to initialize camera")
            return False
        
        print("Camera controller initialized successfully")
        return True
        
    except Exception as e:
        print(f"Error initializing controller: {e}")
        return False

def reload_controller_config():
    """Reload config and reapply camera settings using controller method"""
    global controller
    try:
        if controller:
            if controller.reload_config():
                print(f"Config reloaded at {datetime.now().strftime('%H:%M:%S')}")
                return True
            else:
                print("Failed to reload config")
                return False
    except Exception as e:
        print(f"Error reloading config: {e}")
        return False

def generate_frames():
    """Generate video frames for web stream"""
    frame_count = 0
    while True:
        try:
            # Check for config changes every 30 frames (~1 second at 30fps)
            if frame_count % 30 == 0:
                if check_config_changes():
                    print("Config changed, reapplying camera settings...")
                    reload_controller_config()
            
            # Use the controller's camera to capture frames
            if controller and controller.camera:
                frame = controller.camera.capture_array()
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            else:
                print("Controller or camera not available")
                break
            
            frame_count += 1
            
        except Exception as e:
            print(f"Error generating frame: {e}")
            break

@app.route('/video_feed')
def video_feed():
    """Video streaming route"""
    return Response(generate_frames(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/')
def index():
    """Main page with preview"""
    pi_ip = os.popen('hostname -I').read().strip()
    return f'''
    <html>
    <head>
        <title>Camera Preview</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            .info {{ background: #f0f0f0; padding: 10px; border-radius: 5px; margin: 10px 0; }}
            .status {{ color: green; font-weight: bold; }}
        </style>
    </head>
    <body>
        <h1>📷 Camera Preview</h1>
        
        <div class="info">
            <p><strong>Pi IP:</strong> {pi_ip}</p>
            <p><strong>Status:</strong> <span class="status">Live</span></p>
            <p><strong>Config Auto-Reload:</strong> Every ~1 second</p>
        </div>
        
        <img src="/video_feed" width="640" height="480" style="border: 2px solid #ccc; border-radius: 5px;">
        
        <div class="info">
            <h3>How to Use:</h3>
            <ol>
                <li>Edit <code>config.yaml</code> in your preferred editor</li>
                <li>Save the file</li>
                <li>Changes appear automatically in ~1 second</li>
                <li>No need to restart the preview!</li>
            </ol>
            
            <h3>Common Settings to Adjust:</h3>
            <ul>
                <li><strong>Focus:</strong> <code>camera.focus.lens_position</code> (10.0 for 10cm)</li>
                <li><strong>Brightness:</strong> <code>camera.brightness</code> (-1.0 to 1.0)</li>
                <li><strong>Contrast:</strong> <code>camera.contrast</code> (0.0 to 2.0)</li>
                <li><strong>Saturation:</strong> <code>camera.saturation</code> (0.0 to 2.0)</li>
                <li><strong>Sharpness:</strong> <code>camera.sharpness</code> (0.0 to 2.0)</li>
            </ul>
        </div>
        
        <p><em>Press Ctrl+C in terminal to stop preview</em></p>
    </body>
    </html>
    '''

@app.route('/status')
def status():
    """API endpoint to check status"""
    return {
        'status': 'running',
        'camera_configured': controller is not None and controller.camera is not None,
        'config_last_modified': datetime.fromtimestamp(last_config_mtime).isoformat() if last_config_mtime else None
    }

if __name__ == '__main__':
    print("🎥 Starting Camera Preview Server...")
    print("=" * 50)
    
    # Check if config.yaml exists
    if not os.path.exists('config.yaml'):
        print("❌ Error: config.yaml not found!")
        print("Make sure you're running this from the same directory as config.yaml")
        sys.exit(1)
    
    # Initial camera setup
    if not initialize_controller():
        print("❌ Failed to initialize camera")
        sys.exit(1)
    
    # Get Pi IP
    try:
        pi_ip = os.popen('hostname -I').read().strip()
        print(f"🌐 Preview URL: http://{pi_ip}:5000")
    except:
        print("🌐 Preview URL: http://localhost:5000")
    
    print("📝 Edit config.yaml and save - changes appear automatically!")
    print("⏹️  Press Ctrl+C to stop")
    print("=" * 50)
    
    try:
        app.run(host='0.0.0.0', port=5000, debug=False)
    except KeyboardInterrupt:
        print("\n🛑 Stopping preview...")
    finally:
        if controller:
            controller.cleanup()
            print("✅ Camera stopped")
