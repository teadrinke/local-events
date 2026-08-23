import asyncio
import logging
from math import isnan
from typing import Any

import pgeocode
from cachetools import TTLCache

from app.core.config import settings
from app.models.event import Event, EventQuery, EventsResponse
from app.providers.base import EventProvider, ProviderError
from app.services.distance import Coordinate, DistanceCalculator

logger = logging.getLogger(__name__)

CACHE_MAXSIZE = 256


class EventService:
    def __init__(
        self,
        providers: list[EventProvider],
        distance_calculator: DistanceCalculator,
        cache: TTLCache | None = None,
    ) -> None:
        self._providers = providers
        self._distance_calculator = distance_calculator
        self._cache: TTLCache = (
            cache
            if cache is not None
            else TTLCache(maxsize=CACHE_MAXSIZE, ttl=settings.cache_ttl_s)
        )
        self._geocoder = pgeocode.Nominatim("us")

    async def search(self, query: EventQuery) -> EventsResponse:
        key = self._cache_key(query)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        events, sources_queried, sources_failed = await self._gather(query)
        self._apply_distances(query.postal_code, events)

        events.sort(key=lambda event: event.starts_at)
        events = events[: query.limit]

        response = EventsResponse(
            events=events,
            count=len(events),
            sources_queried=sources_queried,
            sources_failed=sources_failed,
        )
        self._cache[key] = response
        return response

    @staticmethod
    def _cache_key(query: EventQuery) -> tuple[Any, ...]:
        return (
            query.postal_code,
            query.radius_mi,
            query.start_date,
            query.end_date,
            query.limit,
        )

    async def _gather(
        self, query: EventQuery
    ) -> tuple[list[Event], list[str], list[str]]:
        results = await asyncio.gather(
            *(provider.search_events(query) for provider in self._providers),
            return_exceptions=True,
        )

        events: list[Event] = []
        queried: list[str] = []
        failed: list[str] = []
        for provider, result in zip(self._providers, results):
            queried.append(provider.name)
            if isinstance(result, ProviderError):
                logger.warning("provider %s failed: %s", provider.name, result)
                failed.append(provider.name)
            elif isinstance(result, BaseException):
                logger.exception(
                    "provider %s raised an unexpected error", provider.name,
                    exc_info=result,
                )
                failed.append(provider.name)
            else:
                # Events from every provider are concatenated as-is. Cross-source
                # dedup is deliberately out of scope. Two cases look alike and
                # must not be conflated:
                #
                #   Same show, several nights, one provider -> genuinely distinct
                #   events with distinct ids (a residency at one venue). These
                #   must NOT be merged; collapsing them hides real dates.
                #
                #   Same show, same night, two providers -> true duplicates, each
                #   carrying that source's own id.
                #
                # The intended matching signal is external_ids: the same show
                # usually shares a ticketmaster/seatgeek ticketing link across
                # sources, so an overlapping seller URL is strong evidence.
                # Artist + venue + start time is the fallback, and it is only a
                # fallback because those differ in spelling and precision
                # between feeds.
                events.extend(result)
        return events, queried, failed

    def _apply_distances(self, postal_code: str, events: list[Event]) -> None:
        origin = self._resolve_origin(postal_code)
        if origin is None:
            logger.warning(
                "could not resolve origin %r; leaving distances unset", postal_code
            )
            return

        destinations: list[Coordinate | None] = [
            (event.venue_lat, event.venue_lon)
            if event.venue_lat is not None and event.venue_lon is not None
            else None
            for event in events
        ]
        for event, result in zip(events, self._distance_calculator.distances(origin, destinations)):
            event.distance_mi = result.miles if result else None

    def _resolve_origin(self, postal_code: str) -> Coordinate | None:
        record = self._geocoder.query_postal_code(postal_code.strip())
        lat, lon = record.get("latitude"), record.get("longitude")
        if lat is None or lon is None or isnan(float(lat)) or isnan(float(lon)):
            return None
        return float(lat), float(lon)
