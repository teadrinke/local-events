import asyncio
import logging
from datetime import datetime, timezone
from functools import lru_cache
from math import isnan
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pgeocode

from app.core.config import settings
from app.models.event import Event, EventQuery
from app.providers.base import EventProvider, ProviderError

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
BACKOFF_S = 0.25


@lru_cache(maxsize=1)
def _geocoder() -> pgeocode.Nominatim:
    # pgeocode resolves postal codes against a GeoNames snapshot downloaded once
    # into a local cache, then works fully offline from that copy. The snapshot is
    # only as fresh as the installed pgeocode release, so very new or recently
    # reassigned postal codes may not resolve.
    return pgeocode.Nominatim("us")


class JamBaseProvider(EventProvider):
    name = "jambase"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def search_events(self, query: EventQuery) -> list[Event]:
        lat, lon = self._resolve_postal_code(query.postal_code)
        payload = await self._get_events(query, lat, lon)

        events: list[Event] = []
        for raw in payload.get("events") or []:
            # Product decision, not a data limitation: cancelled and postponed
            # shows are dropped rather than surfaced. A stricter version would
            # keep them and carry the status through for a badge in the UI.
            status = (raw or {}).get("eventStatus")
            if status != "scheduled":
                logger.debug(
                    "skipping non-scheduled jambase event %s (status=%s)",
                    (raw or {}).get("identifier", "<no identifier>"),
                    status,
                )
                continue
            try:
                events.append(self._to_event(raw))
            except Exception as exc:
                logger.warning(
                    "skipping malformed jambase event %s: %s",
                    (raw or {}).get("identifier", "<no identifier>"),
                    exc,
                )
        return events

    def _resolve_postal_code(self, postal_code: str) -> tuple[float, float]:
        record = _geocoder().query_postal_code(postal_code.strip())
        lat, lon = record.get("latitude"), record.get("longitude")
        if lat is None or lon is None or isnan(float(lat)) or isnan(float(lon)):
            raise ProviderError(f"could not resolve US postal code {postal_code!r}")
        return float(lat), float(lon)

    async def _get_events(
        self, query: EventQuery, lat: float, lon: float
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "geoLatitude": lat,
            "geoLongitude": lon,
            "geoRadiusAmount": query.radius_mi,
            "geoRadiusUnits": "mi",
        }
        if query.start_date:
            params["eventDateFrom"] = query.start_date.isoformat()
        if query.end_date:
            params["eventDateTo"] = query.end_date.isoformat()

        url = f"{settings.jambase_base_url.rstrip('/')}/events"
        headers = {
            "Authorization": f"Bearer {settings.jambase_api_key}",
            "Accept": "application/json",
        }

        last_error = "unknown error"
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await self._client.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=settings.request_timeout_s,
                )
            except httpx.TimeoutException as exc:
                last_error = f"timeout: {exc}"
            except httpx.HTTPError as exc:
                raise ProviderError(f"jambase request failed: {exc}") from exc
            else:
                if response.status_code < 400:
                    try:
                        return response.json()
                    except ValueError as exc:
                        raise ProviderError(
                            f"jambase returned non-JSON body: {exc}"
                        ) from exc
                if response.status_code < 500:
                    # A bad request will not fix itself.
                    raise ProviderError(
                        f"jambase rejected the request "
                        f"({response.status_code}): {response.text[:200]}"
                    )
                last_error = f"server error {response.status_code}"

            if attempt < MAX_RETRIES:
                await asyncio.sleep(BACKOFF_S * 2**attempt)

        raise ProviderError(
            f"jambase unavailable after {MAX_RETRIES + 1} attempts: {last_error}"
        )

    def _to_event(self, raw: dict[str, Any]) -> Event:
        location = raw["location"]
        address = location.get("address") or {}
        geo = location.get("geo") or {}

        headliner = self._headliner(raw.get("performer") or [])
        offer = self._primary_offer(raw.get("offers") or [])
        price = (offer.get("priceSpecification") or {}) if offer else {}

        return Event(
            id=raw["identifier"],
            source=self.name,
            title=raw["name"],
            artist=headliner.get("name") if headliner else None,
            venue_name=location["name"],
            venue_city=address.get("addressLocality") or None,
            venue_lat=geo.get("latitude"),
            venue_lon=geo.get("longitude"),
            starts_at=self._starts_at(raw["startDate"], address["x-timezone"]),
            time_tbd=self._is_date_only(raw["startDate"]),
            ticket_url=offer.get("url") if offer else None,
            price_min=self._as_float(price.get("minPrice")),
            price_max=self._as_float(price.get("maxPrice")),
            currency=price.get("priceCurrency") or None,
            genres=list(headliner.get("genre") or []) if headliner else [],
            external_ids=self._external_ids(raw.get("offers") or []),
        )

    @staticmethod
    def _headliner(performers: list[dict[str, Any]]) -> dict[str, Any] | None:
        def rank(p: dict[str, Any]) -> int:
            value = p.get("x-performanceRank")
            return int(value) if isinstance(value, (int, str)) and str(value).isdigit() else 999

        flagged = [p for p in performers if p.get("x-isHeadliner")]
        if flagged:
            # Some events flag several headliners; lowest rank wins.
            return min(flagged, key=rank)
        ranked = [p for p in performers if rank(p) == 1]
        return ranked[0] if ranked else None

    @staticmethod
    def _primary_offer(offers: list[dict[str, Any]]) -> dict[str, Any] | None:
        primaries = [o for o in offers if o.get("category") == "ticketingLinkPrimary"]
        if not primaries:
            return None
        # Several primaries can coexist; prefer one that actually carries prices.
        with_price = [o for o in primaries if o.get("priceSpecification")]
        return with_price[0] if with_price else primaries[0]

    @staticmethod
    def _external_ids(offers: list[dict[str, Any]]) -> dict[str, str]:
        ids: dict[str, str] = {}
        for offer in offers:
            seller = (offer.get("seller") or {}).get("identifier")
            url = offer.get("url")
            if seller and url:
                ids.setdefault(str(seller), str(url))
        return ids

    @staticmethod
    def _is_date_only(start_date: str) -> bool:
        # Some events carry a bare "2026-08-22" with no time component. The
        # resulting midnight is not a real door time, so callers can say so.
        return "T" not in start_date

    @staticmethod
    def _starts_at(start_date: str, tz_name: str) -> datetime:
        # startDate is naive local time (sometimes date-only); the zone is separate.
        naive = datetime.fromisoformat(start_date)
        return naive.replace(tzinfo=ZoneInfo(tz_name)).astimezone(timezone.utc)

    @staticmethod
    def _as_float(value: Any) -> float | None:
        if value in (None, ""):
            return None
        return float(value)
