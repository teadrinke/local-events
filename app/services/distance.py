from abc import ABC, abstractmethod
from math import asin, cos, radians, sin, sqrt

from pydantic import BaseModel

EARTH_RADIUS_MI = 3958.7613

Coordinate = tuple[float, float]


class DistanceResult(BaseModel):
    miles: float
    duration_minutes: int | None = None  # None for straight-line


class DistanceCalculator(ABC):
    @abstractmethod
    def distances(
        self, origin: Coordinate, destinations: list[Coordinate | None]
    ) -> list[DistanceResult | None]:
        """Distances from origin to every destination, index-aligned.

        Takes and returns whole lists so a routing-API implementation can
        answer in one round trip instead of one call per event. A None
        destination yields None at the same index.
        """


class HaversineCalculator(DistanceCalculator):
    def distances(
        self, origin: Coordinate, destinations: list[Coordinate | None]
    ) -> list[DistanceResult | None]:
        return [
            DistanceResult(miles=self._haversine_mi(origin, dest)) if dest else None
            for dest in destinations
        ]

    @staticmethod
    def _haversine_mi(origin: Coordinate, dest: Coordinate) -> float:
        lat1, lon1 = radians(origin[0]), radians(origin[1])
        lat2, lon2 = radians(dest[0]), radians(dest[1])
        a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
        return 2 * EARTH_RADIUS_MI * asin(sqrt(a))
