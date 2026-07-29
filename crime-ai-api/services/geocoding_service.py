"""
Geocoding abstraction: converts free-text Nigerian locations into
coordinates. Designed as a thin provider interface so a future
provider (e.g. OpenStreetMap Nominatim) can be added without changing
any calling code.
"""

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass

from data.nigeria_gazetteer import find_area, find_state_center


@dataclass
class GeocodeResult:
    """Result of a geocoding attempt."""
    latitude: float
    longitude: float
    state: str
    lga: str | None
    confidence: float


class GeocodingProvider(ABC):
    """Abstract base for location-text-to-coordinates providers."""

    @abstractmethod
    def geocode(self, location_text: str, state_hint: str | None = None) -> GeocodeResult | None:
        """Attempt to geocode free text into coordinates."""
        raise NotImplementedError


class NigeriaGazetteerProvider(GeocodingProvider):
    """
    Offline geocoding against the hand-curated gazetteer of well-known
    Nigerian areas. No external dependency, no API key, works for the
    ten seeded cities and their major districts out of the box.

    Ambiguous or unmatched text falls back to the state's centroid
    (lower confidence) rather than guessing a precise point, so bad
    geocoding doesn't quietly distort a cluster's location.
    """

    def geocode(self, location_text: str, state_hint: str | None = None) -> GeocodeResult | None:
        area_match = find_area(location_text)
        if area_match:
            state, area_name, lat, lng, _weight = area_match
            lat, lng = _jitter(lat, lng, spread_meters=150)
            return GeocodeResult(
                latitude=lat, longitude=lng, state=state, lga=area_name, confidence=0.9
            )

        state_match = find_state_center(state_hint) if state_hint else None
        if not state_match:
            state_match = find_state_center(location_text)

        if state_match:
            state, lat, lng = state_match
            lat, lng = _jitter(lat, lng, spread_meters=2000)
            return GeocodeResult(
                latitude=lat, longitude=lng, state=state, lga=None, confidence=0.4
            )

        return None


def _jitter(lat: float, lng: float, spread_meters: float) -> tuple[float, float]:
    """
    Apply a small random offset to a coordinate, used to avoid
    stacking every geocoded report from the same area on one exact
    point. Not cryptographically random — purely for visual/clustering
    realism.

    Args:
        lat, lng: Base coordinates.
        spread_meters: Maximum jitter radius in meters.

    Returns:
        tuple[float, float]: Jittered (lat, lng).
    """
    meters_per_degree_lat = 111_320.0
    d_lat = random.uniform(-spread_meters, spread_meters) / meters_per_degree_lat
    d_lng = random.uniform(-spread_meters, spread_meters) / (
        111_320.0 * max(0.1, abs(_cos_deg(lat)))
    )
    return lat + d_lat, lng + d_lng


def _cos_deg(degrees: float) -> float:
    import math
    return math.cos(math.radians(degrees))


def get_geocoder() -> GeocodingProvider:
    """
    Factory returning the active geocoding provider. Swapping in a
    future provider (e.g. Nominatim) only requires changing this
    function, not any calling code.

    Returns:
        GeocodingProvider: The configured provider instance.
    """
    return NigeriaGazetteerProvider()