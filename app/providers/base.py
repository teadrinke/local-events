from abc import ABC, abstractmethod

from app.models.event import Event, EventQuery


class ProviderError(Exception):
    """The only exception this layer raises. No httpx error may escape."""


class LocationNotFoundError(ProviderError):
    """The query location could not be resolved: bad input, not an outage.

    Subclasses ProviderError so existing handlers keep catching it.
    """


class EventProvider(ABC):
    name: str

    @abstractmethod
    async def search_events(self, query: EventQuery) -> list[Event]:
        """Return normalized events matching the query."""
