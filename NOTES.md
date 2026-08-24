# Notes

## Design decisions

- JamBase v3 rejects `postalCode` with a 400. Verified the geo filters against the
  live API rather than the docs: `geoLatitude`/`geoLongitude` + `geoRadiusAmount`
  works and the radius genuinely filters (5mi: 783, 25mi: 2,076, 100mi: 3,119 results
  from the same origin). `geoCityId` and `geoMetroId` also work and return
  area-scoped results (917 and 3,736 results respectively from the same area), but
  each requires a separate ID lookup step first. So the user enters a ZIP and the
  provider resolves it to coordinates via pgeocode. That resolution doubles as the
  origin for distance calculation.

- Provider failures are absorbed into `sources_failed` rather than raised, so one dead
  provider out of many doesn't fail the whole search. Unresolvable postal codes are
  excluded from that: `LocationNotFoundError` propagates to a 404, because bad input
  isn't an upstream outage.

- A malformed individual event is logged and skipped, not fatal. One bad record
  shouldn't cost the user the other 39.

- Canceled events are filtered out. A product decision, not a data limitation — a
  stricter version would surface them with a status badge.

- Cache maxsize is a module constant rather than a setting. Not every number needs to
  be tunable.

## Known limitations

- Cached `EventsResponse` objects are returned by reference and are mutable; a caller
  mutating `response.events` corrupts the cache entry until TTL expiry. Harmless for
  the current route, which only serializes.

- pgeocode downloads a GeoNames snapshot on first use, outside the injected httpx
  client, so it has no timeout or retry handling. A first run on a restricted network
  fails at geocoding rather than at the API boundary.

- The provider and the service each construct their own `pgeocode.Nominatim`, so the
  GeoNames dataset is loaded twice. Its cached files (`US.txt`, `US-index.txt`) are
  ~2.8MB each on disk; the in-memory footprint after pandas parsing is larger and was
  not measured. A shared geocoding module would fix it.

- `Event.artist` is a single field, but JamBase sometimes flags multiple rank-1
  co-headliners. The tie is broken deterministically by performer identifier, which
  makes the choice stable but not meaningful. Representing it properly needs
  `headliners: list[str]`.

- Performer names can contain double-encoded UTF-8 from the API (e.g. "Janelle
  MonÃ¡e"). Passed through unmodified — a naive repair mangles genuinely accented
  names.

- Some events have a date-only `startDate` with no time component. These are flagged
  `time_tbd` and shown as "Time TBA" rather than midnight.

- `^\d{5}$` validates format, not existence, so a syntactically valid but nonexistent
  postal code is caught at geocoding rather than at validation. It also matches
  5-digit postal codes from other countries.

- When every provider fails, `/events` returns 200 with `events: []` and the provider
  in `sources_failed`, not a 502. Correct for fan-out isolation, misleading with a
  single provider — the frontend uses `sources_failed` to tell the two apart.

- US-only. International support needs a real geocoder behind the same resolution
  step.

- No cross-provider deduplication.
