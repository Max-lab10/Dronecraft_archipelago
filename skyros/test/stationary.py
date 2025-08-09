from skyros.drone import Drone

import logging
import sys
import math
import time
from skyros.drone import Drone
from skyros.collision_avoidance import CollisionAvoidance, ForceCollisionAvoidance
from skyros.drone_data import DronePosition

# Create logger for this file
logger = logging.getLogger(__name__)

def calculate_distance(pos1, pos2):
    """Calculate distance between two positions"""
    # Handle pos1 (DronePosition object)
    if hasattr(pos1, 'x'):
        x1, y1 = pos1.x, pos1.y
    else:
        x1, y1 = pos1['x'], pos1['y']
    
    # Handle pos2 (dictionary)
    if hasattr(pos2, 'x'):
        x2, y2 = pos2.x, pos2.y
    else:
        x2, y2 = pos2['x'], pos2['y']
    
    dx = x1 - x2
    dy = y1 - y2
    return math.sqrt(dx*dx + dy*dy)

def print_drone_distances(drone):
    """Print distances between this drone and all other discovered drones"""
    my_telemetry = drone.get_telemetry()
    network_status = drone.get_network_status()
    drone_details = network_status['drone_details']

    # Convert drone_details to the format expected by get_avoidance_vector
    other_drones = {}
    for drone_id, details in drone_details.items():
        pos_dict = details['position']
        position = DronePosition(
            x=pos_dict['x'],
            y=pos_dict['y'],
            z=pos_dict['z'],
            vx=pos_dict['vx'],
            vy=pos_dict['vy'],
            vz=pos_dict['vz']
        )
        # Create a simple object with position attribute for compatibility
        drone_info = type('DroneInfo', (), {'position': position})()
        other_drones[drone_id] = drone_info

    target_pos = DronePosition(x=0, y=0, z=0)
    avoidance = ForceCollisionAvoidance()
    vx, vy, vz = avoidance.get_avoidance_vector(
        my_telemetry,
        target_pos,
        other_drones,
        dt=1/10,
    )
    
    if not my_telemetry:
        logger.warning("No telemetry available for this drone")
        return
    
    
    if not other_drones:
        logger.info("No other drones discovered")
        return
    
    logger.info(f"=== Distances from {drone.name} ===")
    logger.info(f"My position: x={my_telemetry.x:.2f}, y={my_telemetry.y:.2f}, z={my_telemetry.z:.2f}")
    logger.info(f"Avoidance vector: vx={vx:.2f}, vy={vy:.2f}, vz={vz:.2f}")
    
    for drone_id, drone_info in other_drones.items():
        other_pos = drone_info.position
        distance = calculate_distance(my_telemetry, other_pos)
        logger.info(f"Distance to drone {drone_id}: {distance:.2f}m")
        logger.info(f"Other drone position: x={other_pos.x:.2f}, y={other_pos.y:.2f}, z={other_pos.z:.2f}")


def setup_logger(verbose=False, quiet=False):
    """Set up simple CLI logger"""
    level = logging.DEBUG if verbose else (logging.WARNING if quiet else logging.INFO)
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        stream=sys.stdout
    )
    
    return logging.getLogger()


def get_logger(name):
    """Get a logger with the given name"""
    return logging.getLogger(name)

# Create and start drone
setup_logger()
with Drone(uart_port="/dev/ttyAMA1") as drone:
    # Set up custom message handler
    def handle_message(msg):
        logger.info(f"Received: {msg}")

    drone.set_custom_message_callback(handle_message)
    drone.broadcast_custom_message("Hello from drone_1!")

    if drone.wait_for_drones(n=1, timeout=30.0):
        status = drone.get_network_status()
        logger.info(f"Telemetry-discovered drones: {status['telemetry_discovered_count']}")
        logger.info(f"Total discovered drones: {status['discovered_drones']}")
    else:
        logger.warning("Timeout waiting for drones, proceeding anyway...")

    # Broadcast message to other drones
    drone.broadcast_custom_message("Hello from drone_1!")

    while True:
      time.sleep(1)
      print_drone_distances(drone)
    drone.wait(100)
