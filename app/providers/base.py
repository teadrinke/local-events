from abc import ABC, abstractmethod

from app.models.event import Event, EventQuery


class ProviderError(Exception):
    """The only exception this layer raises. No httpx error may escape."""


class EventProvider(ABC):
    name: str

    @abstractmethod
    async def search_events(self, query: EventQuery) -> list[Event]:
        """Return normalized events matching the query."""
