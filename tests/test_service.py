from datetime import datetime, timedelta, timezone

import pytest

from app.models.event import Event, EventQuery
from app.providers.base import EventProvider, LocationNotFoundError, ProviderError
from app.services.distance import HaversineCalculator
from app.services.event_service import EventService

BASE = datetime(2026, 9, 1, tzinfo=timezone.utc)


def make_event(name: str, hours: int) -> Event:
    return Event(
        id=f"stub:{name}",
        source="stub",
        title=name,
        venue_name="Venue",
        venue_lat=34.05,
        venue_lon=-118.24,
        starts_at=BASE + timedelta(hours=hours),
    )


class StubProvider(EventProvider):
    def __init__(self, name: str, events: list[Event]) -> None:
        self.name = name
        self._events = events

    async def search_events(self, query: EventQuery) -> list[Event]:
        return list(self._events)


class FailingProvider(EventProvider):
    def __init__(self, name: str, error: Exception) -> None:
        self.name = name
        self._error = error

    async def search_events(self, query: EventQuery) -> list[Event]:
        raise self._error


@pytest.fixture(autouse=True)
def offline_geocoder(monkeypatch):
    """Keep the suite offline.

    EventService builds a pgeocode.Nominatim in __init__, which downloads a
    GeoNames snapshot the first time it runs on a machine. These tests stub
    _resolve_origin anyway, so the real geocoder is never needed.
    """

    class Unused:
        def query_postal_code(self, postal_code):
            raise AssertionError("the geocoder should not be reached in tests")

    monkeypatch.setattr(
        "app.services.event_service.pgeocode.Nominatim", lambda country: Unused()
    )


def build_service(providers: list[EventProvider]) -> EventService:
    service = EventService(providers, HaversineCalculator())
    # Keep the geocoder offline and deterministic; distance maths is not
    # what these tests are about.
    service._resolve_origin = lambda postal_code: (34.05, -118.24)
    return service


@pytest.mark.asyncio
async def test_sorts_and_limits():
    # Deliberately out of order so sorting cannot pass by accident.
    unsorted = [make_event("late", 10), make_event("early", 1), make_event("mid", 5)]
    service = build_service([StubProvider("stub", unsorted)])

    response = await service.search(EventQuery(postal_code="90012", limit=2))

    assert [event.title for event in response.events] == ["early", "mid"]
    assert response.count == 2
    # The limit must cut the sorted list, not the provider's original order:
    # "late" arrived first but must not survive a limit of 2.
    assert "late" not in {event.title for event in response.events}


@pytest.mark.asyncio
async def test_provider_failure_isolated():
    healthy = StubProvider("healthy", [make_event("kept", 1)])
    broken = FailingProvider("broken", ProviderError("upstream down"))
    service = build_service([healthy, broken])

    response = await service.search(EventQuery(postal_code="90012"))

    assert [event.title for event in response.events] == ["kept"]
    assert response.sources_failed == ["broken"]
    assert response.sources_queried == ["healthy", "broken"]


@pytest.mark.asyncio
async def test_location_error_propagates():
    healthy = StubProvider("healthy", [make_event("kept", 1)])
    lost = FailingProvider("lost", LocationNotFoundError("could not resolve '00000'"))
    service = build_service([healthy, lost])

    # Bad input, not an outage: it must not be masked by fan-out isolation,
    # even though LocationNotFoundError subclasses ProviderError.
    with pytest.raises(LocationNotFoundError):
        await service.search(EventQuery(postal_code="00000"))
