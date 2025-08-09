from dataclasses import dataclass
from enum import Enum


@dataclass
class DronePosition:
    """Drone position and velocity data"""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0
    yaw: float = 0.0
    yaw_rate: float = 0.0
    frame_id: str = "aruco_map"


@dataclass
class DroneDiscoveryMethod(str, Enum):
    TELEMETRY = "telemetry"
    STATUS = "status"


@dataclass
class DroneInfo:
    """Complete drone information including position and discovery data"""

    drone_id: int
    position: DronePosition
    last_seen: float
    discovered_via: DroneDiscoveryMethod = DroneDiscoveryMethod.TELEMETRY
