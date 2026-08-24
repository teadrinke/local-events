# Writeup

## Technology choices

FastAPI with `httpx` on the async side, Pydantic for models and validation,
`cachetools` for an in-memory TTL cache, `pgeocode` for offline postal-code
resolution, and a single vanilla HTML/JS file for the frontend.

The async client is the one choice worth defending: `requests` would block
the event loop, which forecloses the parallel provider fan-out this design
is built around. Everything else is the boring default.

The frontend is deliberately not React. A build step and a second process
would have added setup friction and a longer README for zero benefit on a
brief that explicitly deprioritizes visual polish. The time went into the
provider abstraction instead.

## Backend / API design

Four layers, with dependencies pointing one direction:

    routes → services → providers → models

`models/` imports nothing from the app. `providers/` and `services/` import
`models/`. Nothing under `app/services/` or `app/api/` references JamBase, and
`main.py` is the only file that imports the provider. Config holds the
vendor-named settings, as it should.

One edge crosses that diagram deliberately: `routes/` imports the provider
*error contract* from `providers/base.py`, because it is the layer that
translates `ProviderError` and `LocationNotFoundError` into 502 and 404. It
depends on the contract, never on a provider implementation.

The design centers on one idea: **every JamBase-specific detail is trapped
inside `providers/jambase.py`** — its parameter names, its nested JSON, its
naive timestamps, its six-seller offer arrays. Everything above that file
speaks only the normalized `Event` model.

`EventQuery` and `Event` are the two ends of that vocabulary. The query
holds a postal code because that's the user's language; the provider
translates it to the lat/long JamBase actually accepts. A future provider
that takes postal codes directly passes it through unchanged.

The response is an envelope rather than a bare list:

    {"events": [...], "count": n,
     "sources_queried": [...], "sources_failed": [...]}

With one provider `sources_failed` is always empty. It exists now because
adding it later would be a breaking change, and because the frontend already
uses it — see "biggest limitation" below.

Reliability lives at the provider boundary: a timeout on every call, retries
on 5xx and timeouts only (never 4xx — a bad request won't fix itself), and
`ProviderError` raised in place of any `httpx` exception, so transport
details never escape the layer that owns them. A malformed individual event
is logged and skipped rather than fatal; one bad record shouldn't cost the
user the other thirty-nine.

## API investigation

The geo parameters were determined empirically rather than from docs. JamBase
v3 rejects `postalCode` with a 400 (`Unknown parameter`), so the obvious
design didn't survive contact with the API. Testing each filter from the same
origin:

    postalCode                       → 400
    geoLatitude/Longitude + radius   → 783 / 2,076 / 3,119 at 5 / 25 / 100 mi
    geoCityId                        → 917
    geoMetroId                       → 3,736

Lat/long won because the radius genuinely filters and because resolving the
user's ZIP to coordinates is needed for distance calculation anyway — one
resolution serves both.

## UI design decisions

The card answers the two questions that actually gate a decision: **can I get
there**, and **is it soon**. That's why distance and a relative date header
("Today", "Tomorrow", "Sat, Aug 29") are on the card at all, and why events
are grouped by day rather than listed flat — people plan by day, not by
scrolling a stream.

Price range appears when the source publishes it, genres as small tags, and
a ticket link. Everything optional degrades silently; the UI never renders
`null`.

Five states are handled explicitly: empty, loading, results, no-results, and
error. The last two are the interesting pair — they are not the same thing,
and telling them apart requires reading `sources_failed`, not the status code.

## Tradeoffs made to keep it simple

- **No database.** There is no write path and no cross-restart requirement,
  so an in-memory TTL cache does the job a table would.
- **Straight-line distance, not drive time.** Haversine is free math;
  routing needs another API key and a call per search. The
  `DistanceCalculator` interface takes a *list* of destinations and returns a
  `DistanceResult` with an optional `duration_minutes`, so a routing
  implementation drops in with one batched call rather than forty.
- **Canceled events filtered out** rather than badged. A product call: a
  discovery app showing canceled shows is worse than one showing fewer.
- **Cache size is a module constant**, not a setting. Not every number needs
  to be tunable.
- **No auth, no Docker, no pagination.** Out of scope at this size.

## What I'd change with more time

- A shared `geocoding.py`. The provider and the service each construct their
  own `pgeocode.Nominatim`, loading the same dataset twice.
- `headliners: list[str]`. JamBase sometimes flags multiple rank-1
  co-headliners; a single `artist` field structurally cannot represent that.
  The tie is currently broken by performer identifier, which is stable but
  not meaningful.
- Price comparison. `external_ids` already holds ticketing links for
  SeatGeek, StubHub, Vivid Seats and others per event — showing them side by
  side is close to free and is the most obvious product win available.
- Cross-provider deduplication, and international support behind the same
  location-resolution seam.

## How I used AI

Claude Code, driven one phase at a time with explicit scope limits ("two
files only, no services, no routes") rather than one-shotting the project.
Each phase was reviewed before the next began, and every phase was verified
against something real — the saved fixture, the live API, or a test — rather
than accepted on the model's description of its own work.

The most useful pattern was asking it to check my assumptions instead of
implementing them. Before writing the normalization code I told it to survey
the saved fixture and report where the actual data differed from my spec.

A related pattern was surfacing ambiguity rather than resolving it silently.
`external_ids` is keyed by seller, but nothing in the API supplies a
partner-side ID — the only identifiers available are JamBase's own, and the
real Ticketmaster ID exists only inside an affiliate URL's query string. Told
to build the field, it implemented the defensible version, flagged that the
value was ambiguous for a field with that name, and laid out the options:
store the offer URL, or parse partner IDs per seller, with a recommendation
against the parsing as brittle. I chose seller links. The decision was mine;
what the tool contributed was noticing the field could not mean what its name
implied.

## Something AI got wrong that I corrected

Two examples, deliberately including one where it was right and I wasn't.

**Corrected.** Early on it guessed a base URL, called it, received a
well-formed 403, and concluded the URL was correct — reasoning that the host
had echoed the query parameters back, so the endpoint must be real. It
wasn't: the legacy v1 API and the v3 Data API are different products, and my
key belonged to the latter. The failure mode is worth naming — *a plausible
error from the wrong service reads exactly like a validated one*. I confirmed
the base URL against the vendor's documentation instead of inferring it from
response shape.

**Accepted.** My field-mapping spec was written from a skim of the API
response, and it found five places the spec contradicted the data — most
importantly that primary ticketing offers frequently carry no price at all,
which I had asserted was true only of secondary resellers. Coding to my
description would have shipped a normalizer that silently dropped prices. It
also overrode my `datetime` annotation with Pydantic's `AwareDatetime`, on
the grounds that my "timezone-aware" comment was documentation nothing
enforced. It was right; JamBase returns naive local timestamps with the zone
on a separate venue field, and the stricter type forces the provider to
resolve it at parse time rather than letting the bug surface as mis-sorted
events.

## Biggest technical limitation

When every provider fails, `/events` returns **200 with an empty list**, not
a 502.

This follows directly from absorbing provider errors into `sources_failed`.
That absorption is correct fan-out behavior — one dead provider out of ten
shouldn't fail the search — but with a single provider it makes a total
outage indistinguishable from a genuine zero-result search at the status-code
level. The envelope carries enough information for a client to tell them
apart, and the frontend does exactly that, but a consumer reading only the
status code would be misled.

The same taxonomy problem bit once already, in a case I did fix. Manual
testing of `00000` showed the UI reporting an upstream outage when the postal
code simply didn't geocode. Every layer had behaved as designed; the error
classification was wrong. `LocationNotFoundError` now propagates to a 404
rather than being absorbed, because fan-out isolation exists to survive
provider outages and shouldn't mask client errors.

## Evolving to ten providers

The seam is already there. Adding a source is one new file implementing
`EventProvider` and one line in the registry in `main.py` — routes, models,
service, and frontend are untouched. That claim is verifiable rather than
asserted: there is no reference to "jambase" anywhere under `app/services/`
or `app/api/`.

What actually gets hard is not adding them.

**Fan-out and partial failure.** Ten sequential calls at ~800ms is eight
seconds, so `asyncio.gather(return_exceptions=True)` — which the service
already uses — becomes load-bearing. The response must carry partial results
with the failures named, which is what the envelope is for.

**Deduplication, which is the genuinely hard part.** The same show appears on
three platforms under three IDs. Matching naively on artist + venue + date
breaks on name variants, venue aliases, and timezone-shifted timestamps.
The better signal is already in the data: JamBase publishes third-party
ticketing links per event, so two providers describing the same show
frequently share a Ticketmaster or SeatGeek URL. Match on shared external IDs
first, fall back to fuzzy matching only where there is no overlap. Note that
same-show-different-night events must *not* be merged — a residency is
several distinct events.

**Field coverage variance.** Providers disagree about what they publish.
`Event` is already almost entirely optional fields for this reason, and the
UI degrades silently rather than rendering gaps.

## Self-assessment

**Code quality: B+.** Layering is clean and enforced, errors are typed and
translated at boundaries, and the tests run offline in under a second. Points
off for the duplicated geocoder instances and for a cached response that is
returned by reference and mutable — harmless with the current route, but a
latent trap.

**Work product: A-.** Complete and working end to end, with a README that
gets a reviewer running in two minutes and a limitations list I wrote before
being asked for one. The UI is functional and clean but deliberately plain.

**Extensibility: A-.** Adding a provider is a genuinely additive change, and
the same seam pattern is applied twice — once for providers, once for
distance calculation, anticipating drive time. Not an A because the parts I
know will be hard at ten providers, dedup in particular, are documented
rather than built.

## Time spent

~2.5 hours of implementation, plus design work beforehand and this document
afterward.
