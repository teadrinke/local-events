import logging
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.models.event import EventQuery, EventsResponse
from app.providers.base import LocationNotFoundError, ProviderError
from app.services.event_service import EventService

logger = logging.getLogger(__name__)

router = APIRouter()


def get_event_service(request: Request) -> EventService:
    """Hands over the single service built during app startup."""
    return request.app.state.event_service


@router.get("/events", response_model=EventsResponse)
async def search_events(
    service: Annotated[EventService, Depends(get_event_service)],
    postal_code: Annotated[str, Query(pattern=r"^\d{5}$")],
    radius_mi: Annotated[int, Query(ge=1, le=100)] = 25,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> EventsResponse:
    query = EventQuery(
        postal_code=postal_code,
        radius_mi=radius_mi,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    try:
        return await service.search(query)
    except LocationNotFoundError as exc:
        # Checked before ProviderError, which it subclasses. A well-formed but
        # non-existent postal code is bad input, not an upstream outage.
        logger.info("unresolvable postal code %s: %s", postal_code, exc)
        raise HTTPException(
            status_code=404,
            detail=f"Postal code {postal_code} could not be found.",
        ) from exc
    except ProviderError as exc:
        # Log the upstream detail; hand the client a message with none of it.
        logger.error("event search failed: %s", exc)
        raise HTTPException(
            status_code=502, detail="Upstream event provider is unavailable."
        ) from exc
