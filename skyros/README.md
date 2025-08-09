# Skyros - ESP-NOW Swarm Drone Communication Library

A Python library for drone swarm communication and coordination using ESP-NOW protocol. This library provides high-level APIs for drone control, collision avoidance, and real-time communication between multiple drones.

## Table of Contents

- [File Structure](#file-structure)
- [Quick Start](#quick-start)
- [API Reference](#api-reference)
- [Important Notes](#important-notes)
- [Deployment](#deployment)

## File Structure

```
skyros/
├── src/skyros/                    # Main library source
│   ├── drone.py                   # Main Drone class (most important)
│   ├── link.py                    # ESP32 communication layer
│   ├── drone_data.py              # Data structures and enums
│   └── collision_avoidance/       # Collision avoidance algorithms
│       ├── abstract_avoidance.py  # Abstract base class
│       └── force_avoidance.py     # Force-based avoidance implementation
├── examples/                      # Usage examples
│   ├── example.py                 # Basic usage example
│   ├── complex_example.py         # Advanced swarm coordination
│   └── example_stress_usage.py    # Stress testing (debugging only)
├── test/                          # Test files
│   ├── stationary.py              # Stationary testing
│   ├── stress.py                  # Network stress testing
│   └── network_performance_test.py # Performance benchmarks
└── pyproject.toml                 # Package configuration
```

### Key Files

- **`drone.py`** - The main `Drone` class that provides the primary API for swarm communication and control
- **`link.py`** - Low-level ESP32 communication interface
- **`drone_data.py`** - Data structures for drone positions and discovery information
- **`collision_avoidance/`** - Collision avoidance algorithms for safe swarm flight

## Quick Start

### 1. Installation

Install the library in development mode:

```bash
cd skyros/
pip install -e .
```

### 2. Basic Usage

Create a simple drone swarm script:

```python
import logging
from skyros.drone import Drone

# Set up logging
logging.basicConfig(level=logging.INFO)

# Create and start drone
with Drone(network_id=0x12, wifi_channel=6) as drone:
    # Wait for other drones to be discovered
    if drone.wait_for_drones(n=1, timeout=30.0):
        print("Other drones discovered!")
        
        # Take off
        drone.takeoff(z=1.0)
        drone.wait(5)
        
        # Navigate with collision avoidance
        drone.navigate_with_avoidance(x=2.0, y=0.0, z=1.0)
        
        # Land
        drone.land()
```

### 3. Configuration Parameters

**Critical Parameters for Swarm Communication:**

- **`network_id`** (default: 0x12) - Must be the same for all drones in the swarm
- **`wifi_channel`** (default: 1) - Must be the same for all drones in the swarm
- **`drone_id`** - Auto-assigned from IP address, or manually set

**Example with custom configuration:**
```python
drone = Drone(
    network_id=0x12,      # Same for all drones in swarm
    wifi_channel=6,        # Same for all drones in swarm  
    drone_id=1,           # Optional: manual drone ID
    uart_port="/dev/ttyAMA1",  # UART port for ESP32
    telemetry_rate=20.0   # Telemetry broadcast rate
)
```

### 4. Important Requirements

**For `wait_for_drones()` and collision avoidance to work:**

1. **ArUco Markers**: Drones must see at least one ArUco marker to have valid coordinates
2. **Network Configuration**: All drones in swarm must use the same `network_id` and `wifi_channel`

**Without ArUco markers:**
- Drones won't have valid position coordinates
- `wait_for_drones()` will timeout
- Collision avoidance won't work properly
- Telemetry packets won't contain meaningful position data

## API Reference
> **Note:** For the latest API details, see `drone.py`

### Main Drone Class

#### Initialization
```python
Drone(
    drone_id: Optional[int] = None,      # Auto-assigned from IP if None
    name: Optional[str] = None,           # Auto-generated if None
    uart_port: str = "/dev/ttyAMA1",     # ESP32 UART port
    baudrate: int = 921600,              # UART baud rate
    network_id: int = 0x12,              # Must match all drones in swarm
    wifi_channel: int = 1,               # Must match all drones in swarm
    tx_power: int = 11,                  # ESP32 transmission power
    telemetry_rate: float = 20.0,        # Telemetry broadcast rate (Hz)
    telemetry_frame: str = "aruco_map"   # ROS frame for telemetry
)
```

#### Core Methods

**Communication Control:**
```python
drone.start() -> bool                    # Start communication
drone.stop()                             # Stop communication
drone.wait(duration: float)              # Wait for specified seconds
```

**Drone Discovery:**
```python
drone.wait_for_drones(n: int, timeout: float = 60.0) -> bool
drone.get_discovered_drones() -> set     # Get discovered drone IDs
drone.get_network_status() -> Dict       # Get detailed network status
```

**Flight Control:**
```python
drone.takeoff(z: float = 1.5, delay: float = 4.0)
drone.land(z: float = 0.5, delay: float = 4.0, frame_id: str = "aruco_map")
drone.navigate_wait(x, y, z, yaw, speed, frame_id, auto_arm, tolerance)
drone.navigate_with_avoidance(x, y, z, yaw, frame_id, timeout, perpetual, avoidance_class)
```

**Custom Messaging:**
```python
drone.broadcast_custom_message(message: str) -> bool
drone.set_custom_message_callback(callback: Callable[[str], None])
```

**Telemetry:**
```python
drone.get_telemetry(frame_id: str = "aruco_map") -> Optional[DronePosition]
```

#### Context Manager Usage
```python
with Drone(network_id=0x12, wifi_channel=6) as drone:
    # Drone automatically starts and stops
    drone.wait_for_drones(n=1)
    drone.takeoff()
    # ... your code ...
    drone.land()
```

### Data Structures

#### DronePosition
```python
@dataclass
class DronePosition:
    x: float = 0.0          # X coordinate
    y: float = 0.0          # Y coordinate  
    z: float = 0.0          # Z coordinate
    vx: float = 0.0         # X velocity
    vy: float = 0.0         # Y velocity
    vz: float = 0.0         # Z velocity
    yaw: float = 0.0        # Yaw angle
    yaw_rate: float = 0.0   # Yaw rate
    frame_id: str = "aruco_map"  # Coordinate frame
```

#### DroneInfo
```python
@dataclass  
class DroneInfo:
    drone_id: int                    # Drone identifier
    position: DronePosition          # Current position
    last_seen: float                 # Timestamp of last telemetry
    discovered_via: DroneDiscoveryMethod  # How drone was discovered
```

### Collision Avoidance

The library includes collision avoidance algorithms:

```python
from skyros.collision_avoidance import ForceCollisionAvoidance

# Use force-based collision avoidance
drone.navigate_with_avoidance(
    x=2.0, y=0.0, z=1.0,
    avoidance_class=ForceCollisionAvoidance
)
```

## Important Notes

### Network Configuration
- **All drones in swarm must use the same `network_id` and `wifi_channel`**
- **Different networks won't communicate with each other**
- **Channel range: 1-13 (WiFi channels)**

### ArUco Marker Requirements
- **Drones must see ArUco markers for valid coordinates**
- **Without markers: `wait_for_drones()` will timeout**
- **Without markers: collision avoidance won't work**
- **Ensure ROS provides "aruco_map" frame**

### Telemetry and Discovery
- **Telemetry packets contain position data from ArUco markers**
- **Drones are discovered via telemetry packets**
- **Status packets provide basic connectivity info**
- **Drones expire after 5 seconds without telemetry (configurable)**

### Custom Messages
- **Broadcast to all drones in the network**
- **Use JSON format for structured communication**
- **Set callback to handle incoming messages**
- **Message size is limited to 125 characters**

### Error Handling
- **Check return values from `start()` and `wait_for_drones()`**
- **Monitor network status with `get_network_status()`**
- **Use try/except for robust error handling**

## Deployment

For deploying this library to multiple drones simultaneously, see the [Ansible Deployment Guide](ansible_deployment.md) in this directory.
