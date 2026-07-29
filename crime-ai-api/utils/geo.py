"""
Shared geographic utility functions used by clustering, scoring,
and geocoding services.
"""

import math

EARTH_RADIUS_METERS = 6_371_000.0

# Nigeria's approximate bounding box, used to sanity-check coordinates
# against spoofing / obviously invalid input.
NIGERIA_BOUNDS = {
    "min_lat": 4.0,
    "max_lat": 14.0,
    "min_lng": 2.5,
    "max_lng": 15.0,
}


def haversine_distance_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Compute the great-circle distance between two lat/lng points.

    Args:
        lat1, lng1: Coordinates of the first point in decimal degrees.
        lat2, lng2: Coordinates of the second point in decimal degrees.

    Returns:
        float: Distance in meters.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return EARTH_RADIUS_METERS * c


def is_within_nigeria(lat: float, lng: float) -> bool:
    """
    Sanity-check that a coordinate plausibly falls within Nigeria's
    bounding box. A cheap first line of defense against coordinate
    spoofing or client bugs sending (0, 0) or out-of-range values.

    Args:
        lat: Latitude in decimal degrees.
        lng: Longitude in decimal degrees.

    Returns:
        bool: True if within Nigeria's approximate bounding box.
    """
    return (
        NIGERIA_BOUNDS["min_lat"] <= lat <= NIGERIA_BOUNDS["max_lat"]
        and NIGERIA_BOUNDS["min_lng"] <= lng <= NIGERIA_BOUNDS["max_lng"]
    )