## Troubleshooting Guide

Quick lookup of common symptoms → causes → fixes.

### Slack
- `invalid_auth`
  - Cause: `SLACK_BOT_TOKEN` not set/expired
  - Fix: `export SLACK_BOT_TOKEN="xoxb-..."`; test with `auth_test()`; persist in `~/.bashrc`

- `missing_scope` (e.g., `channels:history`)
  - Cause: Polling mode needs read scopes
  - Fix: Add scopes: `channels:history`, `groups:history`, `mpim:history`, `im:history`; reinstall app

- `channel_not_found`
  - Cause: Using channel name with APIs needing ID; bot not invited; private channel without scope
  - Fix: Resolve ID via `conversations.list`, invite bot, or switch to `#general`

- Files upload failures / deprecations
  - Use `files_upload_v2` with channel ID; avoid `files.upload`

### Camera
- `Control VerticalFlip is not advertised`
  - Fix: Use `transform` in Picamera2 config; avoid direct control

- No images, keeps starting/stopping
  - Check SSH connection drops; use `screen` to persist

### Runtime
- Script dies after SSH disconnect
  - Use `screen -S timelapse ...`; reattach with `screen -r timelapse`

- High CPU / slow
  - Lower resolution, increase interval, disable extras

### Diagnostics
- Verify Slack auth: `python3 -c "from slack_sdk import WebClient; import os; print(WebClient(token=os.environ['SLACK_BOT_TOKEN']).auth_test())"`
- Check process: `ps aux | grep local_tp.py`
- Check logs in configured log file


