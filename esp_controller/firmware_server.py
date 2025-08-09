#!/usr/bin/env python3
"""
Firmware Server for Clover Swarm ESP-NOW Controller

This server provides:
- HTTP server for firmware downloads with concurrent support for 8 devices
- Upload status monitoring with progress tracking
- Simple web interface for firmware management
- Detailed logging of OTA operations with download progress
"""

import os
import sys
import json
import time
import logging
import threading
from datetime import datetime
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import argparse
import mimetypes
from collections import defaultdict, deque
import socket
import queue

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('firmware_server.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class DownloadProgress:
    def __init__(self, client_ip, firmware_name, total_size):
        self.client_ip = client_ip
        self.firmware_name = firmware_name
        self.total_size = total_size
        self.bytes_sent = 0
        self.start_time = time.time()
        self.last_update = time.time()
        self.status = "downloading"
        self.completion_time = None
    
    def update_progress(self, bytes_sent):
        self.bytes_sent = bytes_sent
        self.last_update = time.time()
        if bytes_sent >= self.total_size:
            self.status = "completed"
            self.completion_time = time.time()
    
    def get_progress_percentage(self):
        if self.total_size == 0:
            return 0
        return min(100, (self.bytes_sent / self.total_size) * 100)
    
    def get_download_speed(self):
        elapsed = time.time() - self.start_time
        if elapsed == 0:
            return 0
        return self.bytes_sent / elapsed  # bytes per second
    
    def to_dict(self):
        return {
            'client_ip': self.client_ip,
            'firmware_name': self.firmware_name,
            'total_size': self.total_size,
            'bytes_sent': self.bytes_sent,
            'progress_percentage': self.get_progress_percentage(),
            'download_speed': self.get_download_speed(),
            'status': self.status,
            'start_time': datetime.fromtimestamp(self.start_time).isoformat(),
            'last_update': datetime.fromtimestamp(self.last_update).isoformat(),
            'completion_time': datetime.fromtimestamp(self.completion_time).isoformat() if self.completion_time else None
        }

class FirmwareServer:
    def __init__(self, port=8080, firmware_dir="firmware", max_concurrent_downloads=8):
        self.port = port
        self.firmware_dir = Path(firmware_dir)
        self.firmware_dir.mkdir(exist_ok=True)
        self.upload_status = {}
        self.server = None
        self.max_concurrent_downloads = max_concurrent_downloads
        self.active_downloads = {}  # client_ip -> DownloadProgress
        self.download_history = deque(maxlen=100)  # Keep last 100 downloads
        self.download_lock = threading.Lock()
        
        # Initialize MIME types
        mimetypes.init()
        
    def start(self):
        """Start the firmware server with threaded request handling"""
        server_address = ('', self.port)
        self.server = ThreadedHTTPServer(server_address, FirmwareRequestHandler)
        self.server.firmware_server = self
        
        logger.info(f"Starting firmware server on port {self.port}")
        logger.info(f"Firmware directory: {self.firmware_dir.absolute()}")
        logger.info(f"Server URL: http://localhost:{self.port}")
        logger.info(f"Max concurrent downloads: {self.max_concurrent_downloads}")
        
        try:
            self.server.serve_forever()
        except KeyboardInterrupt:
            logger.info("Shutting down server...")
            self.server.shutdown()
    
    def get_firmware_list(self):
        """Get list of available firmware files"""
        firmware_files = []
        for file_path in self.firmware_dir.glob("*.bin"):
            stat = file_path.stat()
            firmware_files.append({
                'name': file_path.name,
                'size': stat.st_size,
                'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'url': f"/firmware/{file_path.name}"
            })
        return firmware_files
    
    def log_upload_attempt(self, drone_id, firmware_name, status="started"):
        """Log upload attempt"""
        timestamp = datetime.now().isoformat()
        self.upload_status[drone_id] = {
            'firmware': firmware_name,
            'status': status,
            'timestamp': timestamp,
            'attempts': self.upload_status.get(drone_id, {}).get('attempts', 0) + 1
        }
        logger.info(f"Drone {drone_id}: {status} upload of {firmware_name}")
    
    def get_upload_status(self):
        """Get current upload status for all drones"""
        return self.upload_status
    
    def start_download(self, client_ip, firmware_name, total_size):
        """Start tracking a new download"""
        with self.download_lock:
            # Check if client already has an active download
            if client_ip in self.active_downloads:
                logger.warning(f"Client {client_ip} already has active download")
                return False
            
            # Check if we've reached max concurrent downloads
            if len(self.active_downloads) >= self.max_concurrent_downloads:
                logger.warning(f"Max concurrent downloads reached ({self.max_concurrent_downloads})")
                return False
            
            progress = DownloadProgress(client_ip, firmware_name, total_size)
            self.active_downloads[client_ip] = progress
            logger.info(f"Started download: {client_ip} -> {firmware_name} ({total_size} bytes)")
            return True
    
    def update_download_progress(self, client_ip, bytes_sent):
        """Update download progress for a client"""
        with self.download_lock:
            if client_ip in self.active_downloads:
                self.active_downloads[client_ip].update_progress(bytes_sent)
    
    def complete_download(self, client_ip):
        """Mark download as completed"""
        with self.download_lock:
            if client_ip in self.active_downloads:
                progress = self.active_downloads[client_ip]
                progress.status = "completed"
                progress.completion_time = time.time()
                self.download_history.append(progress.to_dict())
                del self.active_downloads[client_ip]
                logger.info(f"Completed download: {client_ip} -> {progress.firmware_name}")
    
    def get_download_status(self):
        """Get current download status"""
        with self.download_lock:
            active = {ip: progress.to_dict() for ip, progress in self.active_downloads.items()}
            history = list(self.download_history)
            return {
                'active_downloads': active,
                'download_history': history,
                'max_concurrent': self.max_concurrent_downloads,
                'current_concurrent': len(self.active_downloads)
            }

class ThreadedHTTPServer(HTTPServer):
    """Threaded HTTP server to handle concurrent requests"""
    def __init__(self, server_address, RequestHandlerClass):
        HTTPServer.__init__(self, server_address, RequestHandlerClass)
        self.allow_reuse_address = True
    
    def process_request(self, request, client_address):
        """Process request in a separate thread"""
        thread = threading.Thread(target=self._process_request, args=(request, client_address))
        thread.daemon = True
        thread.start()
    
    def _process_request(self, request, client_address):
        """Process the request in a thread"""
        try:
            self.finish_request(request, client_address)
        except Exception as e:
            logger.error(f"Error processing request from {client_address}: {e}")
        finally:
            self.shutdown_request(request)

class FirmwareRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Handle GET requests"""
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        
        try:
            if path == "/" or path == "/index.html":
                self.send_index_page()
            elif path == "/status":
                self.send_status_json()
            elif path == "/downloads":
                self.send_download_status_json()
            elif path == "/firmware":
                self.send_firmware_list()
            elif path.startswith("/firmware/"):
                self.send_firmware_file(path[10:])  # Remove "/firmware/" prefix
            elif path == "/favicon.ico":
                self.send_error(404, "Not Found")
            else:
                self.send_error(404, "Not Found")
        except Exception as e:
            logger.error(f"Error handling GET request: {e}")
            self.send_error(500, "Internal Server Error")
    
    def do_POST(self):
        """Handle POST requests"""
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        
        try:
            if path == "/upload_log":
                self.handle_upload_log()
            else:
                self.send_error(404, "Not Found")
        except Exception as e:
            logger.error(f"Error handling POST request: {e}")
            self.send_error(500, "Internal Server Error")
    
    def send_index_page(self):
        """Send the main index page with enhanced UI"""
        html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Clover Swarm Firmware Server</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
        }
        .container {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 20px;
        }
        .card {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .firmware-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 5px;
            margin: 5px 0;
        }
        .status-item {
            padding: 10px;
            border-radius: 5px;
            margin: 5px 0;
        }
        .status-success { background-color: #d4edda; border: 1px solid #c3e6cb; }
        .status-error { background-color: #f8d7da; border: 1px solid #f5c6cb; }
        .status-pending { background-color: #fff3cd; border: 1px solid #ffeaa7; }
        .status-downloading { background-color: #cce5ff; border: 1px solid #b3d9ff; }
        .btn {
            background: #007bff;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 5px;
            cursor: pointer;
            text-decoration: none;
        }
        .btn:hover { background: #0056b3; }
        .refresh-btn {
            background: #28a745;
            margin-bottom: 10px;
        }
        .refresh-btn:hover { background: #1e7e34; }
        .progress-bar {
            width: 100%;
            height: 20px;
            background-color: #f0f0f0;
            border-radius: 10px;
            overflow: hidden;
            margin: 5px 0;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #28a745, #20c997);
            transition: width 0.3s ease;
        }
        .download-item {
            border: 1px solid #ddd;
            border-radius: 5px;
            padding: 10px;
            margin: 5px 0;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 10px;
            margin-bottom: 15px;
        }
        .stat-card {
            background: #f8f9fa;
            padding: 10px;
            border-radius: 5px;
            text-align: center;
        }
        .stat-number {
            font-size: 1.5em;
            font-weight: bold;
            color: #007bff;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🚁 Clover Swarm Firmware Server</h1>
        <p>Manage firmware updates for your drone swarm with concurrent download support</p>
    </div>
    
    <div class="container">
        <div class="card">
            <h2>📁 Available Firmware</h2>
            <button class="btn refresh-btn" onclick="loadFirmware()">🔄 Refresh</button>
            <div id="firmware-list">
                <p>Loading firmware list...</p>
            </div>
        </div>
        
        <div class="card">
            <h2>📊 Upload Status</h2>
            <button class="btn refresh-btn" onclick="loadStatus()">🔄 Refresh</button>
            <div id="status-list">
                <p>Loading status...</p>
            </div>
        </div>
        
        <div class="card">
            <h2>⬇️ Download Monitor</h2>
            <button class="btn refresh-btn" onclick="loadDownloads()">🔄 Refresh</button>
            <div id="download-stats" class="stats">
                <div class="stat-card">
                    <div class="stat-number" id="active-downloads">-</div>
                    <div>Active Downloads</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="max-concurrent">-</div>
                    <div>Max Concurrent</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="total-history">-</div>
                    <div>Total History</div>
                </div>
            </div>
            <div id="download-list">
                <p>Loading downloads...</p>
            </div>
        </div>
    </div>
    
    <script>
        function loadFirmware() {
            fetch('/firmware')
                .then(response => response.json())
                .then(data => {
                    const list = document.getElementById('firmware-list');
                    if (data.length === 0) {
                        list.innerHTML = '<p>No firmware files found</p>';
                        return;
                    }
                    
                    list.innerHTML = data.map(fw => `
                        <div class="firmware-item">
                            <div>
                                <strong>${fw.name}</strong><br>
                                <small>Size: ${formatBytes(fw.size)} | Modified: ${fw.modified}</small>
                            </div>
                            <a href="${fw.url}" class="btn">⬇️ Download</a>
                        </div>
                    `).join('');
                })
                .catch(error => {
                    console.error('Error loading firmware:', error);
                    document.getElementById('firmware-list').innerHTML = '<p>Error loading firmware list</p>';
                });
        }
        
        function loadStatus() {
            fetch('/status')
                .then(response => response.json())
                .then(data => {
                    const list = document.getElementById('status-list');
                    if (Object.keys(data).length === 0) {
                        list.innerHTML = '<p>No upload activity</p>';
                        return;
                    }
                    
                    list.innerHTML = Object.entries(data).map(([droneId, status]) => `
                        <div class="status-item status-${status.status === 'success' ? 'success' : 
                                                       status.status === 'error' ? 'error' : 'pending'}">
                            <strong>Drone ${droneId}</strong><br>
                            <small>Firmware: ${status.firmware}</small><br>
                            <small>Status: ${status.status}</small><br>
                            <small>Time: ${status.timestamp}</small><br>
                            <small>Attempts: ${status.attempts}</small>
                        </div>
                    `).join('');
                })
                .catch(error => {
                    console.error('Error loading status:', error);
                    document.getElementById('status-list').innerHTML = '<p>Error loading status</p>';
                });
        }
        
        function loadDownloads() {
            fetch('/downloads')
                .then(response => response.json())
                .then(data => {
                    // Update stats
                    document.getElementById('active-downloads').textContent = data.current_concurrent;
                    document.getElementById('max-concurrent').textContent = data.max_concurrent;
                    document.getElementById('total-history').textContent = data.download_history.length;
                    
                    const list = document.getElementById('download-list');
                    
                    // Show active downloads
                    const activeDownloads = Object.values(data.active_downloads);
                    if (activeDownloads.length === 0) {
                        list.innerHTML = '<p>No active downloads</p>';
                    } else {
                        list.innerHTML = '<h3>Active Downloads:</h3>' + 
                            activeDownloads.map(download => `
                                <div class="download-item status-downloading">
                                    <strong>${download.client_ip}</strong><br>
                                    <small>Firmware: ${download.firmware_name}</small><br>
                                    <small>Speed: ${formatBytes(download.download_speed)}/s</small><br>
                                    <div class="progress-bar">
                                        <div class="progress-fill" style="width: ${download.progress_percentage}%"></div>
                                    </div>
                                    <small>${download.bytes_sent} / ${download.total_size} bytes (${download.progress_percentage.toFixed(1)}%)</small>
                                </div>
                            `).join('');
                    }
                    
                    // Show recent history
                    if (data.download_history.length > 0) {
                        const recentHistory = data.download_history.slice(-5); // Last 5 downloads
                        list.innerHTML += '<h3>Recent Downloads:</h3>' + 
                            recentHistory.map(download => `
                                <div class="download-item status-success">
                                    <strong>${download.client_ip}</strong><br>
                                    <small>Firmware: ${download.firmware_name}</small><br>
                                    <small>Completed: ${download.completion_time}</small><br>
                                    <small>Size: ${formatBytes(download.total_size)}</small>
                                </div>
                            `).join('');
                    }
                })
                .catch(error => {
                    console.error('Error loading downloads:', error);
                    document.getElementById('download-list').innerHTML = '<p>Error loading download status</p>';
                });
        }
        
        function formatBytes(bytes) {
            if (bytes === 0) return '0 Bytes';
            const k = 1024;
            const sizes = ['Bytes', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }
        
        // Load data on page load
        loadFirmware();
        loadStatus();
        loadDownloads();
        
        // Auto-refresh every 10 seconds for downloads, 30 seconds for others
        setInterval(() => {
            loadDownloads();
        }, 10000);
        
        setInterval(() => {
            loadFirmware();
            loadStatus();
        }, 30000);
    </script>
</body>
</html>
        """
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(html.encode())
    
    def send_firmware_list(self):
        """Send JSON list of available firmware files"""
        firmware_list = self.server.firmware_server.get_firmware_list()
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(firmware_list).encode())
    
    def send_firmware_file(self, filename):
        """Send firmware file for download with progress tracking"""
        firmware_path = self.server.firmware_server.firmware_dir / filename
        
        if not firmware_path.exists():
            self.send_error(404, "Firmware file not found")
            return
        
        try:
            # Get client IP
            client_ip = self.client_address[0]
            
            # Get file size
            file_size = firmware_path.stat().st_size
            
            # Start tracking download
            if not self.server.firmware_server.start_download(client_ip, filename, file_size):
                self.send_error(503, "Server busy - max concurrent downloads reached")
                return
            
            try:
                with open(firmware_path, 'rb') as f:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/octet-stream')
                    self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
                    self.send_header('Content-Length', str(file_size))
                    self.end_headers()
                    
                    bytes_sent = 0
                    chunk_size = 8192  # 8KB chunks
                    
                    while True:
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break
                        
                        self.wfile.write(chunk)
                        bytes_sent += len(chunk)
                        
                        # Update progress every 64KB (8 chunks)
                        if bytes_sent % (chunk_size * 8) == 0:
                            self.server.firmware_server.update_download_progress(client_ip, bytes_sent)
                    
                    # Final progress update
                    self.server.firmware_server.update_download_progress(client_ip, file_size)
                    
                logger.info(f"Firmware downloaded: {filename} to {client_ip} ({file_size} bytes)")
                
            finally:
                # Mark download as completed
                self.server.firmware_server.complete_download(client_ip)
                
        except Exception as e:
            logger.error(f"Error sending firmware file {filename}: {e}")
            self.send_error(500, "Error reading firmware file")
    
    def send_status_json(self):
        """Send JSON status of upload operations"""
        status = self.server.firmware_server.get_upload_status()
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(status).encode())
    
    def send_download_status_json(self):
        """Send JSON status of download operations"""
        download_status = self.server.firmware_server.get_download_status()
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(download_status).encode())
    
    def handle_upload_log(self):
        """Handle upload log POST request"""
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode())
            drone_id = data.get('drone_id')
            firmware = data.get('firmware')
            status = data.get('status', 'unknown')
            
            if drone_id and firmware:
                self.server.firmware_server.log_upload_attempt(drone_id, firmware, status)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'status': 'logged'}).encode())
            else:
                self.send_error(400, "Missing required fields")
                
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
        except Exception as e:
            logger.error(f"Error handling upload log: {e}")
            self.send_error(500, "Internal Server Error")
    
    def log_message(self, format, *args):
        """Override to use our logger"""
        logger.info(f"{self.address_string()} - {format % args}")

def main():
    parser = argparse.ArgumentParser(description='Clover Swarm Firmware Server')
    parser.add_argument('--port', type=int, default=8080, help='Server port (default: 8080)')
    parser.add_argument('--firmware-dir', default='firmware', help='Firmware directory (default: firmware)')
    parser.add_argument('--host', default='0.0.0.0', help='Host address (default: 0.0.0.0)')
    parser.add_argument('--max-downloads', type=int, default=8, help='Max concurrent downloads (default: 8)')
    
    args = parser.parse_args()
    
    # Create firmware server
    server = FirmwareServer(port=args.port, firmware_dir=args.firmware_dir, max_concurrent_downloads=args.max_downloads)
    
    logger.info("=== Clover Swarm Firmware Server ===")
    logger.info(f"Host: {args.host}")
    logger.info(f"Port: {args.port}")
    logger.info(f"Firmware Directory: {args.firmware_dir}")
    logger.info(f"Max Concurrent Downloads: {args.max_downloads}")
    logger.info("===================================")
    
    try:
        server.start()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 