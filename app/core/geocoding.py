from functools import lru_cache

import pgeocode

from app.core.errors import GeocoderUnavailableError


@lru_cache(maxsize=1)
def geocoder() -> pgeocode.Nominatim:
    # pgeocode resolves postal codes against a GeoNames snapshot downloaded once
    # into a local cache, then works fully offline from that copy. The snapshot is
    # only as fresh as the installed pgeocode release, so very new or recently
    # reassigned postal codes may not resolve.
    #
    # Built on first query rather than at import or startup: the download is the
    # one part of this app that needs general network access, and it must not be
    # able to keep the process from booting. Failures are not cached, so a later
    # request retries the download.
    try:
        return pgeocode.Nominatim("us")
    except Exception as exc:
        raise GeocoderUnavailableError(
            "could not load the pgeocode GeoNames postal-code dataset "
            f"({type(exc).__name__}: {exc}). The first geocode needs network "
            "access to download it into ~/.cache/pgeocode; later runs read that "
            "cache and work offline."
        ) from exc
