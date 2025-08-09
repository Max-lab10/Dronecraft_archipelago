#!/usr/bin/env python3
"""
Example usage of the updated drone.py library with wait_for_drones functionality
"""

import time

from skyros.drone import Drone


def example_basic_usage():
    """Basic drone usage with direct ID"""
    print("=== Basic Drone Usage ===")

    # Create drone with specific ID - automatically named "drone_5"
    drone = Drone(drone_id=5)
    print(f"Created drone: {drone.name} with ID: {drone.drone_id}")

    # Or with custom name
    custom_drone = Drone(drone_id=10, name="leader_drone")
    print(f"Created drone: {custom_drone.name} with ID: {custom_drone.drone_id}")


def example_wait_for_drones():
    """Example of waiting for other drones via telemetry with expiration"""
    print("\n=== Wait for Drones via Telemetry Example ===")

    # Create drone that will wait for others
    drone = Drone(drone_id=1)

    try:
        with drone:  # Start the drone
            # Configure drone expiry timeout (default is 5 seconds)
            drone.set_drone_expiry_timeout(3.0)  # Expire after 3 seconds offline

            print(f"{drone.name} started, waiting for 2 other drones via telemetry...")
            print("Note: Only drones sending telemetry packets will be discovered")
            print("Drones will expire if telemetry not received for 3 seconds")

            # Wait for 2 other drones to be discovered via telemetry
            if drone.wait_for_drones(n=2, timeout=30.0):
                print("All required drones found via telemetry! Starting mission...")

                # Get network status with detailed info
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
                        f"via={details['discovered_via']}"
                    )

                # Monitor for 10 seconds to see expiration in action
                print("\nMonitoring drone status for 10 seconds...")
                for i in range(10):
                    time.sleep(1)
                    current_discovered = drone.get_discovered_drones()
                    print(f"Active drones: {sorted(list(current_discovered))}")

            else:
                print("Timeout waiting for drones, proceeding anyway...")

    except KeyboardInterrupt:
        print("Interrupted by user")


def example_swarm_coordination():
    """Example of coordinated swarm behavior"""
    print("\n=== Swarm Coordination Example ===")

    drone = Drone(drone_id=2)

    try:
        with drone:
            # Wait for at least 3 other drones
            print("Waiting for swarm to assemble...")
            if drone.wait_for_drones(n=3, timeout=60.0):
                # Get network status
                status = drone.get_network_status()
                print(f"Network status: {status}")

                # Perform coordinated takeoff
                print("Performing coordinated takeoff...")
                drone.takeoff(z=2.0)

                # Navigate with collision avoidance
                print("Navigating to formation position...")
                drone.navigate_with_avoidance(x=2.0, y=2.0, z=2.0)

                # Hold position for 10 seconds
                drone.wait(10.0)

                # Land
                print("Landing...")
                drone.land()

            else:
                print("Failed to assemble swarm")

    except Exception as e:
        print(f"Error: {e}")


def main():
    print("Updated drone.py Library Examples")
    print("=================================")

    print("\nKey improvements:")
    print("- Direct drone_id parameter instead of hash-based generation")
    print("- Automatic drone_n naming template (drone_1, drone_2, etc.)")
    print("- wait_for_drones(n) function - waits for telemetry packets (primary discovery)")
    print("- get_discovered_drones() to get list of found drones")
    print("- Telemetry-focused discovery - position data essential for swarm coordination")
    print("- Status packets only update timestamps, don't create new discoveries")
    print("- Drone expiration mechanism - drones expire if telemetry not received for >5s")
    print("- set_drone_expiry_timeout() to configure expiration time")
    print("- Enhanced network status with discovery method tracking")
    print()

    # Show basic usage
    example_basic_usage()

    print("\nTo run the wait_for_drones example, uncomment the following:")
    print("# example_wait_for_drones()")
    print("# example_swarm_coordination()")

    print("\nNote: These examples require actual ESP32 hardware connected via UART")


if __name__ == "__main__":
    main()
