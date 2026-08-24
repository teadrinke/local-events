# Local Events

Search for upcoming live music events near a US postal code. FastAPI backend over the
JamBase v3 Data API, with a vanilla JavaScript frontend served from the same app.

## Setup

Windows (PowerShell):

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

macOS / Linux:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Add your JamBase API key to `.env` before starting the server — the app fails at
startup if it's missing, rather than at the first request.

Then open http://127.0.0.1:8000

Note: the first search downloads a GeoNames postal-code dataset via pgeocode and
caches it locally (about 5.4MB on disk once extracted, in `~/.cache/pgeocode`). That
request is separate from the JamBase call and doesn't go through the app's HTTP
client, so the first run needs general network access. Subsequent runs work from the
cache.

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

Tests run fully offline against a saved API response in
`tests/fixtures/jambase_sample.json`. No API key or network access is required — HTTP
and geocoding are both stubbed.

## API

### GET /events

| Param | Type | Default | Bounds |
|---|---|---|---|
| postal_code | string | required | 5 digits |
| radius_mi | int | 25 | 1–100 |
| start_date | date | none | YYYY-MM-DD |
| end_date | date | none | YYYY-MM-DD |
| limit | int | 50 | 1–200 |

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
change when providers are added — and the frontend uses it to distinguish "no events
here" from "the source is down", since both return 200 with an empty list.

Status codes: 200 success, 404 postal code could not be resolved, 422 invalid
parameters. A 502 is defined for an upstream provider error, but the service currently
absorbs provider failures into `sources_failed`, so even a total outage returns 200 —
see NOTES.md.

### GET /health

Returns `{"status": "ok"}`. Shallow — confirms the app is running, does not check
JamBase reachability.

### GET /docs

Interactive OpenAPI documentation.

## Project structure

```
app/
  main.py                     app wiring; the only file that names JamBase
  core/config.py              settings from .env, validated at startup
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

Each package also carries an empty `__init__.py`.

Dependencies point one direction: `models` imports nothing from the app, `providers`
and `services` import `models`, `api` imports `services`. Adding a second event source
means one new file in `providers/` and one line in `main.py` — nothing else changes.

## Known limitations

See NOTES.md.

## Time spent

TODO — I'll fill this in.
