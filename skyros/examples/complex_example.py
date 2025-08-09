import json
import logging
import sys
from skyros.drone import Drone


def setup_logger(verbose=False, quiet=False):
    """Set up simple CLI logger"""
    level = logging.DEBUG if verbose else (logging.WARNING if quiet else logging.INFO)
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        stream=sys.stdout
    )
    
    return logging.getLogger()

# Create and start drone
setup_logger()

# Variables for slave drone coordinates
slave_target = None

def handle_message(msg):
    global slave_target
    print(f"Received: {msg}")
    
    try:
        data = json.loads(msg)
        if data.get("t") == "fc":  # flight_command
            # Check if this message is for this specific drone
            target_drone_id = data.get("d")
            if target_drone_id == drone.drone_id:
                # Parse coordinates for this drone
                slave_target = {
                    "x": data.get("x", 0),
                    "y": data.get("y", 0),
                    "z": data.get("z", 1)
                }
                logging.info(f"Slave {drone.drone_id} got target: {slave_target}")
    except json.JSONDecodeError:
        logging.warning(f"Failed to parse JSON: {msg}")

# drone_id is set by last octet of ip address
with Drone(network_id=0x12, wifi_channel=6, tx_power=11, uart_port="/dev/ttyAMA1") as drone:
    drone.set_custom_message_callback(handle_message)

    # Send start json message to other drones
    start_message = {
        "status": "start",
        "info": {
            "drone_id": drone.drone_id,
        }
    }
    drone.broadcast_custom_message(json.dumps(start_message))

    # Wait for other drones to start
    if drone.wait_for_drones(n=1, timeout=30.0):
        # Get network status with detailed info
        status = drone.get_network_status()

        # Show detailed drone info
        for drone_id, details in status["drone_details"].items():
            pos = details["position"]
            logging.info(
                f"  drone_{drone_id}: pos=({pos['x']:.1f},{pos['y']:.1f},{pos['z']:.1f}) "
            )
        drone.wait(5)

    # Take off
    drone.takeoff(z=1.0)
    drone.wait(5)

    # Master drone logic: drone with lowest ID becomes master
    discovered_drones = drone.get_discovered_drones()
    all_drones = discovered_drones | {drone.drone_id}
    master_drone_id = min(all_drones)
    
    if drone.drone_id == master_drone_id:
        logging.info(f"Drone {drone.drone_id} is MASTER - controlling swarm")
        
        # Master sends individual coordinates to each drone
        discovered_drones = drone.get_discovered_drones()
        
        # Send coordinates to each drone separately
        for target_drone_id in discovered_drones:
            # Different coordinates for each drone
            coordinates = {
                1: {"x": 2, "y": 0, "z": 1},
                2: {"x": -2, "y": 0, "z": 1},
                3: {"x": 0, "y": 2, "z": 1}
            }.get(target_drone_id, {"x": 0, "y": 0, "z": 1})
            
            # Compact format for individual drone
            flight_command = {
                "t": "fc",  # flight_command
                "m": drone.drone_id,  # master_id
                "d": target_drone_id,  # target drone id
                "x": coordinates["x"],
                "y": coordinates["y"],
                "z": coordinates["z"]
            }
            
            json_msg = json.dumps(flight_command)
            logging.info(f"Master sending to drone {target_drone_id}: {json_msg} ({len(json_msg)} chars)")
            
            drone.broadcast_custom_message(json_msg)
        
        # Master flies to its position
        drone.navigate_with_avoidance(x=0.0, y=0.0, z=1.0)
    else:
        logging.info(f"Drone {drone.drone_id} is SLAVE - waiting for master commands")
        
        # Wait for master commands and execute them
        drone.wait(3)  # Wait for master to send commands
        
        # Execute received coordinates if available
        if slave_target:
            logging.info(f"Slave {drone.drone_id} flying to: {slave_target}")
            drone.navigate_with_avoidance(
                x=slave_target["x"], 
                y=slave_target["y"], 
                z=slave_target["z"]
            )
        else:
            logging.warning(f"Slave {drone.drone_id} no target received, flying to default")
            drone.navigate_with_avoidance(x=0.0, y=0.0, z=1.0)

    # Broadcast message to other drones
    drone.broadcast_custom_message(f"Hello from drone_{drone.drone_id}!")

    # Land
    drone.land()

    drone.wait(10)
