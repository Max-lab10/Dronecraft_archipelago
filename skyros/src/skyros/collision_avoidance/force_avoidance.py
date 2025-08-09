import math
import time
from typing import Dict, Tuple

from skyros.drone_data import DroneInfo, DronePosition

from .abstract_avoidance import CollisionAvoidance


class ForceCollisionAvoidance(CollisionAvoidance):
    # Collision avoidance constants
    COLLISION_RADIUS = 0.15  # drone radius in meters
    FORCE_EXPONENT = 1.45  # force peaks at d=1 (drone radius) and decays to both sides
    MAX_SPEED = 1.5  # maximum speed in meters per second
    MAX_ACCELERATION = 3.0  # maximum acceleration in meters per second^2
    REPULSION_STRENGTH = 5000.0  # repulsion force strength
    ATTRACTION_STRENGTH = 50.0  # attraction to target strength
    ARRIVAL_RADIUS = 0.75  # start slowing down within this distance
    TARGET_THRESHOLD = 0.2  # distance at which target is considered "reached" (meters)
    TARGET_SPEED_THRESHOLD = 0.1  # speed at which target is considered "reached" (m/s)
    BASE_DAMPING = 0.1  # base velocity damping factor
    FORCE_DAMPING_FACTOR = 0.05  # how much to increase damping based on force magnitude
    MAX_DAMPING = 0.25  # maximum damping coefficient

    def __init__(self):
        self._last_collision_log = 0.0
        super().__init__()

    def calculate_repulsion_force(self, distance: float) -> float:
        """Calculate repulsion force that peaks at drone radius"""
        if distance >= self.COLLISION_RADIUS * 10:
            return 0.0

        if distance < self.COLLISION_RADIUS:
            return 0.0

        # Normalize distance to drone radius
        d = distance / self.COLLISION_RADIUS
        # Force peaks at d=1 (drone radius) and decays to both sides
        force = self.REPULSION_STRENGTH * math.exp(-((d - 1) ** self.FORCE_EXPONENT))
        return force

    def get_avoidance_vector(
        self,
        my_pos: DronePosition,
        target_pos: DronePosition,
        other_drones: Dict[int, DroneInfo],
        dt: float = 0.1,
    ) -> Tuple[float, float, float]:
        """Calculate avoidance vector based on other drones' positions"""

        # Calculate desired movement direction
        dx_target = target_pos.x - my_pos.x
        dy_target = target_pos.y - my_pos.y
        dist_to_target = math.sqrt(dx_target**2 + dy_target**2)

        # Clamp the magnitude
        if dist_to_target > self.ARRIVAL_RADIUS:
            dx_target = dx_target / dist_to_target * self.ARRIVAL_RADIUS
            dy_target = dy_target / dist_to_target * self.ARRIVAL_RADIUS

        attraction_mult = self.ATTRACTION_STRENGTH
        APPROACH_RADIUS = self.ARRIVAL_RADIUS * 1.5
        if dist_to_target < APPROACH_RADIUS:
            # Gradually decrease attraction as we get closer to target
            attraction_mult *= max(0.1, (dist_to_target / APPROACH_RADIUS) ** 1.0)

        attr_fx = dx_target * attraction_mult
        attr_fy = dy_target * attraction_mult

        fx = 0
        fy = 0

        distances = {}
        for drone_id, drone_info in other_drones.items():
            other_pos = drone_info.position
            dx = my_pos.x - other_pos.x
            dy = my_pos.y - other_pos.y
            distance = math.sqrt(dx**2 + dy**2)
            distances[drone_id] = distance

            # Predict future positions based on current velocities
            future_dx = (my_pos.x + my_pos.vx * dt) - (other_pos.x + other_pos.vx * dt)
            future_dy = (my_pos.y + my_pos.vy * dt) - (other_pos.y + other_pos.vy * dt)
            future_distance = math.sqrt(future_dx**2 + future_dy**2)

            # If future distance is less than current, increase repulsion
            if future_distance < distance:
                distance_factor = distance / max(future_distance, self.COLLISION_RADIUS * 0.1)
            else:
                distance_factor = 1.0

            # Calculate repulsion force
            force = self.calculate_repulsion_force(distance) * distance_factor
            if force == 0:
                continue

            # Normalize direction vector
            if distance > 0:
                dx /= distance
                dy /= distance

            # Add force components
            fx += dx * force
            fy += dy * force

            # Add extra repulsion based on relative velocity when getting closer
            if future_distance < distance:
                rel_vx = my_pos.vx - other_pos.vx
                rel_vy = my_pos.vy - other_pos.vy
                # Add opposing force to relative velocity
                fx -= rel_vx * force * 0.1
                fy -= rel_vy * force * 0.1

        repulsion_force = math.sqrt(fx**2 + fy**2)
        attraction_force = math.sqrt(attr_fx**2 + attr_fy**2)
        if repulsion_force > attraction_force and time.time() - self._last_collision_log > 2.0:
            self._logger.warning(
                f"[Collision avoidance] Preventing collision (attraction: {attraction_force:.2f}, "
                f"repulsion: {repulsion_force:.2f})"
            )
            self._logger.warning(
                f"[Collision avoidance] Distances: {' | '.join([f'{drone_id}: {distance:.2f} m' for drone_id, distance in distances.items()])}"
            )
            self._last_collision_log = time.time()

        # Calculate total force magnitude for adaptive damping
        fx += attr_fx
        fy += attr_fy
        total_force = math.sqrt(fx**2 + fy**2)

        # Apply forces to velocity with damping
        damping = min(self.BASE_DAMPING + total_force * self.FORCE_DAMPING_FACTOR, self.MAX_DAMPING)

        # Calculate desired new velocity
        prev_vx, prev_vy, prev_vz = self._previous_velocity
        desired_vx = prev_vx * damping + fx * (1 - damping)
        desired_vy = prev_vy * damping + fy * (1 - damping)

        # Calculate acceleration as change in velocity over time
        ax = (desired_vx - prev_vx) / dt
        ay = (desired_vy - prev_vy) / dt

        # Limit acceleration magnitude while preserving direction
        acceleration = math.sqrt(ax * ax + ay * ay)
        if acceleration > self.MAX_ACCELERATION:
            ax *= self.MAX_ACCELERATION / acceleration
            ay *= self.MAX_ACCELERATION / acceleration

        # Apply limited acceleration to velocity
        vx = prev_vx + ax * dt
        vy = prev_vy + ay * dt
        vz = 0

        # Limit velocity magnitude
        velocity = math.sqrt(vx * vx + vy * vy)
        if velocity > self.MAX_SPEED:
            vx *= self.MAX_SPEED / velocity
            vy *= self.MAX_SPEED / velocity

        if velocity < self.TARGET_SPEED_THRESHOLD and dist_to_target < self.TARGET_THRESHOLD:
            vx = 0
            vy = 0
            vz = 0

        self._previous_velocity = (vx, vy, vz)
        return vx, vy, vz
