class GeocoderUnavailableError(Exception):
    """The postal-code dataset could not be loaded.

    Lives in `core` rather than next to `ProviderError`: both `providers/` and
    `services/` geocode, so the type has to sit below both of them.

    Deliberately not a `ProviderError`. No event provider has failed here, and
    the two translate to different status codes at the route boundary.
    """
