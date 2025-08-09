#!/usr/bin/env python3
"""
Firmware Monitor for Clover Swarm ESP-NOW Controller

This script provides:
- Integration with ESP32 controller console commands
- Real-time monitoring of firmware upload status
- Automatic firmware server management
- Status reporting to the controller
"""

import os
import sys
import json
import time
import logging
import requests
import threading
from datetime import datetime
from pathlib import Path
import argparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('firmware_monitor.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class FirmwareMonitor:
    def __init__(self, server_url="http://localhost:8080", firmware_dir="firmware"):
        self.server_url = server_url
        self.firmware_dir = Path(firmware_dir)
        self.firmware_dir.mkdir(exist_ok=True)
        self.monitoring = False
        self.monitor_thread = None
        
    def start_monitoring(self):
        """Start monitoring firmware upload status"""
        if self.monitoring:
            logger.warning("Monitoring already started")
            return
            
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("Firmware monitoring started")
    
    def stop_monitoring(self):
        """Stop monitoring firmware upload status"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join()
        logger.info("Firmware monitoring stopped")
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        last_status = {}
        
        while self.monitoring:
            try:
                # Get current status from server
                response = requests.get(f"{self.server_url}/status", timeout=5)
                if response.status_code == 200:
                    current_status = response.json()
                    
                    # Check for new upload attempts
                    for drone_id, status in current_status.items():
                        if drone_id not in last_status or last_status[drone_id] != status:
                            self._handle_status_change(drone_id, status)
                    
                    last_status = current_status
                    
            except requests.exceptions.RequestException as e:
                logger.warning(f"Failed to connect to firmware server: {e}")
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
            
            time.sleep(2)  # Check every 2 seconds
    
    def _handle_status_change(self, drone_id, status):
        """Handle status change for a drone"""
        logger.info(f"Drone {drone_id} status change: {status['status']} - {status['firmware']}")
        
        # You can add custom logic here to integrate with ESP32 controller
        # For example, send status updates via serial or network
        
        if status['status'] == 'success':
            logger.info(f"✅ Drone {drone_id} successfully updated with {status['firmware']}")
        elif status['status'] == 'error':
            logger.error(f"❌ Drone {drone_id} failed to update with {status['firmware']}")
        elif status['status'] == 'started':
            logger.info(f"🔄 Drone {drone_id} started updating with {status['firmware']}")
    
    def get_firmware_list(self):
        """Get list of available firmware files"""
        try:
            response = requests.get(f"{self.server_url}/firmware", timeout=5)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.error(f"Failed to get firmware list: {e}")
        return []
    
    def log_upload_attempt(self, drone_id, firmware_name, status="started"):
        """Log upload attempt to the server"""
        try:
            data = {
                'drone_id': drone_id,
                'firmware': firmware_name,
                'status': status
            }
            response = requests.post(f"{self.server_url}/upload_log", 
                                  json=data, timeout=5)
            if response.status_code == 200:
                logger.info(f"Upload attempt logged: Drone {drone_id} - {status}")
            else:
                logger.warning(f"Failed to log upload attempt: {response.status_code}")
        except Exception as e:
            logger.error(f"Failed to log upload attempt: {e}")
    
    def check_server_status(self):
        """Check if firmware server is running"""
        try:
            response = requests.get(f"{self.server_url}/status", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def get_server_info(self):
        """Get server information"""
        try:
            response = requests.get(f"{self.server_url}/firmware", timeout=5)
            if response.status_code == 200:
                firmware_list = response.json()
                return {
                    'status': 'running',
                    'firmware_count': len(firmware_list),
                    'firmware_files': [fw['name'] for fw in firmware_list]
                }
        except Exception as e:
            logger.error(f"Failed to get server info: {e}")
        
        return {'status': 'not_available'}

def main():
    parser = argparse.ArgumentParser(description='Clover Swarm Firmware Monitor')
    parser.add_argument('--server-url', default='http://localhost:8080', 
                       help='Firmware server URL (default: http://localhost:8080)')
    parser.add_argument('--firmware-dir', default='firmware', 
                       help='Firmware directory (default: firmware)')
    parser.add_argument('--monitor', action='store_true', 
                       help='Start monitoring mode')
    parser.add_argument('--status', action='store_true', 
                       help='Show server status')
    parser.add_argument('--list', action='store_true', 
                       help='List available firmware')
    parser.add_argument('--log-upload', nargs=3, metavar=('DRONE_ID', 'FIRMWARE', 'STATUS'),
                       help='Log upload attempt (DRONE_ID FIRMWARE STATUS)')
    
    args = parser.parse_args()
    
    monitor = FirmwareMonitor(server_url=args.server_url, firmware_dir=args.firmware_dir)
    
    if args.status:
        info = monitor.get_server_info()
        print(f"Server Status: {info['status']}")
        if info['status'] == 'running':
            print(f"Available firmware: {info['firmware_count']}")
            for fw in info['firmware_files']:
                print(f"  - {fw}")
    
    elif args.list:
        firmware_list = monitor.get_firmware_list()
        if firmware_list:
            print("Available firmware files:")
            for fw in firmware_list:
                print(f"  - {fw['name']} ({fw['size']} bytes)")
        else:
            print("No firmware files available")
    
    elif args.log_upload:
        drone_id, firmware, status = args.log_upload
        monitor.log_upload_attempt(drone_id, firmware, status)
    
    elif args.monitor:
        print("Starting firmware monitor...")
        print(f"Server URL: {args.server_url}")
        print("Press Ctrl+C to stop")
        
        try:
            monitor.start_monitoring()
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping monitor...")
            monitor.stop_monitoring()
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main() 