#!/usr/bin/env python3
"""
ESP32 Communication Link Layer
Low-level interface for UART communication with ESP32 for ESP-NOW drone network
"""

import logging
import struct
import threading
import time
from typing import Any, Callable, Dict, Optional

import serial

from skyros.lib.packet_codec import pack_packet, unpack_header, unpack_packet
from skyros.lib.packet_generator import generate_ack_packet
from skyros.lib.packets import (
    CUSTOM_MESSAGE_SIZE,
    HEADER_SIZE,
    HEADER_FORMAT,
    MAX_PAYLOAD_SIZE,
    PACKET_PREAMBLE,
    CONFIG_SIZE,
    ConfigPacket,
    CustomMessagePacket,
    PacketHeader,
    PacketType,
    PingPacket,
    TelemetryPacket,
)
from skyros.lib.statistics import Statistics


class ESP32Link:
    """Low-level communication layer with ESP32 via UART"""

    def __init__(self, port: str = "/dev/ttyAMA1", baudrate: int = 921600, network_id: int = 0x12, wifi_channel: int = 1, tx_power: int = 11):
        self.port = port
        self.baudrate = baudrate
        self.network_id = network_id
        self.wifi_channel = wifi_channel
        self.tx_power = tx_power

        # UART connection
        self.serial_port: Optional[serial.Serial] = None
        self.running = False

        # Statistics
        self.stats = Statistics()

        # Optimized receive buffers
        self.rx_buffer = bytearray()
        self._buffer_lock = threading.Lock()
        
        # Pre-computed values for performance
        self._preamble_bytes = struct.pack("<H", PACKET_PREAMBLE)
        self._header_format = struct.Struct(HEADER_FORMAT)  # Pre-compiled struct - matches HEADER_FORMAT
        
        # Threading
        self._rx_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Callbacks
        self._packet_callbacks: Dict[int, Callable] = {}
        self._custom_message_callback: Optional[Callable[[str], None]] = None

        # Logger
        self.logger = logging.getLogger(f"ESP32Link-{port}")

    def connect(self) -> bool:
        """Establish UART connection to ESP32"""
        try:
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.close()
                time.sleep(0.1)

            self.serial_port = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.1,
                rtscts=True,  # Hardware flow control
                dsrdtr=False,
            )

            # Clear buffers
            self._clear_esp32_buffer(read_timeout=0.1, log_cleared=False)
            time.sleep(0.1)

            self.logger.info(f"Connected to ESP32 on {self.port} at {self.baudrate} baud")
            return True

        except Exception as e:
            self.logger.error(f"Failed to connect to ESP32: {e}")
            return False

    def disconnect(self):
        """Close UART connection"""
        self.stop()
        if self.serial_port and self.serial_port.is_open:
            self._clear_esp32_buffer(read_timeout=0.1, log_cleared=False)
            time.sleep(0.1)
            self.serial_port.close()
        self.logger.info("Disconnected from ESP32")

    def start(self) -> bool:
        """Start the communication link"""
        if not self.connect():
            return False

        # Send config packet to initialize ESP32
        self._send_config_packet()

        # Clear any old packets from ESP32 buffer after config
        self._clear_esp32_buffer()

        self.running = True
        self._rx_thread = threading.Thread(target=self._receive_thread, daemon=True)
        self._rx_thread.start()

        self.logger.info("ESP32 link started")
        return True

    def _send_config_packet(self):
        """Send configuration packet to ESP32"""
        try:
            header = PacketHeader(
                preamble=PACKET_PREAMBLE,
                payload_size=CONFIG_SIZE,
                packet_type=PacketType.CONFIG,
                network_id=self.network_id,
            )

            packet = ConfigPacket(
                header=header,
                network_id=self.network_id,
                wifi_channel=self.wifi_channel,
                tx_power=self.tx_power,
                crc=0,
            )

            if self.send_packet(packet):
                self.logger.info(f"Config packet sent: network_id={self.network_id}, wifi_channel={self.wifi_channel}, tx_power={self.tx_power}")
            else:
                self.logger.error("Failed to send config packet")
        except Exception as e:
            self.logger.error(f"Error sending config packet: {e}")

    def _clear_esp32_buffer(self, read_timeout: float = 0.5, log_cleared: bool = True):
        """Clear any old packets from ESP32 buffer
        
        Args:
            read_timeout: Time to read and discard data (default: 0.5s)
            log_cleared: Whether to log the number of cleared bytes (default: True)
        """
        try:
            if not self.serial_port or not self.serial_port.is_open:
                return

            # Clear local receive buffer
            self._reset_rx_state()
            
            # Clear UART buffers
            self.serial_port.reset_input_buffer()
            self.serial_port.reset_output_buffer()
            
            # Read and discard any remaining data from ESP32
            # This ensures old packets don't interfere with new communication
            discarded_bytes = 0
            start_time = time.time()
            
            while time.time() - start_time < read_timeout:
                if self.serial_port.in_waiting:
                    data = self.serial_port.read(self.serial_port.in_waiting)
                    discarded_bytes += len(data)
                else:
                    time.sleep(0.01)
            
            if discarded_bytes > 0 and log_cleared:
                self.logger.info(f"Cleared {discarded_bytes} bytes of old data from ESP32 buffer")
            
            # Final buffer reset to ensure clean state
            self.serial_port.reset_input_buffer()
            self._reset_rx_state()
            
        except Exception as e:
            self.logger.error(f"Error clearing ESP32 buffer: {e}")

    def stop(self):
        """Stop the communication link"""
        self.running = False
        if self._rx_thread and self._rx_thread.is_alive():
            self._rx_thread.join(timeout=1.0)
        self.logger.info("ESP32 link stopped")

    def _reset_rx_state(self):
        """Reset receive state machine"""
        with self._buffer_lock:
            self.rx_buffer.clear()

    def send_packet(self, packet) -> bool:
        """Send a packet to ESP32"""
        if not self.serial_port or not self.serial_port.is_open:
            return False

        try:
            with self._lock:
                # Pack packet if it's not already bytes
                if isinstance(packet, bytes):
                    data = packet
                    total_size = len(data)
                    packet_type = struct.unpack("<B", data[3:4])[0]
                else:
                    data = pack_packet(packet)
                    total_size = HEADER_SIZE + packet.header.payload_size
                    packet_type = packet.header.packet_type

                bytes_written = self.serial_port.write(data)
                self.serial_port.flush()

                if bytes_written == total_size:
                    # Batch statistics updates to reduce lock contention
                    self._update_send_stats(packet_type, bytes_written)
                    return True

        except Exception as e:
            self.logger.error(f"Failed to send packet: {e}")

        return False

    def _update_send_stats(self, packet_type: int, bytes_written: int):
        """Update send statistics without frequent locking"""
        # Use atomic operations where possible
        with self.stats.lock:
            self.stats.uart.packets_sent += 1
            self.stats.uart.bytes_sent += bytes_written
            self.stats.uart.packets_sent_by_type[packet_type] += 1
            self.stats.uart.bytes_sent_by_type[packet_type] += bytes_written

    def send_custom_message(self, message: str) -> bool:
        """Send a custom message (max 125 characters)"""
        if len(message) > 125:
            self.logger.warning(f"Message too long ({len(message)} chars), truncating to 125")
            message = message[:125]

        # Pad message to 126 bytes (125 chars + null terminator)
        message_bytes = message.encode("utf-8")[:125]
        custom_data = message_bytes + b"\x00" * (126 - len(message_bytes))

        header = PacketHeader(
            preamble=PACKET_PREAMBLE,
            payload_size=CUSTOM_MESSAGE_SIZE,
            packet_type=PacketType.CUSTOM_MESSAGE,
            network_id=self.network_id,
        )

        packet = CustomMessagePacket(
            header=header,
            custom_data=custom_data,
            crc=0,
        )

        return self.send_packet(packet)

    def send_telemetry(self, drone_id: int, x: float, y: float, z: float, vx: float, vy: float, vz: float) -> bool:
        """Send telemetry data"""
        header = PacketHeader(
            preamble=PACKET_PREAMBLE,
            payload_size=struct.calcsize("<Bffffff") + 2,  # +2 for CRC
            packet_type=PacketType.TELEMETRY,
            network_id=self.network_id,
        )

        packet = TelemetryPacket(
            header=header,
            drone_id=drone_id,
            x=x,
            y=y,
            z=z,
            vx=vx,
            vy=vy,
            vz=vz,
            crc=0,
        )

        return self.send_packet(packet)

    def set_packet_callback(self, packet_type: int, callback: Callable):
        """Set callback for specific packet type"""
        self._packet_callbacks[packet_type] = callback

    def set_custom_message_callback(self, callback: Callable[[str], None]):
        """Set callback for custom messages"""
        self._custom_message_callback = callback

    def _receive_thread(self):
        """Thread for receiving data from ESP32"""
        while self.running:
            try:
                if self.serial_port and self.serial_port.is_open:
                    if self.serial_port.in_waiting:
                        data = self.serial_port.read(self.serial_port.in_waiting)
                        if data:
                            self._process_received_data(data)
                    else:
                        time.sleep(0.01)  # Reduced sleep time for better responsiveness
                else:
                    time.sleep(0.01)
            except Exception as e:
                self.logger.error(f"Receive thread error: {e}")
                self._reset_rx_state()
                time.sleep(0.1)

    def _process_received_data(self, data: bytes):
        """Optimized packet processing using buffered approach"""
        try:
            with self._buffer_lock:
                self.rx_buffer.extend(data)
                
            # Process complete packets
            while True:
                packet_data = self._extract_packet()
                if packet_data is None:
                    break
                    
                self._handle_packet(packet_data)
                
        except Exception as e:
            self.logger.error(f"Packet processing failed: {e}")
            self._reset_rx_state()

    def _extract_packet(self) -> Optional[bytes]:
        """Extract a complete packet from buffer using optimized search"""
        with self._buffer_lock:
            if len(self.rx_buffer) < HEADER_SIZE:
                return None
                
            # Fast preamble search using string find
            preamble_pos = self.rx_buffer.find(self._preamble_bytes)
            if preamble_pos == -1:
                # No preamble found, keep only last byte for potential partial preamble
                if len(self.rx_buffer) > 1:
                    self.rx_buffer = self.rx_buffer[-1:]
                return None
                
            # Remove data before preamble
            if preamble_pos > 0:
                self.rx_buffer = self.rx_buffer[preamble_pos:]
                
            # Check if we have enough data for header
            if len(self.rx_buffer) < HEADER_SIZE:
                return None
                
            # Parse header
            try:
                header_data = self.rx_buffer[:HEADER_SIZE]
                header = self._header_format.unpack(header_data)
                preamble, payload_size, packet_type, network_id = header
                
                if preamble != PACKET_PREAMBLE:
                    # Invalid preamble, remove first byte and continue
                    self.rx_buffer = self.rx_buffer[1:]
                    return None
                    
                if payload_size < 2 or payload_size > MAX_PAYLOAD_SIZE:
                    # Invalid payload size, remove first byte and continue
                    self.rx_buffer = self.rx_buffer[1:]
                    return None
                    
                # Check if we have complete packet
                total_packet_size = HEADER_SIZE + payload_size
                if len(self.rx_buffer) < total_packet_size:
                    return None
                    
                # Extract complete packet
                packet_data = self.rx_buffer[:total_packet_size]
                self.rx_buffer = self.rx_buffer[total_packet_size:]
                
                return packet_data
                
            except struct.error:
                # Invalid header, remove first byte and continue
                self.rx_buffer = self.rx_buffer[1:]
                return None

    def _handle_packet(self, packet_data: bytes):
        """Handle a complete packet"""
        try:
            # Parse header
            header_data = packet_data[:HEADER_SIZE]
            header = self._header_format.unpack(header_data)
            preamble, payload_size, packet_type, network_id = header
            
            # Create header object
            header_obj = PacketHeader(preamble, payload_size, packet_type, network_id)
            
            # Parse payload
            payload = packet_data[HEADER_SIZE:]
            packet = unpack_packet(header_obj, payload)
            
            if packet:
                # Update statistics
                self._update_receive_stats(packet_type, HEADER_SIZE + payload_size)
                
                # Handle packet
                self._handle_received_packet(packet, packet_type)
            else:
                # Corrupted packet
                with self.stats.lock:
                    self.stats.uart.packets_corrupted += 1
                    
        except Exception as e:
            self.logger.debug(f"Packet handling failed: {e}")
            with self.stats.lock:
                self.stats.uart.packets_corrupted += 1

    def _update_receive_stats(self, packet_type: int, total_size: int):
        """Update receive statistics"""
        with self.stats.lock:
            self.stats.uart.packets_received += 1
            self.stats.uart.bytes_received += total_size
            self.stats.uart.packets_received_by_type[packet_type] += 1
            self.stats.uart.bytes_received_by_type[packet_type] += total_size

    def _handle_received_packet(self, packet, packet_type: int):
        """Handle received packet based on type"""
        try:
            # Handle ping packets automatically
            if isinstance(packet, PingPacket):
                ack = generate_ack_packet()
                self.send_packet(ack)

            # Handle custom messages
            elif isinstance(packet, CustomMessagePacket):
                if self._custom_message_callback:
                    # Extract string from custom data (remove null padding)
                    message = packet.custom_data.rstrip(b"\x00").decode("utf-8", errors="ignore")
                    self._custom_message_callback(message)

            # Call registered callbacks
            if packet_type in self._packet_callbacks:
                self._packet_callbacks[packet_type](packet)

        except Exception as e:
            self.logger.error(f"Error handling packet: {e}")

    def get_statistics(self) -> Dict[str, Any]:
        """Get communication statistics"""
        with self.stats.lock:
            return {
                "packets_sent": self.stats.uart.packets_sent,
                "packets_received": self.stats.uart.packets_received,
                "packets_corrupted": self.stats.uart.packets_corrupted,
                "bytes_sent": self.stats.uart.bytes_sent,
                "bytes_received": self.stats.uart.bytes_received,
                "uptime": time.time() - self.stats.start_time,
            }

    def is_connected(self) -> bool:
        """Check if ESP32 is connected"""
        return self.serial_port is not None and self.serial_port.is_open and self.running
