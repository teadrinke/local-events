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

- Canceled events are filtered out. A product decision, not a data limitation; a
  stricter version would surface them with a status badge.

- Cache maxsize is a module constant rather than a setting. Not every number needs to
  be tunable.

- The provider and the service share one `pgeocode.Nominatim` from
  `core/geocoding.py`, built lazily behind an `lru_cache(maxsize=1)` on the first
  geocode. Two reasons for lazy over eager: constructing it downloads the GeoNames
  dataset, and the service is constructed in the app lifespan, so an eager build turned
  a failed download into a boot failure, with `/health` and `/docs` never coming up.
  Sharing it also stops the dataset being loaded twice (cached files `US.txt` and
  `US-index.txt`, ~2.7MB each on disk and ~5.4MB for the pair; the in-memory footprint
  after pandas parsing is larger and was not measured).

- The geocoder lives in `core/`, not in `providers/` or `services/`, because both of
  them geocode: the provider resolves the query postal code, the service resolves the
  same origin for distances. Putting it in either package would have made the other
  import upwards. `GeocoderUnavailableError` sits in `core/errors.py` for the same
  reason, and deliberately does not subclass `ProviderError`: no provider has failed.

- A geocoder failure returns **503** from both call sites. It is re-raised out of the
  provider fan-out rather than absorbed into `sources_failed`, on the same reasoning
  as `LocationNotFoundError`: fan-out isolation exists to survive one provider dying,
  and a missing postal-code dataset takes every provider down at once, so there is
  nothing to isolate. Absorbing it would answer 200 for a search that could not have
  run. 503 rather than the existing 502 keeps one meaning per code: 502 is the event
  provider, 503 is the local postal-code dependency. The failure is not cached, so the
  next request retries the download.

## Known limitations

- Cached `EventsResponse` objects are returned by reference and are mutable; a caller
  mutating `response.events` corrupts the cache entry until TTL expiry. Harmless for
  the current route, which only serializes.

- pgeocode downloads a GeoNames snapshot on first use, outside the injected httpx
  client, so it has no timeout or retry handling. A first run on a restricted network
  fails at geocoding rather than at the API boundary.

- `Event.artist` is a single field, but JamBase sometimes flags multiple rank-1
  co-headliners. The tie is broken deterministically by performer identifier, which
  makes the choice stable but not meaningful. Representing it properly needs
  `headliners: list[str]`.

- Performer names can contain double-encoded UTF-8 from the API (e.g. "Janelle
  MonÃ¡e"). Passed through unmodified: a naive repair mangles genuinely accented
  names.

- Some events have a date-only `startDate` with no time component. These are flagged
  `time_tbd` and shown as "Time TBA" rather than midnight.

- `^\d{5}$` validates format, not existence, so a syntactically valid but nonexistent
  postal code is caught at geocoding rather than at validation. It also matches
  5-digit postal codes from other countries.

- When every provider fails, `/events` returns 200 with `events: []` and the provider
  in `sources_failed`, not a 502. Correct for fan-out isolation, misleading with a
  single provider; the frontend uses `sources_failed` to tell the two apart.

- US-only. International support needs a real geocoder behind the same resolution
  step.

- No cross-provider deduplication.
