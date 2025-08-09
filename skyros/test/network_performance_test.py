#!/usr/bin/env python3
"""
Per-Drone Network Performance Test
Tracks statistics for each drone separately using UART packets
"""

import logging
import sys
import time
import threading
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque, defaultdict

from skyros.drone import Drone
from skyros.lib.packets import TelemetryPacket, StatusPacket, PacketType


@dataclass
class DroneStats:
    """Statistics for a single drone"""
    drone_id: int
    packets_sent: deque = field(default_factory=lambda: deque(maxlen=5))
    packets_received: deque = field(default_factory=lambda: deque(maxlen=5))
    bytes_sent: deque = field(default_factory=lambda: deque(maxlen=5))
    bytes_received: deque = field(default_factory=lambda: deque(maxlen=5))
    last_seen: float = 0.0
    
    def update(self, packets_sent: int, packets_received: int, bytes_sent: int, bytes_received: int):
        """Update rolling statistics"""
        self.packets_sent.append(packets_sent)
        self.packets_received.append(packets_received)
        self.bytes_sent.append(bytes_sent)
        self.bytes_received.append(bytes_received)
        self.last_seen = time.time()
    
    def get_average_rates(self) -> Dict[str, float]:
        """Calculate average rates over 5-second window"""
        if len(self.packets_sent) < 2:
            return {
                'tx_rate': 0.0,
                'rx_rate': 0.0,
                'bytes_tx_rate': 0.0,
                'bytes_rx_rate': 0.0
            }
        
        # Calculate rate of change over the window
        tx_rate = (self.packets_sent[-1] - self.packets_sent[0]) / 5.0
        rx_rate = (self.packets_received[-1] - self.packets_received[0]) / 5.0
        bytes_tx_rate = (self.bytes_sent[-1] - self.bytes_sent[0]) / 5.0
        bytes_rx_rate = (self.bytes_received[-1] - self.bytes_received[0]) / 5.0
        
        return {
            'tx_rate': tx_rate,
            'rx_rate': rx_rate,
            'bytes_tx_rate': bytes_tx_rate,
            'bytes_rx_rate': bytes_rx_rate
        }


class PerDroneNetworkTest:
    """Network performance test tracking statistics per drone"""
    
    def __init__(self, drone_id: Optional[int] = None):
        self.drone_id = drone_id
        self.drone: Optional[Drone] = None
        self.running = False
        self.message_counter = 0
        
        # Per-drone statistics - track actual packet counts for each drone
        self.drone_stats: Dict[int, DroneStats] = {}
        
        # Track packet counts for each drone
        self.drone_packet_counts: Dict[int, Dict[str, int]] = defaultdict(lambda: {
            'packets_sent': 0,
            'packets_received': 0,
            'bytes_sent': 0,
            'bytes_received': 0
        })
        
        # Setup logging
        self.logger = logging.getLogger("PerDroneNetworkTest")
        
    def setup_logger(self, verbose: bool = False):
        """Setup logging configuration"""
        level = logging.DEBUG if verbose else logging.INFO
        logging.basicConfig(
            level=level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            stream=sys.stdout
        )
    
    def custom_message_handler(self, message: str):
        """Handle received custom messages"""
        try:
            if message.startswith("TEST_MSG:"):
                parts = message.split(":")
                if len(parts) >= 2:
                    counter = int(parts[1])
                    self.logger.debug(f"Received test message: {counter}")
        except Exception as e:
            self.logger.error(f"Error processing message: {e}")
    
    def telemetry_packet_handler(self, packet: TelemetryPacket):
        """Handle telemetry packets to track per-drone statistics"""
        try:
            drone_id = packet.drone_id
            
            # Initialize drone stats if not exists
            if drone_id not in self.drone_stats:
                self.drone_stats[drone_id] = DroneStats(drone_id)
                self.drone_packet_counts[drone_id] = {
                    'packets_sent': 0,
                    'packets_received': 0,
                    'bytes_sent': 0,
                    'bytes_received': 0
                }
            
            # Update packet counts for this drone
            self.drone_packet_counts[drone_id]['packets_received'] += 1
            self.drone_packet_counts[drone_id]['bytes_received'] += 25  # Telemetry packet size
            
            self.logger.debug(f"Received telemetry from drone {drone_id}: x={packet.x:.2f}, y={packet.y:.2f}, z={packet.z:.2f}")
            
        except Exception as e:
            self.logger.error(f"Error handling telemetry packet: {e}")
    
    def status_packet_handler(self, packet: StatusPacket):
        """Handle status packets to track per-drone statistics"""
        try:
            drone_id = packet.drone_id
            
            # Initialize drone stats if not exists
            if drone_id not in self.drone_stats:
                self.drone_stats[drone_id] = DroneStats(drone_id)
                self.drone_packet_counts[drone_id] = {
                    'packets_sent': 0,
                    'packets_received': 0,
                    'bytes_sent': 0,
                    'bytes_received': 0
                }
            
            # Update packet counts for this drone
            self.drone_packet_counts[drone_id]['packets_received'] += 1
            self.drone_packet_counts[drone_id]['bytes_received'] += 8  # Status packet size
            
            self.logger.debug(f"Received status from drone {drone_id}: status={packet.status_code}, battery={packet.battery_mv}mV")
            
        except Exception as e:
            self.logger.error(f"Error handling status packet: {e}")
    
    def send_test_messages(self):
        """Send test messages with counter"""
        while self.running:
            try:
                self.message_counter += 1
                message = f"TEST_MSG:{self.message_counter}"
                
                if self.drone.broadcast_custom_message(message):
                    # Update packet counts for our own drone
                    if self.drone_id is not None:
                        if self.drone_id not in self.drone_packet_counts:
                            self.drone_packet_counts[self.drone_id] = {
                                'packets_sent': 0,
                                'packets_received': 0,
                                'bytes_sent': 0,
                                'bytes_received': 0
                            }
                        self.drone_packet_counts[self.drone_id]['packets_sent'] += 1
                        self.drone_packet_counts[self.drone_id]['bytes_sent'] += len(message.encode('utf-8'))
                    
                    self.logger.debug(f"Sent test message: {self.message_counter}")
                else:
                    self.logger.warning(f"Failed to send message: {self.message_counter}")
                
                time.sleep(1.0)  # Send one message per second
                
            except Exception as e:
                self.logger.error(f"Error sending message: {e}")
                break
    
    def stats_monitor_thread(self):
        """Monitor statistics and calculate per-drone averages"""
        while self.running:
            try:
                # Update rolling stats for each drone based on actual packet counts
                for drone_id, packet_counts in self.drone_packet_counts.items():
                    if drone_id not in self.drone_stats:
                        self.drone_stats[drone_id] = DroneStats(drone_id)
                    
                    drone_stat = self.drone_stats[drone_id]
                    drone_stat.update(
                        packets_sent=packet_counts['packets_sent'],
                        packets_received=packet_counts['packets_received'],
                        bytes_sent=packet_counts['bytes_sent'],
                        bytes_received=packet_counts['bytes_received']
                    )
                
                # Print per-drone statistics every 5 seconds
                if self.drone_stats and len(list(self.drone_stats.values())[0].packets_sent) >= 2:
                    self.logger.info("=== PER-DRONE STATISTICS ===")
                    for drone_id, drone_stat in self.drone_stats.items():
                        rates = drone_stat.get_average_rates()
                        self.logger.info(
                            f"Drone {drone_id}: "
                            f"TX: {rates['tx_rate']:.1f} pps, "
                            f"RX: {rates['rx_rate']:.1f} pps, "
                            f"Bytes TX: {rates['bytes_tx_rate']:.1f} B/s, "
                            f"Bytes RX: {rates['bytes_rx_rate']:.1f} B/s"
                        )
                    
                    # Print global statistics
                    global_tx_rate = sum(d.get_average_rates()['tx_rate'] for d in self.drone_stats.values())
                    global_rx_rate = sum(d.get_average_rates()['rx_rate'] for d in self.drone_stats.values())
                    self.logger.info(
                        f"GLOBAL: TX: {global_tx_rate:.1f} pps, RX: {global_rx_rate:.1f} pps"
                    )
                    self.logger.info("=" * 40)
                
                time.sleep(1.0)  # Update every second
                
            except Exception as e:
                self.logger.error(f"Error in stats monitor: {e}")
    
    def run_test(self, uart_port: str = "/dev/ttyAMA1", verbose: bool = False):
        """Run the per-drone network test"""
        self.setup_logger(verbose)
        self.logger.info("Starting per-drone network performance test")
        
        try:
            # Initialize drone
            self.drone = Drone(
                drone_id=self.drone_id,
                uart_port=uart_port,
                telemetry_rate=5.0
            )
            
            # Set custom message callback
            self.drone.set_custom_message_callback(self.custom_message_handler)
            
            # Set packet callbacks for per-drone tracking
            self.drone.link.set_packet_callback(PacketType.TELEMETRY, self.telemetry_packet_handler)
            self.drone.link.set_packet_callback(PacketType.STATUS, self.status_packet_handler)
            
            # Start drone
            if not self.drone.start():
                self.logger.error("Failed to start drone")
                return
            
            self.logger.info("Drone started successfully")
            
            # Start test
            self.running = True
            
            # Start message sending thread
            send_thread = threading.Thread(target=self.send_test_messages)
            send_thread.daemon = True
            send_thread.start()
            
            # Start statistics monitoring thread
            stats_thread = threading.Thread(target=self.stats_monitor_thread)
            stats_thread.daemon = True
            stats_thread.start()
            
            # Keep running until interrupted
            try:
                while self.running:
                    time.sleep(1.0)
            except KeyboardInterrupt:
                self.logger.info("Test interrupted by user")
            
            # Stop test
            self.running = False
            
            # Wait for threads to finish
            send_thread.join(timeout=5.0)
            stats_thread.join(timeout=5.0)
            
            # Stop drone
            self.drone.stop()
            
        except Exception as e:
            self.logger.error(f"Test failed: {e}")
            if self.drone:
                self.drone.stop()


def main():
    """Main function to run the per-drone network test"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Per-Drone Network Performance Test")
    parser.add_argument("--drone-id", type=int, help="Drone ID to use")
    parser.add_argument("--uart-port", default="/dev/ttyAMA1", help="UART port to use")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Create and run test
    test = PerDroneNetworkTest(drone_id=args.drone_id)
    test.run_test(uart_port=args.uart_port, verbose=args.verbose)


if __name__ == "__main__":
    main() 