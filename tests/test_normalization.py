import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.models.event import Event, EventQuery
from app.providers.jambase import JamBaseProvider

FIXTURE = Path(__file__).parent / "fixtures" / "jambase_sample.json"
DATE_ONLY = re.compile(r"\d{4}-\d{2}-\d{2}$")


@pytest.fixture(scope="module")
def raw_events() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["events"]


@pytest.fixture
def provider() -> JamBaseProvider:
    # No client is needed: every test drives the mapping directly or stubs the
    # HTTP step, so nothing here reaches the network.
    return JamBaseProvider(client=None)


def scheduled(raws: list[dict]) -> list[dict]:
    return [r for r in raws if r.get("eventStatus") == "scheduled"]


async def search_with(provider: JamBaseProvider, payload: dict) -> list[Event]:
    """Run search_events with the network and geocoding steps stubbed out."""

    async def fake_get_events(query, lat, lon):
        return payload

    provider._resolve_postal_code = lambda postal_code: (34.05, -118.24)
    provider._get_events = fake_get_events
    return await provider.search_events(EventQuery(postal_code="90012"))


def test_fixture_is_valid(raw_events):
    # The fixture was once a saved 401 error document: valid JSON, no data.
    assert isinstance(raw_events, list)
    assert len(raw_events) > 0
    assert all("identifier" in raw for raw in raw_events)


@pytest.mark.asyncio
async def test_maps_fixture_cleanly(provider, raw_events):
    events = await search_with(provider, {"events": raw_events})

    assert all(isinstance(event, Event) for event in events)
    assert len(events) == len(scheduled(raw_events))


@pytest.mark.asyncio
async def test_canceled_events_skipped(provider, raw_events):
    canceled = {
        raw["identifier"]
        for raw in raw_events
        if raw.get("eventStatus") != "scheduled"
    }
    assert canceled, "fixture must contain at least one non-scheduled event"

    events = await search_with(provider, {"events": raw_events})

    assert canceled.isdisjoint({event.id for event in events})


def test_time_tbd_flag(provider, raw_events):
    # Checked at the mapping level so all four date-only entries are covered,
    # including the one that is also canceled and never reaches search results.
    expected = {
        raw["identifier"]
        for raw in raw_events
        if DATE_ONLY.fullmatch(raw["startDate"])
    }
    assert expected, "fixture must contain at least one date-only startDate"

    mapped = [provider._to_event(raw) for raw in raw_events]

    assert {event.id for event in mapped if event.time_tbd} == expected
    assert {event.id for event in mapped if not event.time_tbd} == {
        raw["identifier"] for raw in raw_events
    } - expected


def test_starts_at_is_utc_aware(provider, raw_events):
    mapped = [provider._to_event(raw) for raw in raw_events]

    assert all(event.starts_at.tzinfo is not None for event in mapped)
    assert all(event.starts_at.utcoffset() == timezone.utc.utcoffset(None) for event in mapped)

    # 2026-08-23T19:00:00 in America/Los_Angeles (PDT, UTC-7) is 02:00 UTC next day.
    spot = next(event for event in mapped if event.id == "jambase:16222113")
    assert spot.starts_at == datetime(2026, 8, 24, 2, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_malformed_event_skipped(provider, raw_events):
    good = scheduled(raw_events)[:2]
    broken = {"identifier": "jambase:BROKEN", "eventStatus": "scheduled",
              "name": "No location here", "startDate": "2026-09-01T20:00:00"}

    events = await search_with(provider, {"events": [broken, *good]})

    assert [event.id for event in events] == [raw["identifier"] for raw in good]
    assert "jambase:BROKEN" not in {event.id for event in events}


def test_headliner_selection(provider, raw_events):
    # In this fixture the headliner happens to sit at performer[0] every time,
    # so the entry is permuted first: without that, a buggy performer[0]
    # implementation would pass this test.
    source = next(
        raw for raw in raw_events
        if len(raw.get("performer") or []) > 1
        and raw["performer"][0].get("x-isHeadliner")
        and sum(1 for p in raw["performer"] if p.get("x-isHeadliner")) == 1
    )
    headliner_name = source["performer"][0]["name"]

    permuted = dict(source, performer=list(reversed(source["performer"])))
    assert not permuted["performer"][0].get("x-isHeadliner")

    event = provider._to_event(permuted)

    assert event.artist == headliner_name
    assert event.artist != permuted["performer"][0]["name"]


def test_headliner_tie_picks_best_rank(provider, raw_events):
    # jambase:16348684 flags three headliners, two of them sharing rank 1:
    #   rank 1  jambase:45790   Janelle Monae
    #   rank 1  jambase:43207   John Legend
    #   rank 2  jambase:249414  Raphael Saadiq
    # The identifier breaks the rank-1 tie, so John Legend wins regardless of
    # the order the API sends the performers in.
    source = next(raw for raw in raw_events if raw["identifier"] == "jambase:16348684")
    reversed_order = dict(source, performer=list(reversed(source["performer"])))

    assert provider._to_event(source).artist == "John Legend"
    assert provider._to_event(reversed_order).artist == "John Legend"
