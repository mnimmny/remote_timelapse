#!/usr/bin/env python3
"""
Raspberry Pi Camera 3 Controller
Optimized for Pi Zero W with picamera2 module
"""

import os
import sys
import time
import yaml
import logging
import shutil
import json
import base64
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

try:
    from picamera2 import Picamera2
    from libcamera import controls
except ImportError:
    print("Error: picamera2 module not found. Please install it with:")
    print("sudo apt update && sudo apt install -y python3-picamera2")
    sys.exit(1)

try:
    import requests
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
except ImportError as e:
    print("Error: Required modules not found. Please install with:")
    print("pip3 install requests slack-sdk")
    sys.exit(1)


class SlackNotifier:
    """Slack SDK notification handler"""
    
    def __init__(self, config: Dict[str, Any], full_config: Dict[str, Any], logger: logging.Logger):
        self.config = config
        self.full_config = full_config
        self.logger = logger
        self.enabled = config.get('enabled', False)
        self.bot_token = config.get('bot_token', '')
        self.channel = config.get('channel', '#general')
        self.username = config.get('username', 'Pi Camera Bot')
        self.icon_emoji = config.get('icon_emoji', ':camera:')
        self.notifications = config.get('notifications', {})
        
        # Initialize Slack client
        if self.enabled:
            if not self.bot_token:
                self.logger.warning("Slack notifications enabled but no bot token provided")
                self.enabled = False
            else:
                try:
                    self.client = WebClient(token=self.bot_token)
                    # Test the connection and get workspace info
                    auth_response = self.client.auth_test()
                    self.logger.info(f"Slack client initialized successfully for workspace: {auth_response.get('team', 'Unknown')}")
                    
                    # Validate channel exists and bot has access
                    try:
                        channel_id = self._convert_channel_name_to_id(self.channel)
                        channel_info = self.client.conversations_info(channel=channel_id)
                        if not channel_info["ok"]:
                            self.logger.warning(f"Channel {self.channel} (ID: {channel_id}) not accessible")
                        else:
                            self.logger.info(f"Successfully verified access to channel {self.channel} (ID: {channel_id})")
                    except SlackApiError as e:
                        self.logger.warning(f"Could not verify channel {self.channel}: {e.response.get('error', 'Unknown error')}")
                        
                except SlackApiError as e:
                    self.logger.error(f"Failed to initialize Slack client: {e}")
                    self.logger.error(f"Auth error details: {e.response.get('error', 'Unknown error')}")
                    self.enabled = False
        
        # Thread management
        self.thread_ts = None  # Track thread timestamp for timelapse updates
        
        # Rate limiting for notifications
        self.last_progress_notification = 0
        self.last_photo_notification = 0
        self.last_health_warning = 0
        self.health_warning_cooldown = 300  # 5 minutes
    
    def _convert_channel_name_to_id(self, channel_name: str) -> str:
        """Convert channel name to channel ID"""
        if not self.enabled:
            return channel_name
            
        try:
            # Remove # prefix if present
            clean_name = channel_name.replace('#', '')
            
            # Get channel ID
            conversations_response = self.client.conversations_list()
            if conversations_response.get("ok"):
                for channel in conversations_response["channels"]:
                    if channel.get("name") == clean_name:
                        channel_id = channel.get("id")
                        self.logger.debug(f"Converted #{clean_name} to ID {channel_id}")
                        return channel_id
                
                self.logger.warning(f"Channel #{clean_name} not found in workspace")
                return channel_name
            else:
                self.logger.warning("Failed to get channels list")
                return channel_name
                
        except Exception as e:
            self.logger.warning(f"Failed to convert channel name to ID: {e}")
            return channel_name
    
    def _send_message(self, text: str, title: str = None, color: str = None, 
                     image_data: bytes = None, image_filename: str = None, 
                     in_thread: bool = False) -> bool:
        """Send a message to Slack via SDK"""
        if not self.enabled:
            return False
        
        try:
            # Prepare message payload
            message_kwargs = {
                "channel": self.channel,
                "text": text,
                "username": self.username,
                "icon_emoji": self.icon_emoji
            }
            
            # Add thread timestamp if replying to thread
            if in_thread and self.thread_ts:
                message_kwargs["thread_ts"] = self.thread_ts
            
            # Add attachments for rich formatting
            if title or color:
                attachment = {
                    "fallback": text,
                    "color": color or "good",
                    "fields": [
                        {
                            "title": title or "Camera Status",
                            "value": "",  # Empty value to avoid duplication
                            "short": False
                        }
                    ],
                    "ts": int(time.time())
                }
                message_kwargs["attachments"] = [attachment]
            
            # Handle image uploads
            if image_data and image_filename:
                return self._upload_image(image_data, image_filename, text, in_thread)
            else:
                # Send text message
                response = self.client.chat_postMessage(**message_kwargs)
                return response["ok"]
                
        except SlackApiError as e:
            self.logger.error(f"Slack API error: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Failed to send Slack message: {e}")
            return False
    
    def _upload_image(self, image_data: bytes, filename: str, text: str, in_thread: bool = False) -> bool:
        """Upload an image to Slack using files_upload_v2"""
        try:
            import io
            
            # Use files_upload_v2 method directly
            self.logger.info(f"Uploading {filename} ({len(image_data)} bytes) using files_upload_v2")
            
            # Convert channel name to channel ID
            channel_id = self._convert_channel_name_to_id(self.channel)
            if channel_id != self.channel:  # Successfully got ID
                self.logger.info(f"Using channel ID {channel_id} for upload to {self.channel}")
            
            upload_args = {
                "file": io.BytesIO(image_data),
                "filename": filename,
                "title": filename,
                "channels": [channel_id],  # Use channel ID
                "initial_comment": text
            }
            
            # Add thread timestamp if in thread
            if in_thread and self.thread_ts:
                upload_args["thread_ts"] = self.thread_ts
            
            # Upload directly to channel using files_upload_v2
            self.logger.info(f"Calling files_upload_v2 with args: {list(upload_args.keys())}")
            
            response = self.client.files_upload_v2(**upload_args)
            
            # Handle SlackResponse object properly
            self.logger.info(f"files_upload_v2 response type: {type(response)}")
            self.logger.info(f"Response ok: {response.get('ok', 'No ok field')}")
            
            if response.get("ok"):
                self.logger.info(f"Successfully uploaded image {filename} to channel")
                return True
            else:
                self.logger.error(f"files_upload_v2 failed: {response.get('error', 'Unknown error')}")
                self.logger.error(f"Full response: {response}")
                return self._upload_image_fallback(image_data, filename, text, in_thread)
                
        except SlackApiError as e:
            self.logger.error(f"Slack API error uploading image: {e}")
            return self._upload_image_fallback(image_data, filename, text, in_thread)
        except Exception as e:
            self.logger.error(f"Failed to upload image: {e}")
            return self._upload_image_fallback(image_data, filename, text, in_thread)
    
    def _upload_image_fallback(self, image_data: bytes, filename: str, text: str, in_thread: bool = False) -> bool:
        """Fallback: Upload image as base64 data URL"""
        try:
            import base64
            
            # Encode image as base64
            image_b64 = base64.b64encode(image_data).decode('utf-8')
            
            # Create an enhanced text notification with emoji and details
            enhanced_text = f"{text}\n"
            enhanced_text += f"📸 *File:* `{filename}`\n"
            enhanced_text += f"📏 *Size:* {len(image_data):,} bytes\n"
            enhanced_text += f"🔗 *Note:* Enable `files:write` scope for image uploads"
            
            # Send as regular message
            return self._send_message(
                text=enhanced_text,
                title="Photo Update",
                color="#36a64f",  # Green color since photo was captured
                in_thread=in_thread
            )
            
        except Exception as e:
            self.logger.error(f"Fallback image notification failed: {e}")
            return False
    
    def send_error(self, message: str, error: Exception = None) -> bool:
        """Send error notification"""
        if not self.notifications.get('errors', True):
            return False
        
        text = f"🚨 *Error*: {message}"
        if error:
            text += f"\n```{str(error)}```"
        
        return self._send_message(
            text=text,
            title="Camera Error",
            color="danger",
            in_thread=False  # Go to main channel
        )
    
    def send_warning(self, message: str) -> bool:
        """Send warning notification"""
        if not self.notifications.get('warnings', True):
            return False
        
        text = f"⚠️ *Warning*: {message}"
        return self._send_message(
            text=text,
            title="Camera Warning",
            color="warning",
            in_thread=False  # Go to main channel
        )
    
    def send_start_notification(self) -> bool:
        """Send timelapse start notification (creates thread)"""
        if not self.notifications.get('start_stop', True):
            return False
        
        text = f"🎬 *Timelapse Started*\n"
        text += f"• Interval: {self.full_config.get('timelapse', {}).get('interval', 'N/A')}s\n"
        text += f"• Duration: {self.full_config.get('timelapse', {}).get('duration', 'N/A')}s\n"
        text += f"• Output: {self.full_config.get('timelapse', {}).get('output_dir', 'N/A')}"
        
        try:
            # Send the start message and capture the thread timestamp
            response = self.client.chat_postMessage(
                channel=self.channel,
                text=text,
                attachments=[
                    {
                        "fallback": text,
                        "color": "good",
                        "fields": [
                            {
                                "title": "Timelapse Started",
                                "value": "",
                                "short": False
                            }
                        ],
                        "ts": int(time.time())
                    }
                ]
            )
            
            if response["ok"]:
                # Capture the thread timestamp from the response
                self.thread_ts = response["ts"]
                self.logger.info("Timelapse started notification sent")
                return True
            else:
                self.logger.error(f"Failed to send start notification: {response.get('error', 'Unknown error')}")
                return False
                
        except SlackApiError as e:
            self.logger.error(f"Slack API error sending start notification: {e}")
            self.logger.error(f"Error details: {e.response.get('error', 'Unknown error')}")
            if hasattr(e.response, 'headers') and 'retry-after' in e.response.headers:
                self.logger.error(f"Rate limited. Retry after: {e.response.headers['retry-after']} seconds")
            return False
    
    def send_stop_notification(self, image_count: int, duration: float) -> bool:
        """Send timelapse stop notification (in thread)"""
        if not self.notifications.get('start_stop', True):
            return False
        
        text = f"✅ *Timelapse Completed*\n"
        text += f"• Images captured: {image_count}\n"
        text += f"• Duration: {duration:.1f}s\n"
        text += f"• Average interval: {duration/max(image_count, 1):.1f}s"
        
        return self._send_message(
            text=text,
            title="Timelapse Completed",
            color="good",
            in_thread=True  # Reply in thread
        )
    
    def send_progress_update(self, image_count: int, elapsed: float, remaining: float) -> bool:
        """Send progress update notification with progress bar"""
        if not self.notifications.get('progress_updates', True):
            return False
        
        interval = self.notifications.get('progress_interval', 10)
        if image_count % interval != 0:
            return False
        
        # Calculate progress percentage
        total_duration = elapsed + remaining
        progress_percent = (elapsed / total_duration) * 100 if total_duration > 0 else 0
        
        # Create progress bar
        progress_bar = self._create_progress_bar(progress_percent)
        
        text = f"📊 *Timelapse Progress*\n"
        text += f"```\n{progress_bar} {progress_percent:.1f}%\n```\n"
        text += f"• Images: {image_count}\n"
        text += f"• Elapsed: {elapsed:.1f}s\n"
        text += f"• Remaining: {remaining:.1f}s"
        
        return self._send_message(
            text=text,
            title="Timelapse Progress",
            color="#36a64f",
            in_thread=True  # Reply in thread
        )
    
    def _create_progress_bar(self, percentage: float, width: int = 20) -> str:
        """Create a text-based progress bar"""
        filled = int((percentage / 100) * width)
        empty = width - filled
        
        # Use different characters for filled and empty parts
        bar = "█" * filled + "░" * empty
        return f"[{bar}]"
    
    def send_photo_notification(self, image_data: bytes, image_count: int) -> bool:
        """Send photo notification with low-res image"""
        if not self.notifications.get('send_photos', True):
            return False
        
        # Rate limiting: only send every N images
        interval = self.notifications.get('photo_interval', 5)
        if image_count % interval != 0:
            return False
        
        # Additional rate limiting: don't send more than once per 2 minutes
        current_time = time.time()
        if current_time - self.last_photo_notification < 120:
            return False
        
        self.last_photo_notification = current_time
        
        text = f"📸 *Photo Update*\n"
        text += f"• Image #{image_count} captured\n"
        text += f"• Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        filename = f"timelapse_{image_count:04d}.jpg"
        return self._send_message(
            text=text,
            title="Photo Update",
            color="#36a64f",
            image_data=image_data,
            image_filename=filename,
            in_thread=True  # Reply in thread
        )
    
    def send_temperature_alert(self, temperature: float) -> bool:
        """Send temperature alert"""
        if not self.notifications.get('temperature_alerts', True):
            return False
        
        # Rate limiting: don't send more than once per 5 minutes
        current_time = time.time()
        if current_time - self.last_health_warning < self.health_warning_cooldown:
            return False
        
        self.last_health_warning = current_time
        
        text = f"🌡️ *High Temperature Alert*\n"
        text += f"• CPU Temperature: {temperature:.1f}°C\n"
        text += f"• Threshold: {self.config.get('system', {}).get('temperature_warning', 80)}°C"
        
        return self._send_message(
            text=text,
            title="Temperature Alert",
            color="warning",
            in_thread=False  # Go to main channel
        )
    
    def send_disk_space_alert(self, free_space_mb: float) -> bool:
        """Send disk space alert"""
        if not self.notifications.get('disk_space_alerts', True):
            return False
        
        # Rate limiting: don't send more than once per 5 minutes
        current_time = time.time()
        if current_time - self.last_health_warning < self.health_warning_cooldown:
            return False
        
        self.last_health_warning = current_time
        
        text = f"💾 *Low Disk Space Alert*\n"
        text += f"• Free space: {free_space_mb:.1f}MB\n"
        text += f"• Threshold: {self.config.get('system', {}).get('low_disk_warning', 100)}MB"
        
        return self._send_message(
            text=text,
            title="Disk Space Alert",
            color="warning",
            in_thread=False  # Go to main channel
        )


class PiCameraController:
    """Main camera controller class for Raspberry Pi Camera 3"""
    
    def __init__(self, config_path: str = "config.yaml"):
        """Initialize the camera controller with configuration"""
        self.config = self._load_config(config_path)
        self.camera = None
        self.logger = self._setup_logging()
        self.image_count = 0
        self.start_time = None
        
        # Initialize Slack notifier
        slack_config = self.config.get('slack', {})
        self.slack = SlackNotifier(slack_config, self.config, self.logger)
        
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        try:
            with open(config_path, 'r') as file:
                config = yaml.safe_load(file)
            
            # Expand paths with ~ and environment variables
            config = self._expand_paths(config)
            
            # Validate macro configuration settings
            self._validate_macro_config(config)
            
            return config
        except FileNotFoundError:
            print(f"Error: Configuration file '{config_path}' not found")
            sys.exit(1)
        except yaml.YAMLError as e:
            print(f"Error parsing YAML configuration: {e}")
            sys.exit(1)
        except ValueError as e:
            print(f"Error: Invalid configuration: {e}")
            sys.exit(1)
    
    def _expand_paths(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Expand ~ and environment variables in path configurations"""
        # Paths that need expansion
        path_keys = [
            'timelapse.output_dir',
            'storage.backup_path', 
            'system.log_file',
            'slack.bot_token'
        ]
        
        for key_path in path_keys:
            keys = key_path.split('.')
            current = config
            
            # Navigate to the nested key
            for key in keys[:-1]:
                if key in current:
                    current = current[key]
                else:
                    break
            else:
                # Expand the final key if it exists
                final_key = keys[-1]
                if final_key in current and isinstance(current[final_key], str):
                    current[final_key] = os.path.expanduser(os.path.expandvars(current[final_key]))
        
        return config
    
    def _validate_macro_config(self, config: Dict[str, Any]) -> None:
        """Validate macro photography configuration settings"""
        camera_config = config.get('camera', {})
        
        # Validate focus settings
        focus_config = camera_config.get('focus', {})
        if focus_config:
            focus_mode = focus_config.get('mode', 'auto')
            if focus_mode not in ['auto', 'manual', 'continuous']:
                raise ValueError(f"Invalid focus mode: {focus_mode}. Must be 'auto', 'manual', or 'continuous'")
            
            # Check for mixed auto/manual focus configuration
            if focus_mode in ['auto', 'continuous']:
                manual_values = ['lens_position']
                provided_manual = [key for key in manual_values if key in focus_config and focus_config[key] is not None]
                if provided_manual:
                    raise ValueError(f"Invalid configuration: focus.mode is '{focus_mode}' but manual values provided: {provided_manual}. Manual values are ignored in auto/continuous mode.")
            
            if focus_mode == 'manual':
                lens_position = focus_config.get('lens_position')
                if lens_position is None:
                    raise ValueError("focus.mode is 'manual' but no lens_position provided. Manual focus requires lens_position.")
                if not isinstance(lens_position, (int, float)):
                    raise ValueError("lens_position must be a number")
                if lens_position < 0.0 or lens_position > 1000.0:
                    raise ValueError(f"lens_position {lens_position} out of range (0.0-1000.0)")
        
        # Validate exposure settings
        exposure_config = camera_config.get('exposure', {})
        legacy_exposure_mode = camera_config.get('exposure_mode', 'auto')
        
        if exposure_config:
            exposure_mode = exposure_config.get('mode', 'auto')
            if exposure_mode not in ['auto', 'manual', 'sport', 'night']:
                raise ValueError(f"Invalid exposure mode: {exposure_mode}. Must be 'auto', 'manual', 'sport', or 'night'")
            
            # Check for mixed auto/manual configuration
            if exposure_mode in ['auto', 'sport', 'night']:
                manual_values = ['shutter_speed', 'iso', 'gain']
                provided_manual = [key for key in manual_values if key in exposure_config and exposure_config[key] is not None]
                if provided_manual:
                    raise ValueError(f"Invalid configuration: exposure.mode is '{exposure_mode}' but manual values provided: {provided_manual}. Manual values are ignored in auto/sport/night mode.")
            
            if exposure_mode == 'manual':
                # For manual mode, at least one manual value should be provided
                manual_values = ['shutter_speed', 'iso', 'gain']
                provided_manual = [key for key in manual_values if key in exposure_config and exposure_config[key] is not None]
                if not provided_manual:
                    raise ValueError("exposure.mode is 'manual' but no manual values provided. Manual exposure requires at least one of: shutter_speed, iso, or gain.")
                
                # Validate provided manual values
                shutter_speed = exposure_config.get('shutter_speed')
                if shutter_speed is not None:
                    if not isinstance(shutter_speed, (int, float)):
                        raise ValueError("shutter_speed must be a number")
                    if shutter_speed < 1 or shutter_speed > 1000000:
                        raise ValueError(f"shutter_speed {shutter_speed} out of range (1-1000000 microseconds)")
                
                iso = exposure_config.get('iso')
                if iso is not None:
                    if not isinstance(iso, (int, float)):
                        raise ValueError("iso must be a number")
                    if iso < 100 or iso > 3200:
                        raise ValueError(f"iso {iso} out of range (100-3200)")
                
                gain = exposure_config.get('gain')
                if gain is not None:
                    if not isinstance(gain, (int, float)):
                        raise ValueError("gain must be a number")
                    if gain < 0.0 or gain > 16.0:
                        raise ValueError(f"gain {gain} out of range (0.0-16.0)")
        
        # Warn about legacy exposure_mode if new exposure section exists
        if exposure_config and legacy_exposure_mode != 'auto':
            raise ValueError("Cannot use both legacy 'exposure_mode' and new 'exposure' section. Use only the 'exposure' section.")
        
        # Validate image quality settings
        if 'noise_reduction' in camera_config:
            if not isinstance(camera_config['noise_reduction'], bool):
                raise ValueError("noise_reduction must be a boolean")
        
        if 'stabilization' in camera_config:
            if not isinstance(camera_config['stabilization'], bool):
                raise ValueError("stabilization must be a boolean")
    
    def _setup_logging(self) -> logging.Logger:
        """Setup logging configuration"""
        log_level = getattr(logging, self.config['system']['log_level'].upper())
        
        # Create logs directory if it doesn't exist
        log_file = self.config['system']['log_file']
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        return logging.getLogger(__name__)
    
    def _check_system_health(self) -> bool:
        """Check system health (temperature, disk space)"""
        try:
            # Check CPU temperature
            temp_file = '/sys/class/thermal/thermal_zone0/temp'
            if os.path.exists(temp_file):
                with open(temp_file, 'r') as f:
                    temp = int(f.read()) / 1000
                    if temp > self.config['system']['temperature_warning']:
                        self.logger.warning(f"High CPU temperature: {temp}°C")
                        self.slack.send_temperature_alert(temp)
                        return False
            
            # Check disk space
            output_dir = self.config['timelapse']['output_dir']
            if os.path.exists(output_dir):
                stat = shutil.disk_usage(output_dir)
                free_mb = stat.free / (1024 * 1024)
                if free_mb < self.config['system']['low_disk_warning']:
                    self.logger.warning(f"Low disk space: {free_mb:.1f}MB free")
                    self.slack.send_disk_space_alert(free_mb)
                    return False
            
            return True
        except Exception as e:
            self.logger.error(f"System health check failed: {e}")
            self.slack.send_error("System health check failed", e)
            return False
    
    def _setup_camera(self) -> bool:
        """Initialize and configure the camera"""
        try:
            self.camera = Picamera2()
            
            # Get camera info
            camera_info = self.camera.camera_properties
            self.logger.info(f"Camera model: {camera_info.get('Model', 'Unknown')}")
            
            # Configure camera
            camera_config = self.camera.create_still_configuration(
                main={
                    "size": (
                        self.config['camera']['resolution']['width'],
                        self.config['camera']['resolution']['height']
                    )
                },
                buffer_count=2
            )
            
            # Add transform settings if needed
            vflip = self.config['camera'].get('vflip', False)
            hflip = self.config['camera'].get('hflip', False)
            
            if vflip or hflip:
                from libcamera import Transform
                transform = Transform(vflip=vflip, hflip=hflip)
                camera_config["transform"] = transform
            
            self.camera.configure(camera_config)
            
            # Set camera controls (consolidated to avoid conflicts)
            controls_dict = {}
            
            # Legacy exposure mode (for backward compatibility)
            legacy_exposure_mode = self.config['camera'].get('exposure_mode', 'auto')
            if legacy_exposure_mode != 'auto':
                controls_dict['ExposureMode'] = getattr(
                    controls.ExposureModeEnum, 
                    legacy_exposure_mode.upper()
                )
            
            # New macro exposure settings
            exposure_config = self.config['camera'].get('exposure', {})
            if exposure_config.get('mode') == 'manual':
                # Manual exposure control
                controls_dict['AeEnable'] = False
                if 'shutter_speed' in exposure_config:
                    controls_dict['ExposureTime'] = exposure_config['shutter_speed']
                if 'iso' in exposure_config:
                    controls_dict['AnalogueGain'] = exposure_config['iso'] / 100.0
                if 'gain' in exposure_config:
                    controls_dict['AnalogueGain'] = exposure_config['gain']
            elif exposure_config.get('mode') == 'auto':
                # Auto exposure
                controls_dict['AeEnable'] = True
            
            # AWB mode (only set if not auto)
            if self.config['camera']['awb_mode'] != 'auto':
                controls_dict['AwbMode'] = getattr(
                    controls.AwbModeEnum,
                    self.config['camera']['awb_mode'].upper()
                )
            
            # Focus control (macro settings only)
            focus_config = self.config['camera'].get('focus', {})
            
            if focus_config:
                # Use macro focus settings
                focus_mode = focus_config.get('mode', 'auto')
                if focus_mode == 'manual':
                    # Manual focus control
                    controls_dict['AfMode'] = controls.AfModeEnum.Manual
                    if 'lens_position' in focus_config:
                        lens_pos = focus_config['lens_position']
                        # Validate lens position range (0.0-1000.0)
                        lens_pos = max(0.0, min(1000.0, lens_pos))
                        controls_dict['LensPosition'] = lens_pos
                        self.logger.info(f"Manual focus set to lens position: {lens_pos}")
                elif focus_mode == 'auto':
                    # Auto focus
                    controls_dict['AfMode'] = controls.AfModeEnum.Auto
                elif focus_mode == 'continuous':
                    # Continuous focus
                    controls_dict['AfMode'] = controls.AfModeEnum.Continuous
            
            # Image quality settings for macro
            if self.config['camera'].get('noise_reduction', False):
                controls_dict['NoiseReductionMode'] = controls.draft.NoiseReductionModeEnum.HighQuality
            
            # REMOVED: ColourGains control that was causing green tint
            # if self.config['camera'].get('stabilization', False):
            #     controls_dict['ColourGains'] = (1.0, 1.0)  # This was causing green tint
            
            # Add image effects and adjustments to same controls dict
            controls_dict.update({
                "Brightness": self.config['camera']['brightness'],
                "Contrast": self.config['camera']['contrast'],
                "Saturation": self.config['camera']['saturation'],
                "Sharpness": self.config['camera']['sharpness']
            })
            
            # Apply all controls in one call to avoid conflicts
            if controls_dict:
                self.camera.set_controls(controls_dict)
            
            self.camera.start()
            self.logger.info("Camera initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize camera: {e}")
            self.slack.send_error("Failed to initialize camera", e)
            return False
    
    def _create_output_directory(self) -> bool:
        """Create output directory for images"""
        try:
            output_dir = Path(self.config['timelapse']['output_dir'])
            output_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Output directory: {output_dir}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to create output directory: {e}")
            return False
    
    def _cleanup_old_images(self):
        """Clean up old images if enabled"""
        if not self.config['storage']['cleanup_old']:
            return
        
        try:
            output_dir = Path(self.config['timelapse']['output_dir'])
            images = list(output_dir.glob("*.jpg"))
            
            if len(images) > self.config['storage']['max_images']:
                # Sort by modification time and remove oldest
                images.sort(key=lambda x: x.stat().st_mtime)
                images_to_remove = images[:-self.config['storage']['max_images']]
                
                for img in images_to_remove:
                    img.unlink()
                    self.logger.info(f"Removed old image: {img.name}")
                    
        except Exception as e:
            self.logger.error(f"Failed to cleanup old images: {e}")
    
    def capture_image(self, filename: Optional[str] = None) -> bool:
        """Capture a single image"""
        if not self.camera:
            self.logger.error("Camera not initialized")
            self.slack.send_error("Camera not initialized")
            return False
        
        try:
            if filename is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{self.config['timelapse']['filename_prefix']}{timestamp}.jpg"
            
            output_path = Path(self.config['timelapse']['output_dir']) / filename
            
            # Capture image
            self.camera.capture_file(str(output_path))
            
            self.image_count += 1
            self.logger.info(f"Captured image {self.image_count}: {filename}")
            
            # Send progress update
            if self.start_time:
                elapsed = time.time() - self.start_time
                remaining = self.config['timelapse']['duration'] - elapsed
                self.slack.send_progress_update(self.image_count, elapsed, remaining)
            
            # Send photo notification if enabled
            if self.slack.notifications.get('send_photos', True):
                self._send_photo_notification()
            
            # Cleanup old images if needed
            self._cleanup_old_images()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to capture image: {e}")
            self.slack.send_error("Failed to capture image", e)
            return False
    
    def _send_photo_notification(self):
        """Capture and send low-resolution photo for notification"""
        try:
            # Get low-res photo settings
            photo_config = self.slack.notifications
            width = photo_config.get('photo_resolution', {}).get('width', 640)
            height = photo_config.get('photo_resolution', {}).get('height', 480)
            quality = photo_config.get('photo_quality', 30)
            
            # Create temporary low-res configuration with same transform settings
            vflip = self.config['camera'].get('vflip', False)
            hflip = self.config['camera'].get('hflip', False)
            
            lowres_config = self.camera.create_still_configuration(
                main={"size": (width, height)},
                buffer_count=1
            )
            
            # Apply same transform settings to low-res config
            if vflip or hflip:
                from libcamera import Transform
                transform = Transform(vflip=vflip, hflip=hflip)
                lowres_config["transform"] = transform
            
            # Switch to low-res config temporarily
            self.camera.switch_mode(lowres_config)
            
            # Capture low-res image to memory
            import io
            image_stream = io.BytesIO()
            self.camera.capture_file(image_stream, format='jpeg')
            image_data = image_stream.getvalue()
            
            # Switch back to main config with same transform settings
            main_config = self.camera.create_still_configuration(
                main={
                    "size": (
                        self.config['camera']['resolution']['width'],
                        self.config['camera']['resolution']['height']
                    )
                },
                buffer_count=2
            )
            
            # Apply same transform settings to main config
            if vflip or hflip:
                from libcamera import Transform
                transform = Transform(vflip=vflip, hflip=hflip)
                main_config["transform"] = transform
            
            self.camera.switch_mode(main_config)
            
            # Send photo notification
            self.slack.send_photo_notification(image_data, self.image_count)
            
        except Exception as e:
            self.logger.warning(f"Failed to send photo notification: {e}")
            # Don't send error notification for this as it's not critical
    
    def run_timelapse(self):
        """Run timelapse capture sequence"""
        if not self.config['timelapse']['enabled']:
            self.logger.info("Timelapse disabled in configuration")
            return
        
        self.logger.info("Starting timelapse capture")
        self.start_time = time.time()
        
        # Send start notification
        self.slack.send_start_notification()
        
        interval = self.config['timelapse']['interval']
        duration = self.config['timelapse']['duration']
        end_time = self.start_time + duration
        
        try:
            while time.time() < end_time:
                # Check system health
                if not self._check_system_health():
                    self.logger.warning("System health check failed, continuing...")
                    self.slack.send_warning("System health check failed, continuing...")
                
                # Capture image
                if self.capture_image():
                    elapsed = time.time() - self.start_time
                    remaining = end_time - time.time()
                    self.logger.info(f"Timelapse progress: {elapsed:.1f}s elapsed, {remaining:.1f}s remaining")
                else:
                    self.logger.error("Failed to capture image, retrying...")
                    self.slack.send_warning("Failed to capture image, retrying...")
                
                # Wait for next capture
                time.sleep(interval)
                
        except KeyboardInterrupt:
            self.logger.info("Timelapse interrupted by user")
            self.slack.send_warning("Timelapse interrupted by user")
        except Exception as e:
            self.logger.error(f"Timelapse failed: {e}")
            self.slack.send_error("Timelapse failed", e)
        finally:
            duration = time.time() - self.start_time if self.start_time else 0
            self.logger.info(f"Timelapse completed. Total images captured: {self.image_count}")
            self.slack.send_stop_notification(self.image_count, duration)
    
    def create_video(self):
        """Create video from captured images using ffmpeg"""
        if not self.config['timelapse']['create_video']:
            return
        
        try:
            import subprocess
            
            output_dir = Path(self.config['timelapse']['output_dir'])
            video_path = output_dir / "timelapse_video.mp4"
            
            # Check if ffmpeg is available
            try:
                subprocess.run(['ffmpeg', '-version'], 
                             capture_output=True, check=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                self.logger.warning("ffmpeg not found, skipping video creation")
                return
            
            # Create video from images
            cmd = [
                'ffmpeg', '-y',  # Overwrite output file
                '-framerate', str(self.config['timelapse']['video_fps']),
                '-pattern_type', 'glob',
                '-i', str(output_dir / '*.jpg'),
                '-c:v', 'libx264',
                '-pix_fmt', 'yuv420p',
                str(video_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                self.logger.info(f"Video created successfully: {video_path}")
            else:
                self.logger.error(f"Video creation failed: {result.stderr}")
                
        except Exception as e:
            self.logger.error(f"Failed to create video: {e}")
    
    def reload_config(self):
        """Reload configuration and reapply camera settings"""
        try:
            # Reload config using existing method
            self.config = self._load_config("config.yaml")
            
            # Properly stop and close current camera
            if self.camera:
                try:
                    self.camera.stop()
                    self.camera.close()
                    # Give the camera time to fully release
                    time.sleep(0.5)
                except Exception as e:
                    self.logger.warning(f"Error stopping camera during reload: {e}")
            
            # Create a new camera instance to avoid state issues
            try:
                from picamera2 import Picamera2
                self.camera = Picamera2()
            except Exception as e:
                self.logger.error(f"Error creating new camera instance: {e}")
                return False
            
            # Reapply camera settings
            if self._setup_camera():
                self.logger.info("Configuration reloaded successfully")
                return True
            else:
                self.logger.error("Failed to reapply camera settings after reload")
                return False
                
        except Exception as e:
            self.logger.error(f"Error reloading configuration: {e}")
            return False
    
    def cleanup(self):
        """Cleanup resources"""
        if self.camera:
            self.camera.stop()
            self.camera.close()
            self.logger.info("Camera resources cleaned up")
    
    def run(self):
        """Main run method"""
        try:
            # Setup
            if not self._create_output_directory():
                return False
            
            if not self._setup_camera():
                return False
            
            # Run timelapse
            self.run_timelapse()
            
            # Create video if enabled
            self.create_video()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Application failed: {e}")
            return False
        finally:
            self.cleanup()


def main():
    """Main entry point"""
    print("Raspberry Pi Camera 3 Controller")
    print("================================")
    
    # Check if running on Raspberry Pi
    if not os.path.exists('/proc/device-tree/model'):
        print("Warning: This script is designed for Raspberry Pi")
    
    # Initialize and run controller
    controller = PiCameraController()
    
    try:
        success = controller.run()
        if success:
            print("Application completed successfully")
        else:
            print("Application failed")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\nApplication interrupted by user")
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
