from datetime import date

from pydantic import AwareDatetime, BaseModel, Field


class EventQuery(BaseModel):
    """What the user asked for."""

    postal_code: str
    radius_mi: int = Field(default=25, ge=1, le=100)
    start_date: date | None = None
    end_date: date | None = None
    limit: int = Field(default=50, ge=1, le=200)


class Event(BaseModel):
    """One normalized event, source-agnostic."""

    id: str  # namespaced, e.g. "jambase:16297877"
    source: str
    title: str
    artist: str | None = None  # headliner only
    venue_name: str
    venue_city: str | None = None
    venue_lat: float | None = None
    venue_lon: float | None = None
    starts_at: AwareDatetime
    ticket_url: str | None = None
    price_min: float | None = None
    price_max: float | None = None
    currency: str | None = None
    genres: list[str] = Field(default_factory=list)
    distance_mi: float | None = None  # filled by the service, not the provider
    external_ids: dict[str, str] = Field(default_factory=dict)  # seller ticketing links


class EventsResponse(BaseModel):
    """The API envelope."""

    events: list[Event]
    count: int
    sources_queried: list[str]
    sources_failed: list[str] = Field(default_factory=list)
