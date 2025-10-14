# Raspberry Pi Camera 3 Controller

A Python script for controlling Raspberry Pi Camera 3 on Pi Zero W using the picamera2 module with YAML configuration.

## Docs
- See `AGENT.md` for repo map, interfaces, config schema, and mock mode
- See `TROUBLESHOOTING.md` for symptom→fix lookups and diagnostics
- See `DECISIONS.md` for architecture/API/security rationale
- See `CONTRIBUTING.md` for setup, dev workflow, and style

## Features

- **Easy Configuration**: YAML-based configuration file for all camera settings
- **Timelapse Capture**: Automated timelapse photography with configurable intervals
- **System Monitoring**: Temperature and disk space monitoring
- **Image Management**: Automatic cleanup of old images
- **Video Creation**: Optional video creation from captured images
- **Slack Notifications**: Real-time notifications with Slack SDK bot integration
- **Low-res Photo Updates**: Periodic low-resolution photos sent to Slack
- **Slack Bot Control**: Interactive Slack commands to control camera remotely
- **System Monitoring**: Temperature and disk space alerts
- **Robust Error Handling**: Comprehensive logging and error recovery
- **Pi Zero W Optimized**: Settings optimized for Pi Zero W performance

### Slack Bot Commands
- `@bot photo` - Take a single photo
- `@bot status` - Show camera and system status
- `@bot start 30s 10m` - Start timelapse (interval duration)
- `@bot stop` - Stop current timelapse
- `@bot help` - Show available commands

## Requirements

- Raspberry Pi Zero W (or compatible Pi)
- Raspberry Pi Camera 3
- Raspberry Pi OS (Bullseye or newer)
- Python 3.7+

## Installation

1. **Update your Pi and install dependencies:**
   ```bash
   sudo apt update
   sudo apt install -y python3-picamera2 python3-pip
   sudo apt install -y ffmpeg  # Optional, for video creation
   sudo apt install -y screen  # For persistent sessions
   ```

2. **Install Python dependencies:**
   ```bash
   pip3 install -r requirements.txt
   ```

3. **Setup Slack bot (optional):**
   - Go to your Slack workspace
   - Create a new app or use an existing one
   - In *OAuth & Permissions* under *Bot Token Scopes*, add these OAuth scopes:
     - `chat:write` (for sending messages)
     - `files:write` (for uploading files)
     - `channels:read` (for channel ID resolution in file uploads)
     - `app_mentions:read` (for bot command processing)
     - `channels:history` (only for polling mode fallback; not needed for Socket Mode)
     - `groups:history` (for private channel polling)
     - `mpim:history` (for multi-party DM polling)
     - `im:history` (for direct message polling)
   - Invite the bot to your target channel (e.g., `#timelapse`)
   - For Socket Mode (recommended), also add:
     - Go to *Socket Mode* and enable it
     - Copy the App-Level Token (starts with `xapp-`)
     - Set: `export SLACK_APP_TOKEN="xapp-your-app-token"`
   - Install the app to your workspace
   - Copy the Bot User OAuth Token (starts with `xoxb-`)
   - Set the environment variable: `export SLACK_BOT_TOKEN="xoxb-your-bot-token"`

4. **Docs quick links:** See `AGENT.md`, `TROUBLESHOOTING.md`, `DECISIONS.md`, `CONTRIBUTING.md` for deeper details.

4. **Enable camera interface:**
   ```bash
   sudo raspi-config
   # Navigate to: Interface Options > Camera > Enable
   ```

5. **Clone or download the script files:**
   ```bash
   # Make sure config.yaml and local_tp.py are in the same directory
   ```

## Configuration

Edit `config.yaml` to customize your camera settings:

### Camera Settings
- **Resolution**: Image resolution (default: 1920x1080)
- **Quality**: JPEG quality (1-100)
- **Exposure Mode**: Auto, night, sports, etc.
- **AWB Mode**: Auto white balance settings
- **Focus Mode**: Auto, manual, continuous
- **Image Orientation**: Vertical and horizontal flip options

### Macro Photography Settings
- **Manual Focus**: Set `focus.mode: "manual"` and `lens_position: 10.0` for 10cm focus
- **Lens Position**: Range 0.0-1000.0 (lower values = closer focus)
- **Manual Exposure**: Set `exposure.mode: "manual"` for precise control
- **Shutter Speed**: Set in microseconds (e.g., 1000 = 1/1000s)
- **ISO**: Set sensitivity (100-3200)
- **Gain**: Additional gain control (0.0-16.0)
- **Noise Reduction**: Enable for better macro detail
- **Stabilization**: Enable for close-up work

### Timelapse Settings
- **Interval**: Seconds between captures (default: 5)
- **Duration**: Total timelapse duration in seconds (default: 3600 = 1 hour)
- **Output Directory**: Where to save images (supports `~` and environment variables)
- **Video Creation**: Enable/disable automatic video creation

### System Settings
- **Log Level**: DEBUG, INFO, WARNING, ERROR
- **Log File**: Path to log file (supports `~` and environment variables)
- **Temperature Warning**: CPU temperature threshold
- **Disk Space Warning**: Free space threshold

### Slack Notifications
- **Bot Token**: Uses `SLACK_BOT_TOKEN` environment variable
- **Channel**: Target Slack channel (optional)
- **Error Notifications**: Enable/disable error alerts
- **Progress Updates**: Periodic progress reports with progress bars
- **Photo Updates**: Low-resolution photos uploaded to Slack
- **Threading**: Start notification creates thread, updates reply in thread
- **System Alerts**: Temperature and disk space warnings

## Usage

### Basic Usage
```bash
python3 local_tp.py
```

### Run in Background
```bash
nohup python3 local_tp.py > output.log 2>&1 &
```

## File Structure

```
timelapse/
├── local_tp.py          # Main camera controller script
├── config.yaml          # Configuration file
├── requirements.txt     # Python dependencies
└── README.md           # This file
```

## Output

- **Images**: Saved to the configured output directory with timestamp filenames
- **Logs**: Written to `/home/pi/camera.log` and console
- **Video**: Optional MP4 video created from captured images
- **Slack Notifications**: Real-time updates sent to your Slack channel

## Running the Script

### Timelapse Mode
For automated timelapse capture:

```bash
# Start timelapse session
screen -S timelapse python3 local_tp.py

# Detach from session (Ctrl+A then D)
# Or just close your SSH terminal

# Later, reconnect to your session
screen -r timelapse

# View all sessions
screen -ls

# Terminate session (when attached): Ctrl+C
# Or kill session entirely:
screen -S timelapse -X quit
```

### Slack Bot Mode
For interactive Slack control:

```bash
# Set required environment variables
export SLACK_BOT_TOKEN="xoxb-your-bot-token"
export SLACK_APP_TOKEN="xapp-your-app-token"  # Optional, for Socket Mode

# Start bot in background
screen -S timelapse-bot python3 timelapse_bot.py

# Or run in foreground for testing
python3 timelapse_bot.py
```

**Bot Features:**
- Real-time Slack commands via Socket Mode (recommended)
- Fallback polling mode if Socket Mode unavailable
- Commands: `@bot photo`, `@bot status`, `@bot start 30s 10m`, `@bot stop`, `@bot help`

Note: If `SLACK_BOT_TOKEN` is missing or invalid, the bot will exit immediately (in `screen` this appears as "[screen is terminating]").

### Alternative: Background Process
```bash
# Run in background (less interactive)
nohup python3 local_tp.py > timelapse.log 2>&1 &

# Check if running
ps aux | grep local_tp.py

# Stop the process
pkill -f local_tp.py
```

> **Note**: SSH connections can drop due to network issues. Screen sessions persist through disconnections, so you can reconnect and monitor your timelapse anytime.

## Troubleshooting
(See also: `TROUBLESHOOTING.md` for a full guide.)

### Camera Not Found
- Ensure camera is properly connected
- Check camera interface is enabled: `sudo raspi-config`
- Verify camera detection: `libcamera-hello --list-cameras`

### Permission Issues
- Run with appropriate permissions for file creation
- Ensure output directory is writable

### Performance Issues
- Reduce image resolution for Pi Zero W
- Increase capture interval
- Monitor CPU temperature

### Low Disk Space
- Enable automatic cleanup in config
- Reduce max_images setting
- Use external storage

### Slack Notifications Not Working
- Verify `SLACK_BOT_TOKEN` is set and valid
- Check internet connectivity
- Ensure Slack app has proper permissions
- Ensure the bot is invited to the target channel
- Check logs for Slack API errors

## Configuration Examples

### High Quality Timelapse
```yaml
camera:
  resolution:
    width: 3280
    height: 2464
  quality: 95
timelapse:
  interval: 10
  duration: 7200  # 2 hours
```

### Fast Motion Capture
```yaml
camera:
  resolution:
    width: 1280
    height: 720
  quality: 80
timelapse:
  interval: 1
  duration: 300  # 5 minutes
```

### Night Photography
```yaml
camera:
  exposure_mode: "night"
  awb_mode: "tungsten"
  brightness: 0.2
timelapse:
  interval: 30
  duration: 10800  # 3 hours
```

### Macro Photography (10-20cm focus)
```yaml
camera:
  resolution:
    width: 1920
    height: 1080
  quality: 95
  focus:
    mode: "manual"
    lens_position: 10.0  # 10cm focus distance
  exposure:
    mode: "manual"
    shutter_speed: 1000  # 1/1000s for sharp macro shots
    iso: 100  # Low ISO for detail
    gain: 1.0
  noise_reduction: true
  stabilization: true
  sharpness: 1.2  # Enhanced sharpness for macro
timelapse:
  interval: 5
  duration: 1800  # 30 minutes
```

### Flipped Camera Setup
```yaml
camera:
  vflip: true   # Flip image vertically
  hflip: false  # Keep horizontal orientation
  resolution:
    width: 1920
    height: 1080
```

### Slack Notifications Setup
```yaml
slack:
  enabled: true
  bot_token: "${SLACK_BOT_TOKEN}"  # Uses environment variable
  channel: "#timelapse"
  username: "Pi Camera Bot"
  notifications:
    errors: true
    progress_updates: true
    progress_interval: 10
    send_photos: true
    photo_interval: 5
    photo_quality: 30
    temperature_alerts: true
    disk_space_alerts: true
```

### Path Configuration
The script supports flexible path configuration using environment variables and home directory expansion:

```yaml
timelapse:
  output_dir: "~/timelapse_images"  # Expands to /home/username/timelapse_images

storage:
  backup_path: "~/backup"  # Expands to /home/username/backup

system:
  log_file: "~/camera.log"  # Expands to /home/username/camera.log
```

You can also use environment variables:
```yaml
timelapse:
  output_dir: "$HOME/timelapse_images"  # Uses $HOME environment variable
```

## Error Recovery

The script is designed to handle failures gracefully:

- **Individual image failures**: Continues with next capture
- **System health issues**: Sends warnings but continues
- **Network issues**: Slack failures don't stop timelapse
- **Power loss**: Images captured so far are preserved
- **Camera errors**: Logs error and stops gracefully

## License

This project is open source. Feel free to modify and distribute.

## Troubleshooting

### Common Issues

#### Slack Authentication Errors
If you see `invalid_auth` errors:

```bash
# Check if token is set
echo $SLACK_BOT_TOKEN

# If empty, re-export it
export SLACK_BOT_TOKEN="xoxb-your-actual-token"

# Test the token works
python3 -c "from slack_sdk import WebClient; client = WebClient(token='$SLACK_BOT_TOKEN'); print(client.auth_test())"
```

**Common causes:**
- SSH session disconnected and environment variable lost
- Terminal session restarted without preserving exports
- Token expired and needs refresh from Slack

#### Persistent Environment Variables
For long-running sessions, add to your shell profile:

```bash
# Add to ~/.bashrc for persistence
echo 'export SLACK_BOT_TOKEN="xoxb-your-token"' >> ~/.bashrc
source ~/.bashrc

# Or create a startup script
cat > start_timelapse.sh << 'EOF'
#!/bin/bash
export SLACK_BOT_TOKEN="xoxb-your-token"
screen -S timelapse python3 local_tp.py
EOF
chmod +x start_timelapse.sh
```

#### Camera Issues
- **"Camera not found"**: Enable camera interface with `sudo raspi-config`
- **"Permission denied"**: Add user to video group: `sudo usermod -a -G video $USER`
- **"Control not advertised"**: Update Pi OS: `sudo apt update && sudo apt upgrade`

#### Performance Issues
- **High CPU usage**: Reduce image resolution in config.yaml
- **Memory issues**: Enable swap: `sudo dphys-swapfile swapoff && sudo dphys-swapfile swapon`
- **Temperature warnings**: Add heatsink or reduce capture frequency

## Support
(See also: `CONTRIBUTING.md` and `DECISIONS.md`.)

For issues and questions:
1. Check the log file for error messages
2. Verify camera connection and configuration
3. Ensure all dependencies are installed
4. Check system resources (temperature, disk space)
5. Verify Slack bot token and permissions