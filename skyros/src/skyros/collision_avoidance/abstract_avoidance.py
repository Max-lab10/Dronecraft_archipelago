import logging
from typing import Dict, Tuple

from skyros.drone_data import DroneInfo, DronePosition


class CollisionAvoidance:
    def __init__(self):
        self._previous_velocity: Tuple[float, float, float] = (0.0, 0.0, 0.0)

        self._logger = logging.getLogger(self.__class__.__name__)

    def reset(self):
        self._previous_velocity = (0.0, 0.0, 0.0)

    def get_avoidance_vector(
        self,
        my_pos: DronePosition,
        target_pos: DronePosition,
        other_drones: Dict[int, DroneInfo],
        dt: float = 0.1,
    ) -> Tuple[float, float, float]:
        raise NotImplementedError
