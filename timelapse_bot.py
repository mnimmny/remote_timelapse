#!/usr/bin/env python3
"""
Slack Bot Controller for Raspberry Pi Timelapse
Handles Slack commands and communicates with timelapse functionality
"""

import os
import sys
import time
import json
import logging
import threading
import queue
from typing import Dict, Any, Optional
from datetime import datetime

# Import existing timelapse functionality
from local_tp import PiCameraController, SlackNotifier

# Slack SDK imports
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse


class TimelapseBot:
    """Slack bot controller for timelapse camera system"""
    
    def __init__(self, config_path: str = "config.yaml"):
        """Initialize the bot with configuration"""
        self.config_path = config_path
        self.logger = self._setup_logging()
        
        # Initialize camera controller
        self.camera_controller = PiCameraController()
        
        # Bot state
        self.is_running = False
        self.command_queue = queue.Queue()
        self.socket_client = None
        
        # Command patterns
        self.command_patterns = {
            'photo': r'@bot\s+photo',
            'status': r'@bot\s+status',
            'start': r'@bot\s+start\s+(\d+)s?\s+(\d+)(s|m|h)?',
            'stop': r'@bot\s+stop',
            'help': r'@bot\s+help'
        }
        
        self.logger.info("Timelapse bot initialized")
    
    def _setup_logging(self) -> logging.Logger:
        """Setup logging for the bot"""
        logger = logging.getLogger('timelapse_bot')
        logger.setLevel(logging.INFO)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Format
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(formatter)
        
        logger.addHandler(console_handler)
        return logger
    
    def start_socket_mode(self):
        """Start Slack Socket Mode for real-time events"""
        try:
            # Get bot token from environment
            bot_token = os.environ.get('SLACK_BOT_TOKEN')
            app_token = os.environ.get('SLACK_APP_TOKEN')  # Socket Mode token
            
            if not bot_token:
                self.logger.error("SLACK_BOT_TOKEN environment variable not set")
                return False
            
            if not app_token:
                self.logger.warning("SLACK_APP_TOKEN not set, using polling mode instead")
                return self.start_polling_mode()
            
            # Initialize Socket Mode client
            self.socket_client = SocketModeClient(
                app_token=app_token,
                web_client=WebClient(token=bot_token)
            )
            
            # Set up event handlers
            self.socket_client.socket_mode_request_listeners.append(self.handle_socket_mode_request)
            
            # Start the client
            self.socket_client.connect()
            self.is_running = True
            
            self.logger.info("Socket Mode client started successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start Socket Mode: {e}")
            return False
    
    def start_polling_mode(self):
        """Start polling mode for Slack commands (fallback)"""
        try:
            bot_token = os.environ.get('SLACK_BOT_TOKEN')
            if not bot_token:
                self.logger.error("SLACK_BOT_TOKEN environment variable not set")
                return False
            
            self.web_client = WebClient(token=bot_token)
            self.is_running = True
            
            # Start polling thread
            polling_thread = threading.Thread(target=self._poll_for_commands)
            polling_thread.daemon = True
            polling_thread.start()
            
            self.logger.info("Polling mode started successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start polling mode: {e}")
            return False
    
    def handle_socket_mode_request(self, client: SocketModeClient, req: SocketModeRequest):
        """Handle Socket Mode requests"""
        try:
            if req.type == "events_api":
                # Handle events
                event = req.payload.get("event", {})
                if event.get("type") == "app_mention":
                    self._process_mention(event)
                
                # Acknowledge the request
                client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
                
        except Exception as e:
            self.logger.error(f"Error handling socket mode request: {e}")
    
    def _poll_for_commands(self):
        """Poll Slack for new messages (fallback mode)"""
        last_timestamp = None
        
        while self.is_running:
            try:
                # Get recent messages from the channel
                channel = self.camera_controller.slack.channel
                
                response = self.web_client.conversations_history(
                    channel=channel,
                    limit=10,
                    oldest=last_timestamp
                )
                
                if response["ok"]:
                    messages = response["messages"]
                    for message in messages:
                        if self._is_bot_mention(message):
                            self._process_mention(message)
                    
                    if messages:
                        last_timestamp = messages[0]["ts"]
                
                time.sleep(5)  # Poll every 5 seconds
                
            except Exception as e:
                self.logger.error(f"Error polling for commands: {e}")
                time.sleep(10)
    
    def _is_bot_mention(self, message: Dict[str, Any]) -> bool:
        """Check if message mentions the bot"""
        text = message.get("text", "")
        return "@bot" in text.lower() and message.get("user") != self.web_client.auth_test()["user_id"]
    
    def _process_mention(self, event_or_message: Dict[str, Any]):
        """Process a bot mention"""
        try:
            text = event_or_message.get("text", "")
            channel = event_or_message.get("channel", "")
            user = event_or_message.get("user", "")
            
            self.logger.info(f"Processing mention: {text}")
            
            # Parse command
            command = self._parse_command(text)
            if command:
                # Execute command
                result = self._execute_command(command, channel, user)
                self._send_response(result, channel)
            
        except Exception as e:
            self.logger.error(f"Error processing mention: {e}")
    
    def _parse_command(self, text: str) -> Optional[Dict[str, Any]]:
        """Parse command from message text"""
        import re
        
        text = text.lower().strip()
        
        # Check each command pattern
        for cmd_type, pattern in self.command_patterns.items():
            match = re.search(pattern, text)
            if match:
                if cmd_type == "start":
                    interval = int(match.group(1))
                    duration_str = match.group(2)
                    duration_unit = match.group(3) or "s"
                    
                    # Convert duration to seconds
                    duration = int(duration_str)
                    if duration_unit == "m":
                        duration *= 60
                    elif duration_unit == "h":
                        duration *= 3600
                    
                    return {
                        "type": cmd_type,
                        "interval": interval,
                        "duration": duration
                    }
                else:
                    return {"type": cmd_type}
        
        return None
    
    def _execute_command(self, command: Dict[str, Any], channel: str, user: str) -> Dict[str, str]:
        """Execute a parsed command"""
        cmd_type = command["type"]
        
        try:
            if cmd_type == "photo":
                # Take a single photo
                success = self.camera_controller.capture_image()
                if success:
                    return {
                        "text": f"📸 Photo captured successfully!",
                        "status": "success"
                    }
                else:
                    return {
                        "text": f"❌ Failed to capture photo",
                        "status": "error"
                    }
            
            elif cmd_type == "status":
                # Get current status
                status_info = self._get_status()
                return {
                    "text": f"📊 *Camera Status*\n{status_info}",
                    "status": "info"
                }
            
            elif cmd_type == "start":
                # Start timelapse
                interval = command["interval"]
                duration = command["duration"]
                
                # Update config temporarily
                self.camera_controller.config['timelapse']['interval'] = interval
                self.camera_controller.config['timelapse']['duration'] = duration
                
                # Start timelapse in background thread
                timelapse_thread = threading.Thread(
                    target=self.camera_controller.run_timelapse
                )
                timelapse_thread.daemon = True
                timelapse_thread.start()
                
                return {
                    "text": f"🎬 Timelapse started!\n• Interval: {interval}s\n• Duration: {duration}s",
                    "status": "success"
                }
            
            elif cmd_type == "stop":
                # Stop timelapse (would need to implement stop mechanism)
                return {
                    "text": f"⏹️ Stop command received (not yet implemented)",
                    "status": "warning"
                }
            
            elif cmd_type == "help":
                # Show help
                help_text = self._get_help_text()
                return {
                    "text": help_text,
                    "status": "info"
                }
            
        except Exception as e:
            self.logger.error(f"Error executing command {cmd_type}: {e}")
            return {
                "text": f"❌ Error executing command: {str(e)}",
                "status": "error"
            }
    
    def _get_status(self) -> str:
        """Get current camera and system status"""
        try:
            status_lines = []
            
            # Camera status
            if self.camera_controller.camera:
                status_lines.append("• Camera: ✅ Connected")
            else:
                status_lines.append("• Camera: ❌ Not connected")
            
            # Timelapse status
            if hasattr(self.camera_controller, 'start_time') and self.camera_controller.start_time:
                elapsed = time.time() - self.camera_controller.start_time
                remaining = self.camera_controller.config['timelapse']['duration'] - elapsed
                status_lines.append(f"• Timelapse: 🎬 Running ({elapsed:.1f}s elapsed, {remaining:.1f}s remaining)")
            else:
                status_lines.append("• Timelapse: ⏸️ Not running")
            
            # Image count
            if hasattr(self.camera_controller, 'image_count'):
                status_lines.append(f"• Images captured: {self.camera_controller.image_count}")
            
            # Slack status
            if self.camera_controller.slack.enabled:
                status_lines.append("• Slack notifications: ✅ Enabled")
            else:
                status_lines.append("• Slack notifications: ❌ Disabled")
            
            return "\n".join(status_lines)
            
        except Exception as e:
            return f"Error getting status: {str(e)}"
    
    def _get_help_text(self) -> str:
        """Get help text for available commands"""
        return """🤖 *Timelapse Bot Commands*

• `@bot photo` - Take a single photo
• `@bot status` - Show camera and system status  
• `@bot start 60s 30m` - Start timelapse (interval duration)
• `@bot stop` - Stop current timelapse
• `@bot help` - Show this help message

*Examples:*
• `@bot start 30s 1h` - Take photo every 30 seconds for 1 hour
• `@bot start 5s 10m` - Take photo every 5 seconds for 10 minutes"""
    
    def _send_response(self, result: Dict[str, str], channel: str):
        """Send response back to Slack"""
        try:
            if hasattr(self, 'web_client'):
                client = self.web_client
            elif self.socket_client:
                client = self.socket_client.web_client
            else:
                self.logger.error("No Slack client available")
                return
            
            # Determine color based on status
            color_map = {
                "success": "good",
                "error": "danger", 
                "warning": "warning",
                "info": "#36a64f"
            }
            
            color = color_map.get(result["status"], "#36a64f")
            
            response = client.chat_postMessage(
                channel=channel,
                text=result["text"],
                attachments=[{
                    "color": color,
                    "fallback": result["text"]
                }]
            )
            
            if response["ok"]:
                self.logger.info(f"Response sent successfully: {result['status']}")
            else:
                self.logger.error(f"Failed to send response: {response.get('error')}")
                
        except Exception as e:
            self.logger.error(f"Error sending response: {e}")
    
    def run(self):
        """Main bot run loop"""
        self.logger.info("Starting Timelapse Bot...")
        
        # Try Socket Mode first, fallback to polling
        if not self.start_socket_mode():
            if not self.start_polling_mode():
                self.logger.error("Failed to start bot in any mode")
                return False
        
        try:
            # Keep running
            while self.is_running:
                time.sleep(1)
                
        except KeyboardInterrupt:
            self.logger.info("Bot stopped by user")
        except Exception as e:
            self.logger.error(f"Bot error: {e}")
        finally:
            self.cleanup()
        
        return True
    
    def cleanup(self):
        """Cleanup resources"""
        self.is_running = False
        if self.socket_client:
            self.socket_client.close()
        self.logger.info("Bot cleanup completed")


def main():
    """Main entry point"""
    print("Timelapse Bot Controller")
    print("========================")
    
    # Check environment
    if not os.environ.get('SLACK_BOT_TOKEN'):
        print("Error: SLACK_BOT_TOKEN environment variable not set")
        sys.exit(1)
    
    # Initialize and run bot
    bot = TimelapseBot()
    
    try:
        success = bot.run()
        if success:
            print("Bot completed successfully")
        else:
            print("Bot failed")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\nBot interrupted by user")
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
