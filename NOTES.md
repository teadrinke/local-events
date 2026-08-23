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
