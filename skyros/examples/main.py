import logging
from skyros.drone import Drone
import rospy
from clover import srv
from std_srvs.srv import Trigger
from led_msgs.srv import SetLEDs
from led_msgs.msg import LEDStateArray, LEDState
import json
import sys
from std_msgs.msg import String

def setup_logger(verbose=False, quiet=False):
    """Set up simple CLI logger"""
    level = logging.DEBUG if verbose else (logging.WARNING if quiet else logging.INFO)
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        stream=sys.stdout
    )
    
    return logging.getLogger()

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

def read_string_from_topic(topic_name='/name_of_topic', timeout=5.0): #по прилету на точку через цикл прогоняем 10 раз
    try:
        msg = rospy.wait_for_message(topic_name, String, timeout=timeout)
        return msg.data 
    except rospy.exceptions.ROSException as e:
        rospy.logwarn(f"can't connect {e}")
        return None

def decoding_qr(qr_code=read_string_from_topic()): 
    """Парсит QR-код и возвращает информацию"""
    if len(qr_code) != 6:
        raise ValueError("wrong format")
    
    recipe_id = int(qr_code[0])
    qr_position = int(qr_code[1])
    blocks = qr_code[2:6]
    
    recipes = {
        0: "pick", #кикра
        1: "axe", #топор
        2: "mace" #булава
    }
    
    print(f"Recepie: {recipes.get(recipe_id, 'unknown')}")
    print(f"Position QR: {qr_position}")
    print(f"Blocks: {blocks}")
    
    return recipe_id, qr_position, blocks

rospy.init_node('flight')

get_telemetry = rospy.ServiceProxy('get_telemetry', srv.GetTelemetry)
navigate = rospy.ServiceProxy('navigate', srv.Navigate)
navigate_global = rospy.ServiceProxy('navigate_global', srv.NavigateGlobal)
set_position = rospy.ServiceProxy('set_position', srv.SetPosition)
set_velocity = rospy.ServiceProxy('set_velocity', srv.SetVelocity)
set_attitude = rospy.ServiceProxy('set_attitude', srv.SetAttitude)
set_rates = rospy.ServiceProxy('set_rates', srv.SetRates)
land = rospy.ServiceProxy('land', Trigger)
set_leds = rospy.ServiceProxy('led/set_leds', SetLEDs)
slave_target = None

# Set up logging
logging.basicConfig(level=logging.INFO)

# Create and start drone
with Drone(network_id=0x52, wifi_channel=6) as drone:
    setup_logger()
    drone.set_custom_message_callback(handle_message)
    # Wait for other drones to be discovered
    if drone.wait_for_drones(n=3, timeout=30.0): #n = 1 or 3
        print("Other drones discovered!")
        status = drone.get_network_status()
        print(f"Telemetry-discovered drones: {status['telemetry_discovered_count']}")
        print(f"Total discovered drones: {status['discovered_drones']}")

        # Show detailed drone info
        for drone_id, details in status["drone_details"].items():
            pos = details["position"]
            print(
                f"  drone_{drone_id}: pos=({pos['x']:.1f},{pos['y']:.1f},{pos['z']:.1f}) "
                f"vel=({pos['vx']:.1f},{pos['vy']:.1f},{pos['vz']:.1f}) "
                f"age={details['age_seconds']:.1f}s "
                f"via={details['discovered_via']}")
        # Take off
        drone.takeoff(z=1.5)
        drone.wait(5)
        set_leds(LEDState(255, 255, 255))
        discovered_drones = drone.get_discovered_drones()
        all_drones = discovered_drones | {drone.drone_id}
        master_drone_id = min(all_drones)
        # Navigate with collision avoidance
        if drone.drone_id == master_drone_id:
            logging.info(f"Drone {drone.drone_id} is MASTER - controlling swarm")
            discovered_drones = drone.get_discovered_drones()
            

        drone.navigate_with_avoidance(x=0.0, y=0.0, z=1.5)

        # Land
        # navigate(x=0, y=0, z=-2, frame_id='body')
        drone.navigate_with_avoidance(x=0.0, y=0.0, z=-1.5, frame_id="body")
        drone.wait(5)
        drone.land()