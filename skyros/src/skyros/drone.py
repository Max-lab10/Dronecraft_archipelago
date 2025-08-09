#!/usr/bin/env python3
"""
High-level Drone Interface for ESP-NOW Swarm Network
Provides user-friendly API for drone control and communication
"""

import logging
import math
import threading
import time
from typing import Any, Callable, Dict, Optional, Type

try:
    import rospy
    from clover.srv import GetTelemetry, Navigate, SetPosition
    from std_srvs.srv import Trigger

    ROS_AVAILABLE = True
except ImportError:
    rospy = None
    ROS_AVAILABLE = False

from skyros.collision_avoidance import CollisionAvoidance, ForceCollisionAvoidance
from skyros.drone_data import DroneDiscoveryMethod, DroneInfo, DronePosition
from skyros.lib.packets import StatusPacket, TelemetryPacket
from skyros.lib.network_utils import get_local_ip_id
from skyros.link import ESP32Link


class Drone:
    """High-level drone interface with ESP-NOW communication and collision avoidance"""

    def __init__(
        self,
        drone_id: Optional[int] = None,
        name: Optional[str] = None,
        uart_port: str = "/dev/ttyAMA1",
        baudrate: int = 921600,
        network_id: int = 0x12,
        wifi_channel: int = 1,
        tx_power: int = 11,
        telemetry_rate: float = 20.0,
        telemetry_frame: str = "aruco_map",
    ):
        # Basic configuration
        self.drone_id = drone_id or get_local_ip_id()
        # Log the drone ID for debugging
        if drone_id is None:
            logging.info(f"Auto-assigned drone ID: {self.drone_id} (from local IP)")
        else:
            logging.info(f"Using provided drone ID: {self.drone_id}")

        self.name = name or f"drone_{self.drone_id}"
        self.telemetry_rate = telemetry_rate
        self.telemetry_frame = telemetry_frame

        # ESP32 communication link
        self.link = ESP32Link(port=uart_port, baudrate=baudrate, network_id=network_id, wifi_channel=wifi_channel, tx_power=tx_power)

        # ROS services (if available)
        self._ros_services = {}
        if ROS_AVAILABLE and rospy is not None:
            try:
                self._ros_services["get_telemetry"] = rospy.ServiceProxy(
                    "get_telemetry", GetTelemetry
                )
                self._ros_services["navigate"] = rospy.ServiceProxy("navigate", Navigate)
                self._ros_services["set_position"] = rospy.ServiceProxy("set_position", SetPosition)
                self._ros_services["autoland"] = rospy.ServiceProxy("land", Trigger)
            except Exception as e:
                logging.warning(f"Failed to initialize ROS services: {e}")

        # State management
        self.running = False
        self._telemetry_lock = threading.Lock()
        self._telemetry_timer: Optional[threading.Timer] = None
        self._cleanup_timer: Optional[threading.Timer] = None

        # Drone network state - single consolidated structure
        self._other_drones: Dict[int, DroneInfo] = {}  # drone_id -> DroneInfo
        self._other_drones_lock = threading.Lock()
        self._drone_expiry_timeout = 5.0  # seconds - drone expires if not seen for this long

        # Custom message callback
        self._custom_message_callback: Optional[Callable[[str], None]] = None

        # Logger
        self.logger = logging.getLogger(self.name)

        # Set up packet callbacks
        self.link.set_packet_callback(1, self._handle_telemetry_packet)  # TELEMETRY
        self.link.set_packet_callback(3, self._handle_status_packet)  # STATUS
        self.link.set_custom_message_callback(self._handle_custom_message)

    def start(self) -> bool:
        """Start the drone communication system"""
        if not self.link.start():
            self.logger.error("Failed to start ESP32 link")
            return False

        self.running = True

        # Start telemetry broadcasting
        self._start_telemetry_timer()

        # Start drone discovery cleanup
        self._start_cleanup_timer()

        self.logger.info(f"Drone {self.name} started successfully")
        return True

    def stop(self):
        """Stop the drone communication system"""
        self.running = False

        if self._telemetry_timer:
            self._telemetry_timer.cancel()

        if self._cleanup_timer:
            self._cleanup_timer.cancel()

        self.link.stop()
        self.link.disconnect()

        self.logger.info(f"Drone {self.name} stopped")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def _start_telemetry_timer(self):
        """Start periodic telemetry broadcasting"""
        if not self.running:
            return

        try:
            self._broadcast_telemetry()
        except Exception as e:
            self.logger.error(f"Telemetry broadcast failed: {e}")

        # Schedule next broadcast
        if self.running:
            self._telemetry_timer = threading.Timer(
                1.0 / self.telemetry_rate, self._start_telemetry_timer
            )
            self._telemetry_timer.start()

    def _resolve_ros_service(self, names, service_type, timeout: float = 5.0):
        """Resolve and wait for a ROS service by trying a list of possible names.

        Returns a rospy.ServiceProxy if successful, otherwise raises RuntimeError.
        """
        if not (ROS_AVAILABLE and rospy is not None):
            raise RuntimeError("ROS is not available")

        # Normalize names to list
        candidate_names = names if isinstance(names, (list, tuple)) else [names]

        last_err = None
        for service_name in candidate_names:
            try:
                rospy.wait_for_service(service_name, timeout=timeout)
                self.logger.info(f"Using service: {service_name}")
                return rospy.ServiceProxy(service_name, service_type)
            except Exception as e:
                last_err = e
                continue

        raise RuntimeError(f"Service not available for any of names {candidate_names}: {last_err}")

    def _call_service_with_retries(self, proxy, attempts: int = 3, delay: float = 0.5, **kwargs):
        """Call a ROS service with retries to mitigate transient transport errors."""
        last_exc = None
        for attempt in range(1, attempts + 1):
            try:
                return proxy(**kwargs)
            except Exception as exc:
                last_exc = exc
                if attempt < attempts:
                    self.logger.debug(
                        f"Service call failed (attempt {attempt}/{attempts}), retrying in {delay}s: {exc}"
                    )
                    time.sleep(delay)
                else:
                    break
        raise last_exc

    def _start_cleanup_timer(self):
        """Start periodic cleanup of expired drones"""
        if not self.running:
            return

        try:
            self._cleanup_expired_drones()
        except Exception as e:
            self.logger.error(f"Drone cleanup failed: {e}")

        # Schedule next cleanup (every 2 seconds)
        if self.running:
            self._cleanup_timer = threading.Timer(2.0, self._start_cleanup_timer)
            self._cleanup_timer.start()

    def _cleanup_expired_drones(self):
        """Remove drones that haven't been seen recently"""
        current_time = time.time()
        expired_drones = []

        with self._other_drones_lock:
            for drone_id, drone_info in list(self._other_drones.items()):
                if current_time - drone_info.last_seen > self._drone_expiry_timeout:
                    expired_drones.append(drone_id)

            # Remove expired drones
            for drone_id in expired_drones:
                if drone_id in self._other_drones:
                    del self._other_drones[drone_id]
                    self.logger.info(
                        f"Drone_{drone_id} expired (not seen for {self._drone_expiry_timeout}s)"
                    )

    def _broadcast_telemetry(self):
        """Broadcast current telemetry to other drones"""
        if not ROS_AVAILABLE or "get_telemetry" not in self._ros_services:
            return

        try:
            with self._telemetry_lock:
                telem = self._ros_services["get_telemetry"](frame_id=self.telemetry_frame)

            # Check for NaN values
            if any(math.isnan(val) for val in [telem.x, telem.y, telem.vx, telem.vy]):
                return

            # Send telemetry via ESP-NOW
            self.link.send_telemetry(self.drone_id, telem.x, telem.y, telem.z, telem.vx, telem.vy, telem.vz)

        except Exception as e:
            self.logger.debug(f"Failed to broadcast telemetry: {e}")

    def _handle_telemetry_packet(self, packet: TelemetryPacket):
        """Handle received telemetry from other drones - PRIMARY discovery mechanism"""
        try:
            if packet.drone_id != self.drone_id:  # Don't track ourselves
                with self._other_drones_lock:
                    current_time = time.time()
                    was_new = packet.drone_id not in self._other_drones

                    # Create position from telemetry data
                    position = DronePosition(x=packet.x, y=packet.y, z=packet.z, vx=packet.vx, vy=packet.vy, vz=packet.vz)

                    # Always update/create drone info from telemetry (most important data)
                    self._other_drones[packet.drone_id] = DroneInfo(
                        drone_id=packet.drone_id,
                        position=position,
                        last_seen=current_time,
                        discovered_via=DroneDiscoveryMethod.TELEMETRY,
                    )

                    if was_new:
                        self.logger.info(
                            f"Discovered drone_{packet.drone_id} via telemetry at ({packet.x:.1f}, {packet.y:.1f}, {packet.z:.1f})"
                        )
                    else:
                        self.logger.debug(
                            f"Updated drone_{packet.drone_id} position: ({packet.x:.1f}, {packet.y:.1f}, {packet.z:.1f})"
                        )
        except Exception as e:
            self.logger.error(f"Error handling telemetry packet: {e}")

    def _handle_status_packet(self, packet: StatusPacket):
        """Handle received status packets - only update timestamp if drone already discovered via telemetry"""
        if packet.drone_id != self.drone_id:  # Don't track ourselves
            with self._other_drones_lock:
                current_time = time.time()

                # Only update timestamp if drone was already discovered via telemetry
                # Status packets alone don't provide position data, so we don't create new entries
                if packet.drone_id in self._other_drones:
                    self._other_drones[packet.drone_id].last_seen = current_time
                    self.logger.debug(f"Updated timestamp for drone_{packet.drone_id} via status")

        if packet.status_code == 4 or packet.error_flags != 0 or packet.battery_mv < 3400:
            self.logger.warning(
                f"Critical drone status - drone_{packet.drone_id}, "
                f"Status={packet.status_code}, Battery={packet.battery_mv}mV, "
                f"Errors=0x{packet.error_flags:04X}"
            )

    def _handle_custom_message(self, message: str):
        """Handle received custom messages"""
        if self._custom_message_callback:
            try:
                self._custom_message_callback(message)
            except Exception as e:
                self.logger.error(f"Error in custom message callback: {e}")

    def get_telemetry(self, frame_id: str = "aruco_map") -> Optional[DronePosition]:
        """Get current drone telemetry"""
        if not ROS_AVAILABLE or "get_telemetry" not in self._ros_services:
            return None

        try:
            with self._telemetry_lock:
                telem = self._ros_services["get_telemetry"](frame_id=frame_id)

            return DronePosition(
                x=telem.x,
                y=telem.y,
                z=telem.z,
                vx=telem.vx,
                vy=telem.vy,
                vz=telem.vz,
                yaw=telem.yaw,
                yaw_rate=telem.yaw_rate,
                frame_id=telem.frame_id,
            )
        except Exception as e:
            self.logger.error(f"Failed to get telemetry: {e}")
            return None

    def broadcast_custom_message(self, message: str) -> bool:
        """Broadcast a custom message to other drones (max 125 characters).
        Note: This method does not guarantee message delivery."""
        if len(message) > 125:
            self.logger.warning(f"Message too long ({len(message)} chars), truncating to 125")
            message = message[:125]

        success = self.link.send_custom_message(message)
        if success:
            self.logger.info(f"Broadcast message: {message}")
        else:
            self.logger.error("Failed to broadcast custom message")

        return success

    def set_custom_message_callback(self, callback: Callable[[str], None]):
        """Set callback function for received custom messages"""
        self._custom_message_callback = callback
        self.logger.info("Custom message callback set")

    def navigate_with_avoidance(
        self,
        x: float = 0.0,
        y: float = 0.0,
        z: float = 0.0,
        yaw: float = float("nan"),
        frame_id: str = "",
        timeout: float = 60.0,
        perpetual: bool = False,
        avoidance_class: Type[CollisionAvoidance] = ForceCollisionAvoidance,
    ):
        """Navigate to target position while avoiding other drones"""

        if not ROS_AVAILABLE:
            self.logger.error("ROS services not available for navigation")
            return False

        self.logger.info(
            f"Navigating to x={x:.2f} y={y:.2f} z={z:.2f} in {frame_id} with collision avoidance"
        )

        if not frame_id:
            frame_id = self.telemetry_frame

        rate_hz = 10
        target_dt = 1.0 / rate_hz
        time_start = time.time()
        target_pos = DronePosition(x=x, y=y, z=z, yaw=yaw, frame_id=frame_id)
        avoidance = avoidance_class()

        try:
            # Resolve required services (namespaced or not)
            telemetry_proxy = self._resolve_ros_service(
                ["get_telemetry", "/get_telemetry", "/clover/get_telemetry"], GetTelemetry
            )
            set_position_proxy = self._resolve_ros_service(
                ["set_position", "/set_position", "/clover/set_position"], SetPosition
            )

            while self.running:
                try:
                    with self._telemetry_lock:
                        telem = telemetry_proxy(frame_id=frame_id)
                    current_pos = DronePosition(
                        x=telem.x,
                        y=telem.y,
                        z=getattr(telem, "z", float("nan")),
                        vx=telem.vx,
                        vy=telem.vy,
                        vz=getattr(telem, "vz", float("nan")),
                        yaw=getattr(telem, "yaw", float("nan")),
                        yaw_rate=getattr(telem, "yaw_rate", float("nan")),
                        frame_id=telem.frame_id,
                    )
                except Exception:
                    time.sleep(target_dt)
                    continue
                if current_pos is None:
                    time.sleep(target_dt)
                    continue

                # Check for NaN values
                if any(
                    math.isnan(val)
                    for val in [current_pos.x, current_pos.y, current_pos.vx, current_pos.vy]
                ):
                    time.sleep(target_dt)
                    continue

                with self._other_drones_lock:
                    other_drones = self._other_drones.copy()

                vx, vy, vz = avoidance.get_avoidance_vector(
                    current_pos,
                    target_pos,
                    other_drones,
                    dt=target_dt,
                )

                if not perpetual and vx == 0 and vy == 0 and vz == 0:
                    self.logger.info("Arrived at target")
                    return True

                # Apply avoidance vector to movement
                next_x = current_pos.x + vx * target_dt
                next_y = current_pos.y + vy * target_dt
                next_z = current_pos.z + vz * target_dt

                set_position_proxy(x=next_x, y=next_y, z=next_z, yaw=yaw, frame_id=frame_id)

                time.sleep(target_dt)

                if timeout and time.time() - time_start > timeout:
                    self.logger.info("Navigation timed out")
                    return False

        except Exception as e:
            self.logger.error(f"Navigation with avoidance failed: {e}")
            return False

        return True

    def navigate_wait(
        self,
        x: float = 0.0,
        y: float = 0.0,
        z: float = 0.0,
        yaw: float = float("nan"),
        speed: float = 0.5,
        frame_id: str = "",
        auto_arm: bool = False,
        tolerance: float = 0.2,
    ):
        """Navigate to position and wait for arrival (without collision avoidance)"""

        if not ROS_AVAILABLE:
            self.logger.error("ROS services not available for navigation")
            return False

        if not frame_id:
            frame_id = self.telemetry_frame

        self.logger.info(f"Navigating to x={x:.2f} y={y:.2f} z={z:.2f} in {frame_id}")

        try:
            navigate_proxy = self._resolve_ros_service(
                ["navigate", "/navigate", "/clover/navigate"], Navigate
            )
            telemetry_proxy = self._resolve_ros_service(
                ["get_telemetry", "/get_telemetry", "/clover/get_telemetry"], GetTelemetry
            )

            self._call_service_with_retries(
                navigate_proxy,
                x=x,
                y=y,
                z=z,
                yaw=yaw,
                speed=speed,
                frame_id=frame_id,
                auto_arm=auto_arm,
            )

            while self.running:
                telem = telemetry_proxy(frame_id="navigate_target")
                if math.sqrt(telem.x**2 + telem.y**2 + telem.z**2) < tolerance:
                    time.sleep(0.1)
                    self.logger.info("Arrived at target")
                    return True
                time.sleep(0.1)

        except Exception as e:
            self.logger.error(f"Navigation failed: {e}")
            return False

    def takeoff(self, z: float = 1.5, delay: float = 4.0):
        """Take off to specified height"""
        if not ROS_AVAILABLE:
            self.logger.error("ROS services not available for takeoff")
            return False

        self.logger.info(f"Taking off to z={z:.2f}")

        try:
            navigate_proxy = self._resolve_ros_service(
                ["navigate", "/navigate", "/clover/navigate"], Navigate
            )
            telemetry_proxy = self._resolve_ros_service(
                ["get_telemetry", "/get_telemetry", "/clover/get_telemetry"], GetTelemetry
            )

            self._call_service_with_retries(
                navigate_proxy,
                z=z,
                x=0.0,
                y=0.0,
                yaw=float("nan"),
                speed=0.5,
                frame_id="body",
                auto_arm=True,
            )
            time.sleep(1.0)

            telem = telemetry_proxy(frame_id="body")
            if not telem.armed:
                raise RuntimeError("Arming failed!")

            time.sleep(delay)
            self.logger.info("Takeoff completed")
            return True

        except Exception as e:
            self.logger.error(f"Takeoff failed: {e}")
            return False

    def land(self, z: float = 0.5, delay: float = 4.0, frame_id: str = "aruco_map"):
        """Land the drone"""
        if not ROS_AVAILABLE:
            self.logger.error("ROS services not available for landing")
            return False

        try:
            telemetry_proxy = self._resolve_ros_service(
                ["get_telemetry", "/get_telemetry", "/clover/get_telemetry"], GetTelemetry
            )
            telem = telemetry_proxy(frame_id=frame_id)
            self.logger.info("Pre-landing")

            if self.navigate_wait(x=telem.x, y=telem.y, z=z, frame_id=frame_id):
                time.sleep(1.0)
                self.logger.info("Landing")
                # Resolve and wait for land service, with fallback to common namespace
                land_service_names = ["land", "/land", "/clover/land"]
                land_proxy = None
                if rospy is not None:
                    last_err = None
                    for service_name in land_service_names:
                        try:
                            rospy.wait_for_service(service_name, timeout=5.0)
                            # Prefer already-prepared proxy if it matches the name
                            if service_name == "land" and "autoland" in self._ros_services:
                                land_proxy = self._ros_services["autoland"]
                            else:
                                land_proxy = rospy.ServiceProxy(service_name, Trigger)
                            self.logger.info(f"Using land service: {service_name}")
                            break
                        except Exception as e:
                            last_err = e
                            continue

                    if land_proxy is None:
                        raise RuntimeError(f"Land service not available: {last_err}")

                    self._call_service_with_retries(land_proxy)
                time.sleep(delay)
                self.logger.info("Landed")
                return True
            else:
                self.logger.error("Failed to reach pre-landing position")
                return False

        except Exception as e:
            self.logger.error(f"Landing failed: {e}")
            return False

    def wait(self, duration: float):
        """Wait for specified duration"""
        if ROS_AVAILABLE and rospy is not None:
            rospy.sleep(duration)
            if rospy.is_shutdown():
                raise RuntimeError("ROS shutdown")
        else:
            time.sleep(duration)

    def set_drone_expiry_timeout(self, timeout: float):
        """
        Set the timeout for drone discovery expiration

        Args:
            timeout: Time in seconds after which a drone is considered offline
        """
        self._drone_expiry_timeout = max(1.0, timeout)  # Minimum 1 second
        self.logger.info(f"Drone expiry timeout set to {self._drone_expiry_timeout}s")

    def wait_for_drones(self, n: int, timeout: float = 60.0) -> bool:
        """
        Wait for n other drones to be discovered via telemetry packets

        Telemetry packets are the primary discovery mechanism as they contain
        position and velocity data essential for swarm coordination.

        Args:
            n: Number of other drones to wait for
            timeout: Maximum time to wait in seconds (default: 60.0)

        Returns:
            bool: True if n drones were discovered, False if timeout occurred
        """
        if n <= 0:
            return True

        self.logger.info(f"{self.name} waiting for {n} other drones via telemetry packets...")
        start_time = time.time()

        while len(self._other_drones) < n and self.running:
            time.sleep(0.5)
            elapsed = time.time() - start_time

            if elapsed > timeout:
                self.logger.warning(
                    f"Timeout waiting for drones. Found {len(self._other_drones)}/{n}"
                )
                return False

            # Log progress every 10 seconds
            if int(elapsed) % 10 == 0 and elapsed > 0:
                with self._other_drones_lock:
                    discovered_list = sorted(list(self._other_drones.keys()))
                self.logger.info(
                    f"Still waiting... Found {len(self._other_drones)}/{n} drones: {discovered_list}"
                )

        if len(self._other_drones) >= n:
            with self._other_drones_lock:
                discovered_list = sorted(list(self._other_drones.keys()))
            self.logger.info(f"{self.name} found all required drones: {discovered_list}")
            return True

        return False

    def get_discovered_drones(self) -> set:
        """Get set of discovered drone IDs"""
        with self._other_drones_lock:
            return set(self._other_drones.keys())

    def get_network_status(self) -> Dict[str, Any]:
        """Get network and communication status"""
        with self._other_drones_lock:
            other_drones_count = len(self._other_drones)
            discovered_drones = sorted(list(self._other_drones.keys()))

            # Get detailed drone info
            drone_details = {}
            telemetry_discovered = 0
            for drone_id, drone_info in self._other_drones.items():
                if drone_info.discovered_via == DroneDiscoveryMethod.TELEMETRY:
                    telemetry_discovered += 1

                drone_details[drone_id] = {
                    "last_seen": drone_info.last_seen,
                    "discovered_via": drone_info.discovered_via,
                    "age_seconds": time.time() - drone_info.last_seen,
                    "position": {
                        "x": drone_info.position.x,
                        "y": drone_info.position.y,
                        "z": drone_info.position.z,
                        "vx": drone_info.position.vx,
                        "vy": drone_info.position.vy,
                        "vz": drone_info.position.vz,
                    },
                }

        return {
            "name": self.name,
            "drone_id": self.drone_id,
            "running": self.running,
            "esp32_connected": self.link.is_connected(),
            "other_drones_count": other_drones_count,
            "telemetry_discovered_count": telemetry_discovered,
            "discovered_drones": discovered_drones,
            "drone_details": drone_details,
            "expiry_timeout": self._drone_expiry_timeout,
            "communication_stats": self.link.get_statistics(),
        }
