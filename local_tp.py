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
except ImportError:
    print("Error: requests module not found. Please install it with:")
    print("pip3 install requests")
    sys.exit(1)


class SlackNotifier:
    """Slack webhook notification handler"""
    
    def __init__(self, config: Dict[str, Any], logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.enabled = config.get('enabled', False)
        self.webhook_url = config.get('webhook_url', '')
        self.channel = config.get('channel', '')
        self.username = config.get('username', 'Pi Camera Bot')
        self.icon_emoji = config.get('icon_emoji', ':camera:')
        self.notifications = config.get('notifications', {})
        
        if self.enabled and not self.webhook_url:
            self.logger.warning("Slack notifications enabled but no webhook URL provided")
            self.enabled = False
    
    def _send_message(self, text: str, title: str = None, color: str = None, 
                     image_data: bytes = None, image_filename: str = None) -> bool:
        """Send a message to Slack via webhook"""
        if not self.enabled:
            return False
        
        try:
            payload = {
                "username": self.username,
                "icon_emoji": self.icon_emoji,
                "text": text
            }
            
            if self.channel:
                payload["channel"] = self.channel
            
            # Add attachment for rich formatting
            if title or color:
                attachment = {
                    "fallback": text,
                    "color": color or "good",
                    "fields": [
                        {
                            "title": title or "Camera Status",
                            "value": text,
                            "short": False
                        }
                    ],
                    "ts": int(time.time())
                }
                payload["attachments"] = [attachment]
            
            # Send image if provided
            if image_data and image_filename:
                # For images, we need to use files.upload API instead of webhook
                # This is a simplified approach - in production you might want to use the Slack SDK
                files = {
                    'file': (image_filename, image_data, 'image/jpeg')
                }
                data = {
                    'channels': self.channel or '',
                    'initial_comment': text,
                    'username': self.username
                }
                
                # Note: This requires a bot token, not a webhook URL
                # For webhook-only approach, we'll skip image upload for now
                self.logger.warning("Image upload requires bot token, skipping image")
                return self._send_webhook(payload)
            else:
                return self._send_webhook(payload)
                
        except Exception as e:
            self.logger.error(f"Failed to send Slack message: {e}")
            return False
    
    def _send_webhook(self, payload: Dict[str, Any]) -> bool:
        """Send webhook payload to Slack"""
        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Slack webhook request failed: {e}")
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
            color="danger"
        )
    
    def send_warning(self, message: str) -> bool:
        """Send warning notification"""
        if not self.notifications.get('warnings', True):
            return False
        
        text = f"⚠️ *Warning*: {message}"
        return self._send_message(
            text=text,
            title="Camera Warning",
            color="warning"
        )
    
    def send_start_notification(self) -> bool:
        """Send timelapse start notification"""
        if not self.notifications.get('start_stop', True):
            return False
        
        text = f"🎬 *Timelapse Started*\n"
        text += f"• Interval: {self.config.get('timelapse', {}).get('interval', 'N/A')}s\n"
        text += f"• Duration: {self.config.get('timelapse', {}).get('duration', 'N/A')}s\n"
        text += f"• Output: {self.config.get('timelapse', {}).get('output_dir', 'N/A')}"
        
        return self._send_message(
            text=text,
            title="Timelapse Started",
            color="good"
        )
    
    def send_stop_notification(self, image_count: int, duration: float) -> bool:
        """Send timelapse stop notification"""
        if not self.notifications.get('start_stop', True):
            return False
        
        text = f"✅ *Timelapse Completed*\n"
        text += f"• Images captured: {image_count}\n"
        text += f"• Duration: {duration:.1f}s\n"
        text += f"• Average interval: {duration/max(image_count, 1):.1f}s"
        
        return self._send_message(
            text=text,
            title="Timelapse Completed",
            color="good"
        )
    
    def send_progress_update(self, image_count: int, elapsed: float, remaining: float) -> bool:
        """Send progress update notification"""
        if not self.notifications.get('progress_updates', True):
            return False
        
        interval = self.notifications.get('progress_interval', 10)
        if image_count % interval != 0:
            return False
        
        text = f"📊 *Progress Update*\n"
        text += f"• Images captured: {image_count}\n"
        text += f"• Elapsed: {elapsed:.1f}s\n"
        text += f"• Remaining: {remaining:.1f}s"
        
        return self._send_message(
            text=text,
            title="Timelapse Progress",
            color="#36a64f"
        )
    
    def send_photo_notification(self, image_data: bytes, image_count: int) -> bool:
        """Send photo notification with low-res image"""
        if not self.notifications.get('send_photos', True):
            return False
        
        interval = self.notifications.get('photo_interval', 5)
        if image_count % interval != 0:
            return False
        
        text = f"📸 *Photo Update*\n"
        text += f"• Image #{image_count} captured\n"
        text += f"• Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        filename = f"timelapse_{image_count:04d}.jpg"
        return self._send_message(
            text=text,
            title="Photo Update",
            color="#36a64f",
            image_data=image_data,
            image_filename=filename
        )
    
    def send_temperature_alert(self, temperature: float) -> bool:
        """Send temperature alert"""
        if not self.notifications.get('temperature_alerts', True):
            return False
        
        text = f"🌡️ *High Temperature Alert*\n"
        text += f"• CPU Temperature: {temperature:.1f}°C\n"
        text += f"• Threshold: {self.config.get('system', {}).get('temperature_warning', 80)}°C"
        
        return self._send_message(
            text=text,
            title="Temperature Alert",
            color="warning"
        )
    
    def send_disk_space_alert(self, free_space_mb: float) -> bool:
        """Send disk space alert"""
        if not self.notifications.get('disk_space_alerts', True):
            return False
        
        text = f"💾 *Low Disk Space Alert*\n"
        text += f"• Free space: {free_space_mb:.1f}MB\n"
        text += f"• Threshold: {self.config.get('system', {}).get('low_disk_warning', 100)}MB"
        
        return self._send_message(
            text=text,
            title="Disk Space Alert",
            color="warning"
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
        self.slack = SlackNotifier(slack_config, self.logger)
        
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        try:
            with open(config_path, 'r') as file:
                config = yaml.safe_load(file)
            return config
        except FileNotFoundError:
            print(f"Error: Configuration file '{config_path}' not found")
            sys.exit(1)
        except yaml.YAMLError as e:
            print(f"Error parsing YAML configuration: {e}")
            sys.exit(1)
    
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
            
            self.camera.configure(camera_config)
            
            # Set camera controls
            controls_dict = {}
            
            # Exposure mode
            if self.config['camera']['exposure_mode'] != 'auto':
                controls_dict['ExposureMode'] = getattr(
                    controls.ExposureModeEnum, 
                    self.config['camera']['exposure_mode'].upper()
                )
            
            # AWB mode
            if self.config['camera']['awb_mode'] != 'auto':
                controls_dict['AeEnable'] = False
                controls_dict['AwbMode'] = getattr(
                    controls.AwbModeEnum,
                    self.config['camera']['awb_mode'].upper()
                )
            
            # Focus mode
            if self.config['camera']['focus_mode'] != 'auto':
                controls_dict['AfMode'] = getattr(
                    controls.AfModeEnum,
                    self.config['camera']['focus_mode'].upper()
                )
            
            if controls_dict:
                self.camera.set_controls(controls_dict)
            
            # Set image effects and adjustments
            self.camera.set_controls({
                "Brightness": self.config['camera']['brightness'],
                "Contrast": self.config['camera']['contrast'],
                "Saturation": self.config['camera']['saturation'],
                "Sharpness": self.config['camera']['sharpness']
            })
            
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
            
            # Create temporary low-res configuration
            lowres_config = self.camera.create_still_configuration(
                main={"size": (width, height)},
                buffer_count=1
            )
            
            # Switch to low-res config temporarily
            self.camera.switch_mode(lowres_config)
            
            # Capture low-res image to memory
            import io
            image_stream = io.BytesIO()
            self.camera.capture_file(image_stream, format='jpeg', quality=quality)
            image_data = image_stream.getvalue()
            
            # Switch back to main config
            main_config = self.camera.create_still_configuration(
                main={
                    "size": (
                        self.config['camera']['resolution']['width'],
                        self.config['camera']['resolution']['height']
                    )
                },
                buffer_count=2
            )
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
