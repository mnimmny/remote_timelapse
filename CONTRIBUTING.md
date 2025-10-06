## Contributing

### Setup
1. Python deps: `pip3 install -r requirements.txt`
2. Picamera2 (on Pi): `sudo apt install -y python3-picamera2`
3. Slack tokens: `export SLACK_BOT_TOKEN=...` (and optionally `SLACK_APP_TOKEN=...`)

### Development
- Run timelapse: `python3 local_tp.py`
- Run bot: `python3 timelapse_bot.py`
- Use `screen` for long runs: `screen -S timelapse ...`

### Code Style
- Prefer readable names, minimal nesting, early returns
- Avoid catching without handling; keep comments for non-obvious rationale

### Testing without Camera
- You can run the bot on non-Pi hardware; camera calls will be no-ops
- Consider mocking `PiCameraController` for unit tests

### PR Checklist
- Update docs if behavior/config changes
- Add rationale to `DECISIONS.md` for notable choices


