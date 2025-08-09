#!/usr/bin/env python3
"""
Console Integration for Clover Swarm Firmware Server

This script provides integration between the ESP32 controller console
and the firmware server for seamless OTA updates.
"""

import os
import sys
import json
import requests
import argparse
from pathlib import Path

class ConsoleIntegration:
    def __init__(self, server_url="http://localhost:8080"):
        self.server_url = server_url
        
    def check_server_status(self):
        """Check if firmware server is running"""
        try:
            response = requests.get(f"{self.server_url}/status", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def get_firmware_list(self):
        """Get list of available firmware files"""
        try:
            response = requests.get(f"{self.server_url}/firmware", timeout=5)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"Error getting firmware list: {e}")
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
            return response.status_code == 200
        except Exception as e:
            print(f"Error logging upload attempt: {e}")
            return False
    
    def generate_ota_command(self, drone_id, firmware_name, ssid=None, password=None):
        """Generate OTA command for ESP32 controller"""
        firmware_url = f"{self.server_url}/firmware/{firmware_name}"
        
        if ssid and password:
            # Full configuration with WiFi and OTA
            return f"ota_config {drone_id} 0x03 {ssid} {password} {firmware_url}"
        else:
            # OTA only
            return f"ota_config {drone_id} 0x01 NULL NULL {firmware_url}"
    
    def print_firmware_status(self):
        """Print current firmware status"""
        if not self.check_server_status():
            print("❌ Firmware server is not running")
            print("Start it with: ./start_firmware_server.sh")
            return
        
        print("✅ Firmware server is running")
        firmware_list = self.get_firmware_list()
        
        if firmware_list:
            print(f"\n📁 Available firmware ({len(firmware_list)} files):")
            for fw in firmware_list:
                size_mb = fw['size'] / (1024 * 1024)
                print(f"  • {fw['name']} ({size_mb:.1f} MB)")
        else:
            print("\n📁 No firmware files available")
            print("Add firmware files to the 'firmware/' directory")
    
    def print_upload_status(self):
        """Print current upload status"""
        try:
            response = requests.get(f"{self.server_url}/status", timeout=5)
            if response.status_code == 200:
                status = response.json()
                if status:
                    print("\n📊 Upload Status:")
                    for drone_id, info in status.items():
                        status_icon = {
                            'success': '✅',
                            'error': '❌',
                            'started': '🔄',
                            'pending': '⏳'
                        }.get(info['status'], '❓')
                        
                        print(f"  {status_icon} Drone {drone_id}: {info['firmware']} ({info['status']})")
                else:
                    print("\n📊 No upload activity")
            else:
                print("❌ Failed to get upload status")
        except Exception as e:
            print(f"❌ Error getting upload status: {e}")

def main():
    parser = argparse.ArgumentParser(description='Clover Swarm Console Integration')
    parser.add_argument('--server-url', default='http://localhost:8080',
                       help='Firmware server URL')
    parser.add_argument('--status', action='store_true',
                       help='Show firmware server status')
    parser.add_argument('--list', action='store_true',
                       help='List available firmware')
    parser.add_argument('--upload-status', action='store_true',
                       help='Show upload status')
    parser.add_argument('--generate-command', nargs=3, 
                       metavar=('DRONE_ID', 'FIRMWARE', 'SSID'),
                       help='Generate OTA command (DRONE_ID FIRMWARE SSID)')
    parser.add_argument('--generate-ota-only', nargs=2,
                       metavar=('DRONE_ID', 'FIRMWARE'),
                       help='Generate OTA-only command (DRONE_ID FIRMWARE)')
    parser.add_argument('--log-upload', nargs=3,
                       metavar=('DRONE_ID', 'FIRMWARE', 'STATUS'),
                       help='Log upload attempt (DRONE_ID FIRMWARE STATUS)')
    
    args = parser.parse_args()
    
    integration = ConsoleIntegration(server_url=args.server_url)
    
    if args.status:
        integration.print_firmware_status()
    
    elif args.list:
        firmware_list = integration.get_firmware_list()
        if firmware_list:
            print("Available firmware files:")
            for fw in firmware_list:
                size_mb = fw['size'] / (1024 * 1024)
                print(f"  {fw['name']} ({size_mb:.1f} MB)")
        else:
            print("No firmware files available")
    
    elif args.upload_status:
        integration.print_upload_status()
    
    elif args.generate_command:
        drone_id, firmware, ssid = args.generate_command
        password = input("Enter WiFi password: ")
        command = integration.generate_ota_command(drone_id, firmware, ssid, password)
        print(f"\nGenerated OTA command:")
        print(f"  {command}")
    
    elif args.generate_ota_only:
        drone_id, firmware = args.generate_ota_only
        command = integration.generate_ota_command(drone_id, firmware)
        print(f"\nGenerated OTA-only command:")
        print(f"  {command}")
    
    elif args.log_upload:
        drone_id, firmware, status = args.log_upload
        if integration.log_upload_attempt(drone_id, firmware, status):
            print(f"✅ Upload attempt logged: Drone {drone_id} - {status}")
        else:
            print(f"❌ Failed to log upload attempt")
    
    else:
        # Default: show status
        integration.print_firmware_status()
        integration.print_upload_status()
        
        print(f"\n💡 Usage examples:")
        print(f"  python3 console_integration.py --status")
        print(f"  python3 console_integration.py --list")
        print(f"  python3 console_integration.py --generate-command 1 firmware_v1.2.bin MyWiFi")
        print(f"  python3 console_integration.py --generate-ota-only 1 firmware_v1.2.bin")
        print(f"  python3 console_integration.py --log-upload 1 firmware_v1.2.bin started")

if __name__ == "__main__":
    main() 