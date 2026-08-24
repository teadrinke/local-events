# Local Events

Search for upcoming live music events near a US postal code. FastAPI backend over the
JamBase v3 Data API, with a vanilla JavaScript frontend served from the same app.

Requires Python 3.10 or newer.

## Setup

Windows (PowerShell):

```powershell
py -3 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

The `.\` prefix is required: PowerShell does not search the current directory for
commands, so the bare path fails with `CouldNotAutoLoadModule`. `py -3` is the Windows
Python launcher pinned to Python 3: a bare `python` can resolve to the Microsoft Store
app execution alias, which is not a usable interpreter, and a bare `py` follows
whatever default `py.ini` or `PY_PYTHON` sets.

macOS / Linux:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Add your JamBase API key to `.env` before starting the server. The app fails at
startup if `JAMBASE_API_KEY` is absent from the environment entirely. An empty value
passes that check, and `.env.example` ships it empty, so a `.env` copied but not
filled in starts cleanly and fails at the first search with a 401 from JamBase.

Then open http://127.0.0.1:8000

Note: the first search downloads a GeoNames postal-code dataset via pgeocode and
caches it locally as `US.txt` and `US-index.txt`, about 2.7MB each and 5.4MB for the
pair, in `~/.cache/pgeocode` (override with `PGEOCODE_DATA_DIR`). That request is
separate from the JamBase call and doesn't go through the app's HTTP client, so the
first run needs general network access. Subsequent runs work from the cache.

Startup itself never touches the network. The dataset is loaded on the first geocode,
not during app startup, so a failed download costs that one search and nothing else:
`/health` and `/docs` still come up.

## API key

Get a trial key from data.jambase.com (14 days, no card required).

This uses the **v3 Data API** at `api.data.jambase.com`, authenticated with a Bearer
token in the Authorization header. It is a different product from the legacy v1
endpoint at `www.jambase.com/jb-api/v1`, which takes the key as a query parameter and
will reject a v3 key as invalid.

## Tests

```bash
pytest
```

11 tests, all offline. They run against a saved API response in
`tests/fixtures/jambase_sample.json`. No API key or network access is required: HTTP
and geocoding are both stubbed.

## API

### GET /events

| Param | Type | Default | Bounds |
|---|---|---|---|
| postal_code | string | required | 5 digits |
| radius_mi | int | 25 | 1-100 |
| start_date | date | none | YYYY-MM-DD |
| end_date | date | none | YYYY-MM-DD |
| limit | int | 50 | 1-200 |

Example:

```
GET /events?postal_code=90007&radius_mi=25&limit=1
```

```json
{
  "events": [
    {
      "id": "jambase:16912141",
      "source": "jambase",
      "title": "Maldita Vecindad at Pershing Square",
      "artist": "Maldita Vecindad",
      "venue_name": "Pershing Square",
      "venue_city": "Los Angeles",
      "venue_lat": 34.0486,
      "venue_lon": -118.2529,
      "starts_at": "2026-08-23T21:00:00Z",
      "time_tbd": false,
      "ticket_url": "https://prod-nts-api.seeticketsusa.us/v1.0.0/promote/...",
      "price_min": null,
      "price_max": null,
      "currency": "USD",
      "genres": [],
      "distance_mi": 2.3651748350403565,
      "external_ids": {
        "see-tickets": "https://prod-nts-api.seeticketsusa.us/...",
        "stubhub": "https://stubhub.prf.hn/..."
      }
    }
  ],
  "count": 1,
  "sources_queried": ["jambase"],
  "sources_failed": []
}
```

Optional fields degrade to `null` or `[]` rather than being omitted: many events carry
no price, and some carry no genres or ticket link. `distance_mi` is returned at full
precision; the frontend rounds it for display.

`sources_queried` and `sources_failed` exist so a partial failure is visible to the
client. With one provider `sources_failed` is always empty, but the shape doesn't
change when providers are added, and the frontend uses it to distinguish "no events
here" from "the source is down", since both return 200 with an empty list.

Status codes: 200 success, 404 postal code could not be resolved, 422 invalid
parameters, 503 the postal-code dataset could not be loaded. The 503 is returned
whichever call site hit the failure first, the provider resolving the query or the
service resolving the distance origin, because it is the same geocoder and the same
outage; the failure is not cached, so a retry is worth making.

A 502 is defined for an upstream provider error but is not reachable in practice: the
service absorbs provider failures into `sources_failed`, so even a total outage returns
200 (see NOTES.md).

### GET /health

Returns `{"status": "ok"}`. Shallow: confirms the app is running, does not check
JamBase reachability.

### GET /docs

Interactive OpenAPI documentation.

## Project structure

```
app/
  main.py                     app wiring; the only file that names JamBase
  core/config.py              settings from .env, validated at startup
  core/errors.py              GeocoderUnavailableError
  core/geocoding.py           shared lazy postal-code geocoder
  models/event.py             EventQuery, Event, EventsResponse
  providers/base.py           EventProvider contract + error types
  providers/jambase.py        JamBase v3 client and normalization
  services/event_service.py   caching, fan-out, enrichment, sorting
  services/distance.py        DistanceCalculator contract + Haversine
  api/routes.py               GET /events
  static/index.html           frontend
tests/
  fixtures/                   saved API response
  test_normalization.py       mapping tests
  test_service.py             orchestration tests
```

Each package also carries an `__init__.py`. All are empty except the top-level
`app/__init__.py`, which holds the Python version check.

Dependencies point one direction: `models` and `core` import nothing from the rest of
the app, `providers` and `services` import `models` and `core`, `api` imports
`services`. The geocoder sits in `core` because both `providers` and `services`
geocode; putting it in either one would have made the other import upwards. Adding a
second event source means one new file in `providers/` and one line in `main.py`;
nothing else changes.

## Known limitations

See NOTES.md.

## Time spent

~2.5 hours of implementation, plus design work beforehand and this writeup afterward.
