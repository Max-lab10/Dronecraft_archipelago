#!/usr/bin/env python3
"""
ESP Flasher and Testing Library
Provides functions for automatic ESP flashing and ESP-NOW testing
"""

import re
import time
import serial
import serial.tools.list_ports
import threading
import subprocess
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from pathlib import Path
import logging


@dataclass
class ESPStats:
    """ESP statistics parsed from UART output"""
    packets_sent_espnow: int = 0
    packets_received_espnow: int = 0
    packets_sent_uart: int = 0 
    packets_received_uart: int = 0
    test_packets_sent: int = 0
    uptime_ms: int = 0
    last_update: float = 0.0
    espnow_tx_pps: float = 0.0
    espnow_rx_pps: float = 0.0


class UARTParser:
    """Parser for ESP UART output to extract statistics"""
    
    def __init__(self):
        self.logger = logging.getLogger("UARTParser")
        
        # Regex patterns for parsing ESP output
        self.patterns = {
            'espnow_tx': re.compile(r'TX: (\d+) packets, (\d+) bytes'),
            'espnow_rx': re.compile(r'RX: (\d+) packets, (\d+) bytes, (\d+) corrupted'),
            'test_packets': re.compile(r'TEST: Total test packets sent: (\d+)'),
            'uptime': re.compile(r'Uptime: (\d+) ms'),
            'heartbeat': re.compile(r'HEARTBEAT: Drone (\d+) - Uptime: (\d+) ms'),
            # Updated patterns for new statistics format (no sliding window)
            'espnow_rates': re.compile(r'ESP-NOW Rates: TX=([\d.]+) pps, RX=([\d.]+) pps'),
            'uart_rates': re.compile(r'UART Rates: TX=([\d.]+) pps, RX=([\d.]+) pps'),
            # Patterns for ESP32 BRIDGE STATISTICS section
            'espnow_interface_tx': re.compile(r'ESP-NOW INTERFACE.*?TX: (\d+) packets, (\d+) bytes'),
            'espnow_interface_rx': re.compile(r'ESP-NOW INTERFACE.*?RX: (\d+) packets, (\d+) bytes, (\d+) corrupted'),
            'uart_interface_tx': re.compile(r'UART INTERFACE.*?TX: (\d+) packets, (\d+) bytes'),
            'uart_interface_rx': re.compile(r'UART INTERFACE.*?RX: (\d+) packets, (\d+) bytes, (\d+) corrupted'),
        }
    
    def parse_statistics_block(self, text: str) -> Optional[ESPStats]:
        """Parse ESP statistics block and return extracted stats"""
        stats = ESPStats()
        stats.last_update = time.time()
        
        # Debug: print the text being parsed
        self.logger.debug(f"Parsing text: {text[:200]}...")
        
        # Find ESP-NOW section specifically
        espnow_section = ""
        uart_section = ""
        lines = text.split('\n')
        in_espnow_section = False
        in_uart_section = False
        
        for line in lines:
            if "--- ESP-NOW INTERFACE ---" in line:
                in_espnow_section = True
                in_uart_section = False
                espnow_section += line + "\n"
                continue
            elif "--- UART INTERFACE ---" in line:
                in_uart_section = True
                in_espnow_section = False
                uart_section += line + "\n"
                continue
            elif in_espnow_section:
                if "===" in line or "---" in line:
                    # End of ESP-NOW section
                    in_espnow_section = False
                else:
                    espnow_section += line + "\n"
            elif in_uart_section:
                if "===" in line or "---" in line:
                    # End of UART section
                    in_uart_section = False
                else:
                    uart_section += line + "\n"
        
        self.logger.debug(f"ESP-NOW section: {espnow_section}")
        self.logger.debug(f"UART section: {uart_section}")
        
        # Parse ESP-NOW TX packets from the specific section
        match = re.search(r'TX: (\d+) packets, (\d+) bytes', espnow_section)
        if match:
            stats.packets_sent_espnow = int(match.group(1))
            self.logger.debug(f"Found ESP-NOW TX packets: {stats.packets_sent_espnow}")
        
        # Parse ESP-NOW RX packets from the specific section
        match = re.search(r'RX: (\d+) packets, (\d+) bytes, (\d+) corrupted', espnow_section)
        if match:
            stats.packets_received_espnow = int(match.group(1))
            self.logger.debug(f"Found ESP-NOW RX packets: {stats.packets_received_espnow}")
        
        # Parse UART TX packets from the specific section
        match = re.search(r'TX: (\d+) packets, (\d+) bytes', uart_section)
        if match:
            stats.packets_sent_uart = int(match.group(1))
            self.logger.debug(f"Found UART TX packets: {stats.packets_sent_uart}")
        
        # Parse UART RX packets from the specific section
        match = re.search(r'RX: (\d+) packets, (\d+) bytes, (\d+) corrupted', uart_section)
        if match:
            stats.packets_received_uart = int(match.group(1))
            self.logger.debug(f"Found UART RX packets: {stats.packets_received_uart}")
        
        # Parse ESP-NOW PPS rates (now using simple averaging over 10 seconds)
        match = re.search(r'ESP-NOW Rates: TX=([\d.]+) pps, RX=([\d.]+) pps', espnow_section)
        if match:
            stats.espnow_tx_pps = float(match.group(1))
            stats.espnow_rx_pps = float(match.group(2))
            self.logger.debug(f"Found ESP-NOW PPS: TX={stats.espnow_tx_pps}, RX={stats.espnow_rx_pps}")
        else:
            # Try to find ESP-NOW Rates in the entire text
            match = re.search(r'ESP-NOW Rates: TX=([\d.]+) pps, RX=([\d.]+) pps', text)
            if match:
                stats.espnow_tx_pps = float(match.group(1))
                stats.espnow_rx_pps = float(match.group(2))
                self.logger.debug(f"Found ESP-NOW PPS in full text: TX={stats.espnow_tx_pps}, RX={stats.espnow_rx_pps}")
            else:
                self.logger.debug("No ESP-NOW PPS pattern found")
        
        # Parse test packets sent
        match = self.patterns['test_packets'].search(text)
        if match:
            stats.test_packets_sent = int(match.group(1))
            self.logger.debug(f"Found test packets: {stats.test_packets_sent}")
        else:
            self.logger.debug("No test packets pattern found")
            
        # Parse uptime
        match = self.patterns['uptime'].search(text)
        if match:
            stats.uptime_ms = int(match.group(1))
        
        # Parse heartbeat (alternative uptime source)
        match = self.patterns['heartbeat'].search(text)
        if match:
            stats.uptime_ms = int(match.group(2))
            
        return stats


class ESPDevice:
    """Represents an ESP device with serial connection and statistics"""
    
    def __init__(self, port: str, name: str = "ESP"):
        self.port = port
        self.name = name
        self.serial_conn: Optional[serial.Serial] = None
        self.stats = ESPStats()
        self.parser = UARTParser()
        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.logger = logging.getLogger(f"ESPDevice-{name}")
        
    def connect(self, baudrate: int = 115200, timeout: float = 1.0) -> bool:
        """Connect to ESP device via serial"""
        try:
            # Close any existing connection
            if self.serial_conn and self.serial_conn.is_open:
                self.serial_conn.close()
            
            # Wait a moment for port to stabilize (especially for ESP32-S2)
            time.sleep(0.5)
            
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=baudrate,
                timeout=timeout,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE
            )
            
            # Test the connection by reading any available data
            if self.serial_conn.in_waiting > 0:
                self.serial_conn.read(self.serial_conn.in_waiting)
            
            self.logger.info(f"Connected to {self.name} on {self.port}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to {self.name} on {self.port}: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from ESP device"""
        self.stop_monitoring()
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            self.logger.info(f"Disconnected from {self.name}")
    
    def start_monitoring(self):
        """Start monitoring ESP output in background thread"""
        if self.running:
            return
            
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        self.logger.info(f"Started monitoring {self.name}")
    
    def stop_monitoring(self):
        """Stop monitoring ESP output"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2.0)
            self.monitor_thread = None
        self.logger.info(f"Stopped monitoring {self.name}")
    
    def _monitor_loop(self):
        """Background thread loop for monitoring ESP output"""
        buffer = ""
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        while self.running:
            try:
                # Check if connection is still valid
                if not self.serial_conn or not self.serial_conn.is_open:
                    self.logger.warning(f"Serial connection to {self.name} lost, stopping monitor")
                    break
                
                if self.serial_conn.in_waiting > 0:
                    data = self.serial_conn.read(self.serial_conn.in_waiting).decode('utf-8', errors='ignore')
                    buffer += data
                    
                    # Process complete lines
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        self._process_line(line.strip())
                    
                    consecutive_errors = 0  # Reset error counter on successful read
                
                time.sleep(0.1)
                
            except serial.SerialException as e:
                consecutive_errors += 1
                if consecutive_errors <= max_consecutive_errors:
                    self.logger.warning(f"Serial error in {self.name} monitor (attempt {consecutive_errors}): {e}")
                    time.sleep(1.0)  # Wait longer between retries
                else:
                    self.logger.error(f"Too many consecutive serial errors in {self.name} monitor, stopping")
                    break
            except Exception as e:
                consecutive_errors += 1
                if consecutive_errors <= max_consecutive_errors:
                    self.logger.warning(f"Error in {self.name} monitor loop (attempt {consecutive_errors}): {e}")
                    time.sleep(0.5)
                else:
                    self.logger.error(f"Too many consecutive errors in {self.name} monitor, stopping")
                    break
    
    def _process_line(self, line: str):
        """Process a line of ESP output"""
        # Look for statistics blocks
        if "=== ESP32 BRIDGE STATISTICS ===" in line:
            # Collect next few lines for statistics parsing
            stats_block = line + "\n"
            try:
                # Read more lines for complete statistics
                for _ in range(20):  # Read up to 20 more lines
                    if self.serial_conn and self.serial_conn.in_waiting > 0:
                        next_line = self.serial_conn.readline().decode('utf-8', errors='ignore').strip()
                        stats_block += next_line + "\n"
                        if "================================" in next_line:
                            break
                
                # Parse the complete statistics block
                new_stats = self.parser.parse_statistics_block(stats_block)
                if new_stats:
                    self.stats = new_stats
                    self.logger.debug(f"Updated stats: TX={self.stats.packets_sent_espnow}, RX={self.stats.packets_received_espnow}, Test={self.stats.test_packets_sent}")
                    
            except Exception as e:
                self.logger.error(f"Failed to parse statistics: {e}")
        
        # Look for ESP-NOW Rates in individual lines
        elif "ESP-NOW Rates:" in line:
            match = re.search(r'ESP-NOW Rates: TX=([\d.]+) pps, RX=([\d.]+) pps', line)
            if match:
                self.stats.espnow_tx_pps = float(match.group(1))
                self.stats.espnow_rx_pps = float(match.group(2))
                self.stats.last_update = time.time()
                self.logger.debug(f"Updated ESP-NOW PPS: TX={self.stats.espnow_tx_pps}, RX={self.stats.espnow_rx_pps}")
        
        # Also catch individual test packet updates
        elif "TEST: Total test packets sent:" in line:
            match = re.search(r'TEST: Total test packets sent: (\d+)', line)
            if match:
                self.stats.test_packets_sent = int(match.group(1))
                self.stats.last_update = time.time()


def detect_esp_ports() -> List[str]:
    """Detect available ESP device ports"""
    ports = []
    
    try:
        # Get all available serial ports
        available_ports = serial.tools.list_ports.comports()
        
        for port in available_ports:
            # Filter for ESP32 devices (common patterns)
            port_name = port.device
            
            # Common ESP32 port patterns
            if any(pattern in port_name.lower() for pattern in [
                'ttyacm', 'ttyusb', 'cu.usbserial', 'cu.wchusbserial',
                'cu.silabs', 'cu.slab', 'cu.ftdi'
            ]):
                ports.append(port_name)
        
        # Sort ports for consistent ordering
        ports.sort()
        
    except Exception as e:
        logging.getLogger("ESPFlasher").warning(f"Error detecting ESP ports: {e}")
    
    return ports


def detect_new_esp_ports(previous_ports: List[str]) -> List[str]:
    """Detect newly connected ESP ports by comparing with previous port list"""
    current_ports = detect_esp_ports()
    new_ports = [p for p in current_ports if p not in previous_ports]
    return new_ports


def _find_esp_port_after_flash(original_port: str, timeout: float = 30.0, exclude_ports: List[str] = None) -> Optional[str]:
    """Find ESP port after flashing (handles ESP32-S2 USB CDC reset)"""
    logger = logging.getLogger("ESPFlasher")
    
    time.sleep(2)

    if exclude_ports is None:
        exclude_ports = []
    
    start_time = time.time()
    retry_count = 0
    max_retries = 5
    
    while time.time() - start_time < timeout:
        try:
            available_ports = detect_esp_ports()
            
            # Filter out excluded ports (ports already in use)
            available_ports = [p for p in available_ports if p not in exclude_ports]
            
            if not available_ports:
                retry_count += 1
                if retry_count <= max_retries:
                    wait_time = min(2.0 * retry_count, 10.0)  # Exponential backoff, max 10s
                    logger.debug(f"No available ESP ports found, retrying in {wait_time}s (attempt {retry_count}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    logger.warning(f"No available ESP ports found after {max_retries} retries")
                    break
                continue
            
            # First, check if original port is still available and not excluded
            if original_port in available_ports:
                logger.info(f"Found original port {original_port} after flash")
                return original_port
            
            # If not, look for any available port
            if available_ports:
                selected_port = available_ports[0]
                logger.info(f"Original port {original_port} not found, using {selected_port}")
                return selected_port
                
        except Exception as e:
            logger.warning(f"Error detecting ports: {e}")
            time.sleep(1.0)
    
    logger.warning(f"Could not find ESP port after flash within {timeout}s")
    return None


def flash_esp(port: str, environment: str = "lolin_s2_mini_test", esp_project_path: str = "esp", exclude_ports: List[str] = None) -> Tuple[bool, str]:
    """Flash ESP device using PlatformIO with fallback to direct esptool. Returns (success, actual_port)"""
    logger = logging.getLogger("ESPFlasher")
    
    if exclude_ports is None:
        exclude_ports = []
    
    # First try with PlatformIO
    try:
        cmd = [
            "pio", "run", 
            "--environment", environment,
            "--upload-port", port,
            "--target", "upload"
        ]
        
        logger.info(f"Flashing ESP on {port} with environment {environment}")
        logger.debug(f"Command: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            cwd=esp_project_path,
            capture_output=True,
            text=True,
            timeout=120  # 2 minute timeout
        )
        
        if result.returncode == 0:
            logger.info(f"Successfully flashed ESP on {port}")
            # Find the actual port after flash (ESP32-S2 may change ports)
            actual_port = _find_esp_port_after_flash(port, exclude_ports=exclude_ports)
            return True, actual_port or port
        else:
            logger.warning(f"PlatformIO flash failed, trying direct esptool method")
            logger.debug(f"PIO Error: {result.stderr}")
            
    except subprocess.TimeoutExpired:
        logger.warning(f"PlatformIO timeout, trying direct esptool method")
    except Exception as e:
        logger.warning(f"PlatformIO exception: {e}, trying direct esptool method")
    
    # Fallback to direct esptool (especially for problematic USB-CDC devices)
    success = _flash_esp_direct(port, environment, esp_project_path)
    if success:
        actual_port = _find_esp_port_after_flash(port, exclude_ports=exclude_ports)
        return True, actual_port or port
    else:
        return False, port


def _flash_esp_direct(port: str, environment: str, esp_project_path: str) -> bool:
    """Flash ESP directly using esptool (fallback method)"""
    logger = logging.getLogger("ESPFlasher")
    
    try:
        import os
        from pathlib import Path
        
        # Determine chip type and build directory based on environment
        if "lolin_s2" in environment:
            chip = "esp32s2"
            build_dir = f".pio/build/{environment}"
        elif "esp32c3" in environment:
            chip = "esp32c3"
            build_dir = f".pio/build/{environment}"
        else:
            chip = "esp32"
            build_dir = f".pio/build/{environment}"
        
        esp_path = Path(esp_project_path).resolve()
        build_path = esp_path / build_dir
        
        # Check if build files exist
        firmware_bin = build_path / "firmware.bin"
        bootloader_bin = build_path / "bootloader.bin"
        partitions_bin = build_path / "partitions.bin"
        
        if not all(f.exists() for f in [firmware_bin, bootloader_bin, partitions_bin]):
            logger.error(f"Build files not found in {build_path}. Run 'pio run -e {environment}' first.")
            return False
        
        # Get esptool path
        esptool_path = Path.home() / ".platformio/packages/tool-esptoolpy/esptool.py"
        boot_app0_path = Path.home() / ".platformio/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin"
        
        if not esptool_path.exists():
            logger.error("esptool.py not found in PlatformIO packages")
            return False
        
        # Build esptool command
        cmd = [
            "python3", str(esptool_path),
            "--chip", chip,
            "--port", port,
            "--baud", "460800",
            "--before", "no_reset",  # Skip DTR/RTS reset that causes issues
            "write_flash", "-z",
            "--flash_mode", "dio",
            "--flash_freq", "80m" if chip == "esp32s2" else "40m",
            "--flash_size", "4MB",
            "0x1000", str(bootloader_bin),
            "0x8000", str(partitions_bin),
            "0xe000", str(boot_app0_path),
            "0x10000", str(firmware_bin)
        ]
        
        logger.info(f"Trying direct esptool flash on {port}")
        logger.debug(f"Command: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode == 0:
            logger.info(f"Successfully flashed ESP on {port} using direct esptool")
            return True
        else:
            logger.error(f"Direct esptool flash failed on {port}")
            logger.error(f"Error: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"Exception in direct esptool flash: {e}")
        return False


def wait_for_esp_ready(esp_device: ESPDevice, timeout: float = 30.0) -> bool:
    """Wait for ESP to boot and be ready (handles ESP32-S2 USB CDC reset)"""
    logger = logging.getLogger("ESPFlasher")
    
    start_time = time.time()
    original_port = esp_device.port
    
    logger.info(f"Waiting for {esp_device.name} to be ready...")
    logger.info("ESP32-S2 may reset USB CDC after flash, waiting for port to stabilize...")
    
    # ESP32-S2 specific: wait a bit longer for USB CDC to stabilize after reset
    time.sleep(5.0)
    
    # Try to reconnect if connection was lost during reset
    max_reconnect_attempts = 5  # Increased from 3
    for attempt in range(max_reconnect_attempts):
        try:
            if not esp_device.serial_conn or not esp_device.serial_conn.is_open:
                logger.info(f"Attempting to reconnect to {esp_device.name} (attempt {attempt + 1})")
                
                # Check if original port still exists, or find new port
                available_ports = detect_esp_ports()
                target_port = original_port
                
                if original_port not in available_ports:
                    if available_ports:
                        # Try to find the most likely port (usually the one that was just flashed)
                        # For ESP32-S2, the port might change after reset
                        target_port = available_ports[0]  # Take first available
                        logger.info(f"Original port {original_port} not available, using {target_port}")
                        esp_device.port = target_port
                    else:
                        logger.warning("No ESP ports available, waiting...")
                        time.sleep(3.0)  # Increased wait time
                        continue
                
                # Try to reconnect
                esp_device.disconnect()
                time.sleep(1.0)  # Brief pause before reconnecting
                if esp_device.connect():
                    logger.info(f"Reconnected to {esp_device.name} on {target_port}")
                    break
                else:
                    logger.warning(f"Failed to reconnect, attempt {attempt + 1}")
                    time.sleep(3.0)  # Increased wait time
            else:
                break
                
        except Exception as e:
            logger.warning(f"Reconnect attempt {attempt + 1} failed: {e}")
            time.sleep(3.0)  # Increased wait time
    
    # Start monitoring if not already started
    if not esp_device.running:
        esp_device.start_monitoring()
    
    # Wait for data with extended timeout for ESP32-S2
    while time.time() - start_time < timeout:
        # Check if we're receiving any data
        if esp_device.stats.last_update > start_time:
            logger.info(f"{esp_device.name} is ready!")
            return True
        
        # Check for connection issues
        if esp_device.serial_conn and not esp_device.serial_conn.is_open:
            logger.warning("Serial connection lost, attempting reconnect...")
            if not esp_device.connect():
                logger.error("Failed to reconnect")
                return False
            esp_device.start_monitoring()
        
        time.sleep(1.0)
    
    logger.error(f"Timeout waiting for {esp_device.name} to be ready")
    return False


def test_espnow_communication(master_esp: ESPDevice, slave_esp: ESPDevice, 
                             test_duration: float = 30.0, min_packets: int = 200) -> Tuple[bool, Dict]:
    """Test bidirectional ESP-NOW communication between two ESP devices"""
    logger = logging.getLogger("ESPNOWTest")
    
    logger.info(f"Starting bidirectional ESP-NOW test: {master_esp.name} <-> {slave_esp.name}")
    logger.info(f"Test duration: {test_duration}s, minimum PPS per direction: {min_packets}")
    
    # Reset statistics - track both directions
    initial_master_sent = master_esp.stats.test_packets_sent
    initial_master_received = master_esp.stats.packets_received_espnow
    initial_slave_sent = slave_esp.stats.test_packets_sent
    initial_slave_received = slave_esp.stats.packets_received_espnow
    
    # Wait a moment for statistics to stabilize
    time.sleep(2.0)
    
    start_time = time.time()
    
    # Track PPS values over time for averaging
    master_rx_pps_samples = []
    slave_rx_pps_samples = []
    
    # Wait for statistics to stabilize (at least 10 seconds for new averaging logic)
    logger.info("Waiting for statistics to stabilize (10s averaging period)...")
    time.sleep(12.0)  # Wait for first complete 10s statistics cycle
    
    # Monitor for test duration
    while time.time() - start_time < test_duration:
        time.sleep(1.0)
        
        # Check if connections are still valid
        if not master_esp.serial_conn or not master_esp.serial_conn.is_open:
            logger.error("Master ESP connection lost during test")
            break
        if not slave_esp.serial_conn or not slave_esp.serial_conn.is_open:
            logger.error("Slave ESP connection lost during test")
            break
        
        # Collect PPS samples (using 10-second averaged values)
        if master_esp.stats.espnow_rx_pps > 0:
            master_rx_pps_samples.append(master_esp.stats.espnow_rx_pps)
        if slave_esp.stats.espnow_rx_pps > 0:
            slave_rx_pps_samples.append(slave_esp.stats.espnow_rx_pps)
        
        # Log progress every 5 seconds with PPS values
        elapsed = time.time() - start_time
        if int(elapsed) % 5 == 0:
            master_tx_pps = master_esp.stats.espnow_tx_pps
            master_rx_pps = master_esp.stats.espnow_rx_pps
            slave_tx_pps = slave_esp.stats.espnow_tx_pps
            slave_rx_pps = slave_esp.stats.espnow_rx_pps
            
            # Calculate current averages for display (last 5 samples)
            current_master_avg = sum(master_rx_pps_samples[-5:]) / min(len(master_rx_pps_samples), 5) if master_rx_pps_samples else 0.0
            current_slave_avg = sum(slave_rx_pps_samples[-5:]) / min(len(slave_rx_pps_samples), 5) if slave_rx_pps_samples else 0.0
            
            logger.info(f"PPS: {elapsed:.0f}s - Master TX={master_tx_pps:.1f} RX={master_rx_pps:.1f} (5s_avg={current_master_avg:.1f}), Slave TX={slave_tx_pps:.1f} RX={slave_rx_pps:.1f} (5s_avg={current_slave_avg:.1f})")
    
    # Calculate average PPS over the test duration (using 10-second averaged values)
    avg_master_rx_pps = sum(master_rx_pps_samples) / len(master_rx_pps_samples) if master_rx_pps_samples else 0.0
    avg_slave_rx_pps = sum(slave_rx_pps_samples) / len(slave_rx_pps_samples) if slave_rx_pps_samples else 0.0
    
    # Final statistics
    final_master_sent = master_esp.stats.test_packets_sent - initial_master_sent
    final_master_received = master_esp.stats.packets_received_espnow - initial_master_received
    final_slave_sent = slave_esp.stats.test_packets_sent - initial_slave_sent
    final_slave_received = slave_esp.stats.packets_received_espnow - initial_slave_received
    
    # Get final PPS rates
    master_tx_pps = master_esp.stats.espnow_tx_pps
    master_rx_pps = master_esp.stats.espnow_rx_pps
    slave_tx_pps = slave_esp.stats.espnow_tx_pps
    slave_rx_pps = slave_esp.stats.espnow_rx_pps
    
    # Calculate success based on average PPS rates
    min_pps_threshold = float(min_packets)
    master_success = avg_master_rx_pps >= min_pps_threshold
    slave_success = avg_slave_rx_pps >= min_pps_threshold
    success = master_success and slave_success
    
    # Calculate total statistics
    total_sent = final_master_sent + final_slave_sent
    total_received = final_master_received + final_slave_received
    
    results = {
        'success': success,
        'master_sent': final_master_sent,
        'master_received': final_master_received,
        'slave_sent': final_slave_sent,
        'slave_received': final_slave_received,
        'total_sent': total_sent,
        'total_received': total_received,
        'test_duration': test_duration,
        'min_packets_required': min_packets,
        'packet_loss_rate': max(0, (total_sent - total_received) / max(total_sent, 1)) * 100,
        'master_success': master_success,
        'slave_success': slave_success,
        'master_tx_pps': master_tx_pps,
        'master_rx_pps': master_rx_pps,
        'slave_tx_pps': slave_tx_pps,
        'slave_rx_pps': slave_rx_pps,
        'avg_master_rx_pps': avg_master_rx_pps,
        'avg_slave_rx_pps': avg_slave_rx_pps
    }
    
    logger.info(f"Test completed: Success={success}")
    logger.info(f"Master: {final_master_sent} sent, {final_master_received} received, TX={master_tx_pps:.1f} pps, RX={master_rx_pps:.1f} pps (avg={avg_master_rx_pps:.1f})")
    logger.info(f"Slave: {final_slave_sent} sent, {final_slave_received} received, TX={slave_tx_pps:.1f} pps, RX={slave_rx_pps:.1f} pps (avg={avg_slave_rx_pps:.1f})")
    logger.info(f"Total: {total_sent} sent, {total_received} received")
    logger.info(f"Packet loss rate: {results['packet_loss_rate']:.1f}%")
    logger.info(f"PPS Success (using 10s averaged values): Master RX avg={avg_master_rx_pps:.1f} >= {min_pps_threshold}, Slave RX avg={avg_slave_rx_pps:.1f} >= {min_pps_threshold}")
    
    return success, results