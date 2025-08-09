#!/usr/bin/env python3
"""
UART Stress Test for Raspberry Pi 4
Communicates with ESP32 via UART with hardware flow control
Internal testing tool for link library
"""

import signal
import struct
import sys
import threading
import time

import serial

from skyros.lib.packet_codec import pack_packet, unpack_header, unpack_packet
from skyros.lib.packet_generator import generate_ack_packet, generate_random_packet
from skyros.lib.packets import (
    HEADER_SIZE,
    MAX_PAYLOAD_SIZE,
    PACKET_PREAMBLE,
    PingPacket,
    StatusPacket,
)
from skyros.lib.statistics import Statistics


class UARTStressTest:
    def __init__(self):
        # UART settings
        self.serial_port = None
        self.stats = Statistics()
        self.running = False

        # Buffers
        self.rx_buffer = bytearray()
        self.header_buffer = bytearray()
        self.searching_preamble = True

    def send_packet(self, packet) -> bool:
        """Send a packet with hardware flow control"""
        if not self.serial_port:
            return False

        try:
            # If packet is already bytes (bulk data), use it directly
            if isinstance(packet, bytes):
                data = packet
                total_size = len(data)
                packet_type = struct.unpack("<B", data[3:4])[0]
            else:
                # Otherwise pack the packet object
                data = pack_packet(packet)
                total_size = HEADER_SIZE + packet.header.payload_size
                packet_type = packet.header.packet_type

            bytes_written = self.serial_port.write(data)
            self.serial_port.flush()

            if bytes_written == total_size:
                with self.stats.lock:
                    self.stats.uart.packets_sent += 1
                    self.stats.uart.bytes_sent += bytes_written
                    self.stats.uart.packets_sent_by_type[packet_type] += 1
                    self.stats.uart.bytes_sent_by_type[packet_type] += bytes_written
                return True

        except Exception as e:
            print(f"ERROR: Failed to send packet - {e}")

        return False

    def process_received_data(self, data: bytes) -> None:
        """Process received data"""
        try:
            for byte in data:
                if self.searching_preamble:
                    self.header_buffer.append(byte)
                    if len(self.header_buffer) >= 2:
                        potential_preamble = (self.header_buffer[-1] << 8) | self.header_buffer[-2]
                        if potential_preamble == PACKET_PREAMBLE:
                            # Found preamble, keep only the last 2 bytes
                            self.header_buffer = bytearray(self.header_buffer[-2:])
                            self.searching_preamble = False
                        elif len(self.header_buffer) > 2:
                            # Keep only the last byte
                            self.header_buffer = bytearray([self.header_buffer[-1]])
                else:
                    self.header_buffer.append(byte)

                    # Process header
                    if len(self.header_buffer) == HEADER_SIZE:
                        try:
                            header = unpack_header(bytes(self.header_buffer))
                            if header is None:
                                raise ValueError("Invalid header")

                            if header.payload_size < 2 or header.payload_size > MAX_PAYLOAD_SIZE:
                                raise ValueError(f"Invalid payload size: {header.payload_size}")

                            # Start receiving payload
                            self.rx_buffer = bytearray()
                            continue

                        except Exception as e:
                            print(f"ERROR: Header processing failed - {e}")
                            self.searching_preamble = True
                            self.header_buffer = bytearray([byte])
                            with self.stats.lock:
                                self.stats.uart.packets_corrupted += 1
                            continue

                    # Process payload
                    elif len(self.header_buffer) > HEADER_SIZE:
                        try:
                            current_header = unpack_header(bytes(self.header_buffer[:HEADER_SIZE]))
                            if current_header is None:
                                raise ValueError("Invalid header during payload processing")

                            self.rx_buffer.append(byte)

                            # Check for payload completion
                            if len(self.rx_buffer) == current_header.payload_size:
                                packet = unpack_packet(current_header, bytes(self.rx_buffer))
                                if packet:
                                    with self.stats.lock:
                                        self.stats.uart.packets_received += 1
                                        total_size = HEADER_SIZE + current_header.payload_size
                                        self.stats.uart.bytes_received += total_size
                                        self.stats.uart.packets_received_by_type[
                                            current_header.packet_type
                                        ] += 1
                                        self.stats.uart.bytes_received_by_type[
                                            current_header.packet_type
                                        ] += total_size

                                    # Handle the packet
                                    self.handle_received_packet(packet, current_header.packet_type)
                                else:
                                    with self.stats.lock:
                                        self.stats.uart.packets_corrupted += 1

                                # Start searching for the next packet
                                self.searching_preamble = True
                                self.header_buffer = bytearray([byte])
                                self.rx_buffer = bytearray()

                            elif len(self.rx_buffer) > current_header.payload_size:
                                raise ValueError("Payload buffer overflow")

                        except Exception as e:
                            print(f"ERROR: Payload processing failed - {e}")
                            self.searching_preamble = True
                            self.header_buffer = bytearray([byte])
                            self.rx_buffer = bytearray()
                            with self.stats.lock:
                                self.stats.uart.packets_corrupted += 1
                            continue

        except Exception as e:
            print(f"ERROR: Packet processing failed - {e}")
            self.searching_preamble = True
            self.header_buffer = bytearray()
            self.rx_buffer = bytearray()

    def handle_received_packet(self, packet, packet_type: int):
        """Handle a received packet based on its type"""
        # Only handle ping packets with ACK response, no verbose logging
        if isinstance(packet, PingPacket):
            # Respond to a ping packet
            ack = generate_ack_packet()
            self.send_packet(ack)

        # Check for critical status packets that indicate errors
        elif isinstance(packet, StatusPacket):
            if packet.status_code == 4 or packet.error_flags != 0 or packet.battery_mv < 3400:
                print(
                    f"ERROR: Critical drone status - drone_{packet.drone_id}, "
                    f"Status={packet.status_code}, Battery={packet.battery_mv}mV, "
                    f"Errors=0x{packet.error_flags:04X}"
                )

    def receive_thread(self):
        """Thread for receiving data"""
        while self.running:
            try:
                if self.serial_port and self.serial_port.is_open:
                    if self.serial_port.in_waiting:
                        data = self.serial_port.read(self.serial_port.in_waiting)
                        if data:
                            self.process_received_data(data)
                else:
                    # Short pause if no data
                    time.sleep(0.001)
            except Exception as e:
                print(f"ERROR: Receive thread failed - {e}")
                # Reset receive state
                self.searching_preamble = True
                self.header_buffer = bytearray()
                self.rx_buffer = bytearray()
                time.sleep(0.1)

    def print_statistics(self):
        """Print statistics"""
        current_time = time.time()

        with self.stats.lock:
            elapsed_time = current_time - self.stats.start_time
            interval_time = current_time - self.stats.last_stats_time

            if interval_time >= 10.0:  # Print stats every 10 seconds
                print(f"\n=== UART STATS (Uptime: {elapsed_time:.0f}s) ===")
                print(
                    f"TX: {self.stats.uart.packets_sent} packets, {self.stats.uart.bytes_sent} bytes"
                )
                print(
                    f"RX: {self.stats.uart.packets_received} packets, {self.stats.uart.bytes_received} bytes"
                )
                print(f"Corrupted: {self.stats.uart.packets_corrupted}")

                if elapsed_time > 0:
                    tx_rate = self.stats.uart.packets_sent / elapsed_time
                    rx_rate = self.stats.uart.packets_received / elapsed_time
                    print(f"Rates: TX={tx_rate:.1f} pps, RX={rx_rate:.1f} pps")

                total_rx = self.stats.uart.packets_received + self.stats.uart.packets_corrupted
                if total_rx > 0:
                    error_rate = (self.stats.uart.packets_corrupted * 100.0) / total_rx
                    print(f"Error Rate: {error_rate:.2f}%")

                print("=" * 40)

                self.stats.last_stats_time = current_time

    def signal_handler(self, signum, frame):
        """Signal handler for graceful shutdown"""
        print("\nStopping UART stress test...")
        self.running = False

        # Allow time for data reception to finish
        time.sleep(0.1)

        if self.serial_port and self.serial_port.is_open:
            # Signal ESP32 to stop
            self.serial_port.reset_output_buffer()
            self.serial_port.reset_input_buffer()
            time.sleep(0.1)  # Allow time for buffer clearing
            self.serial_port.close()

        sys.exit(0)

    def run(self):
        """Main program loop"""
        # Set up signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

        try:
            # Close the port if it was already open
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.close()
                time.sleep(0.1)  # Allow time for closing

            # Initialize UART with hardware flow control
            self.serial_port = serial.Serial(
                port="/dev/ttyAMA1",  # Primary UART on RPI4
                baudrate=921600,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.1,
                rtscts=True,  # Enable hardware flow control
                dsrdtr=False,
            )

            # Clear buffers
            self.serial_port.reset_input_buffer()
            self.serial_port.reset_output_buffer()
            self.rx_buffer.clear()
            self.header_buffer.clear()
            self.searching_preamble = True
            time.sleep(0.1)  # Allow time for buffer clearing

            print("RPI4 UART Stress Test Starting...")
            print(f"UART Port: {self.serial_port.port}")
            print(f"Baudrate: {self.serial_port.baudrate}")
            print("Hardware flow control: ENABLED")
            print("Starting stress test...")
            print()

            self.running = True

            # Start the receive thread
            rx_thread = threading.Thread(target=self.receive_thread, daemon=True)
            rx_thread.start()

            # Main sending loop
            last_tx = time.time()
            packet_counter = 0

            while self.running:
                now = time.time()
                # Send a packet no more than once every 10ms (100 packets/sec)
                if now - last_tx >= 0.01:  # 10ms
                    # Check the transmit buffer
                    if self.serial_port.out_waiting < 128:  # Space for a packet
                        # Generate a random packet type
                        packet = generate_random_packet()
                        if self.send_packet(packet):
                            last_tx = now
                            packet_counter += 1

                # Print statistics every 1000 packets
                if packet_counter % 1000 == 0:
                    self.print_statistics()

                # Small delay for stability
                time.sleep(0.001)  # 1ms

        except Exception as e:
            print(f"ERROR: {e}")
        finally:
            self.running = False
            if self.serial_port and self.serial_port.is_open:
                # Clear buffers before closing
                self.serial_port.reset_input_buffer()
                self.serial_port.reset_output_buffer()
                time.sleep(0.1)  # Allow time for clearing
                self.serial_port.close()


if __name__ == "__main__":
    test = UARTStressTest()
    test.run()
