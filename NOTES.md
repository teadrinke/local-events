# Notes

## Known limitations

- **Cached responses are shared and mutable.** `EventService` returns the cached
  `EventsResponse` by reference, so a caller that mutates `response.events` corrupts
  the cache entry for every subsequent hit until the TTL expires. Safe for the current
  route, which only serializes the response.

- **pgeocode bypasses the injected HTTP client.** On first use it downloads a GeoNames
  snapshot into a local cache (`~/.cache/pgeocode`), outside the shared
  `httpx.AsyncClient`. That request has no timeout, no retry, and no `ProviderError`
  translation, so a first run without network egress fails at geocoding rather than at
  the API call. Subsequent runs are fully offline.

- **Performer names can contain double-encoded UTF-8.** The API returns values such as
  `"Janelle MonÃ¡e"`. These are passed through unmodified: a blind
  `.encode('latin-1').decode('utf-8')` repair would mangle names that are legitimately
  accented, so the raw value is preferred over a guess.

- **Some events have date-only start times.** 4 of the 40 events in the sample response
  carry a `startDate` of the form `2026-08-22` with no time component. These become
  local midnight after timezone conversion rather than a real door time.

- **Cross-provider deduplication is not implemented.** The same show arriving from two
  sources appears twice, once per source id. See the comment in
  `app/services/event_service.py` for the intended matching strategy and for why
  same-show-different-night events must not be merged.

- **A total upstream failure still returns 200.** When every provider fails, `/events`
  responds `200` with `events: []` and the failed provider named in `sources_failed`,
  rather than a `502`. This follows from the service absorbing provider errors for
  fan-out isolation: correct when 1 of 10 providers is down, misleading when the only
  provider is down, since the response is otherwise indistinguishable from a genuine
  zero-result search unless the client inspects `sources_failed`. The frontend uses
  `sources_failed` to tell the two apart. A stricter version would return `502` when
  `sources_failed` covers every provider queried.

- **`^\d{5}$` validates format, not existence.** The route's pattern only checks that
  a postal code is five digits, so a well-formed but non-existent value such as `00000`
  passes validation and is caught later, at geocoding, when pgeocode fails to resolve
  it. That surfaces as `404` rather than the `422` a malformed value gets. Validating
  existence up front would mean consulting the same GeoNames dataset the geocoder
  already uses, so the check is left where the data lives.
