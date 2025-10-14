## Agent Guide

Purpose: Give LLMs and automations a concise, structured map of the repo, stable entrypoints, and common tasks.

### Repository Map
- `local_tp.py`: Main timelapse controller and `SlackNotifier`
- `timelapse_bot.py`: Slack bot for interactive control
- `config.yaml`: User configuration (camera, timelapse, slack, system)
- `requirements.txt`: Python dependencies (SDKs; picamera2 via apt)
- `README.md`: Human quickstart and usage

### Entrypoints and Contracts
- `PiCameraController`
  - `run_timelapse()`: Start timelapse according to `config.yaml`
  - `capture_image(...)`: Capture single image to disk
  - Fields used by bot: `config`, `image_count`, `start_time`
- `SlackNotifier`
  - `send_start_notification(...)`, `send_progress_update(...)`, `send_photo_notification(...)`, `send_stop_notification(...)`
  - Uses Slack SDK; uploads via `files_upload_v2`; requires channel ID resolution
- `TimelapseBot`
  - Commands: `@bot photo|status|start <interval> <duration>|stop|help`
  - Prefers Socket Mode; falls back to polling (needs history scopes)

### Configuration Schema (minimal)
```yaml
camera:
  resolution: { width: int, height: int }
  vflip: bool
  hflip: bool
  focus:
    mode: "auto|manual|continuous"
    lens_position: float  # 0.0-1000.0 for manual focus
  exposure:
    mode: "auto|manual|sport|night"
    shutter_speed: int    # microseconds
    iso: int              # 100-3200
    gain: float           # 0.0-16.0
  noise_reduction: bool
  stabilization: bool

timelapse:
  interval: int   # seconds
  duration: int   # seconds
  output_dir: str

slack:
  enabled: bool
  bot_token: "${SLACK_BOT_TOKEN}"
  channel: "#channel-name"
  notifications:
    errors: bool
    progress_updates: bool
    progress_interval: int
    send_photos: bool
    photo_interval: int

system:
  log_level: "INFO|DEBUG|..."
  log_file: str
```

### Environment Variables
- `SLACK_BOT_TOKEN` (required for Slack features)
- `SLACK_APP_TOKEN` (optional; enable Socket Mode)

### Common Automations
- Start timelapse (headless): `screen -S timelapse python3 local_tp.py`
- Start bot (Socket Mode): `screen -S timelapse-bot python3 timelapse_bot.py`
- Verify Slack auth: `python3 -c "from slack_sdk import WebClient; import os; print(WebClient(token=os.environ['SLACK_BOT_TOKEN']).auth_test())"`

### Error→Fix Lookup (quick)
- `invalid_auth`: export `SLACK_BOT_TOKEN` again; token expired or not set
- `channel_not_found`: use channel ID; invite bot; fix config channel name
- `missing_scope`: add listed scopes; reinstall app
- `files.upload deprecated`: use `files_upload_v2` (already implemented)

### Mock Mode (Non-Pi Development)
For testing without Raspberry Pi hardware:

```python
# Mock PiCameraController for non-Pi environments
class MockPiCameraController:
    def __init__(self, config_path="config.yaml"):
        self.config = self._load_config(config_path)
        self.camera = None
        self.image_count = 0
        self.start_time = None
        self.slack = SlackNotifier(self.config.get('slack', {}), self.config, logging.getLogger())
    
    def run_timelapse(self):
        print("Mock: Starting timelapse...")
        # Simulate timelapse without actual camera
    
    def capture_image(self, filename):
        print(f"Mock: Would capture {filename}")
        return True
```

### Assumptions
- Camera control requires Raspberry Pi OS with `python3-picamera2` installed via apt
- Slack files remain private to workspace (no public URLs)

### Security Notes
- Do not commit secrets; use env vars
- Avoid `files_sharedPublicURL` for images; use direct upload to channel ID

### Prompts Examples
- "Start a 30-minute timelapse every 5s": Update `timelapse` in `config.yaml` and run `local_tp.py`
- "Enable low-res Slack photos": set `slack.notifications.send_photos: true` and intervals
- "Set up macro photography for 10cm focus": set `camera.focus.mode: "manual"` and `lens_position: 10.0`


