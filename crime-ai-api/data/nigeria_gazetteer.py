"""
A small, hand-curated gazetteer of real, well-known Nigerian cities
and named areas within them (major markets, transit hubs, districts).

Used for two purposes:
1. Text-based geocoding fallback (services/geocoding_service.py) when a
   report arrives with a location description instead of GPS coordinates.
2. Generating geographically believable seed data (scripts/seed_data.py).

Coordinates are approximate area centers, not precise addresses.
density_weight is a relative multiplier used only for seed generation,
to bias more synthetic reports toward areas that are larger or busier
— it has no bearing on real report processing.
"""

NIGERIA_GAZETTEER = {
    "Lagos": {
        "state_center": (6.5244, 3.3792),
        "areas": {
            "Oshodi": (6.5560, 3.3450, 1.6),
            "Ajegunle": (6.4453, 3.3288, 1.4),
            "Mile 12": (6.5804, 3.3921, 1.3),
            "Agege": (6.6180, 3.3218, 1.2),
            "Ikeja": (6.6018, 3.3515, 1.1),
            "Surulere": (6.5010, 3.3583, 1.1),
            "Mushin": (6.5295, 3.3540, 1.3),
            "Apapa": (6.4488, 3.3591, 1.0),
        },
    },
    "Abuja": {
        "state_center": (9.0765, 7.3986),
        "areas": {
            "Wuse Market": (9.0631, 7.4816, 1.2),
            "Nyanya": (9.0167, 7.5333, 1.3),
            "Kubwa": (9.1500, 7.3333, 1.2),
            "Garki": (9.0333, 7.4833, 1.0),
            "Lugbe": (8.9833, 7.3667, 1.1),
        },
    },
    "Port Harcourt": {
        "state_center": (4.8156, 7.0498),
        "areas": {
            "Mile 1 Market": (4.7833, 7.0167, 1.4),
            "Diobu": (4.7975, 7.0128, 1.3),
            "Rumuokoro": (4.8681, 7.0356, 1.1),
            "Choba": (4.8981, 6.9089, 1.0),
        },
    },
    "Kano": {
        "state_center": (12.0022, 8.5920),
        "areas": {
            "Sabon Gari": (12.0089, 8.5264, 1.5),
            "Kurmi Market": (11.9993, 8.5150, 1.3),
            "Sharada": (11.9500, 8.4833, 1.0),
        },
    },
    "Ibadan": {
        "state_center": (7.3775, 3.9470),
        "areas": {
            "Dugbe Market": (7.3733, 3.8867, 1.4),
            "Bodija": (7.4333, 3.9000, 1.0),
            "Molete": (7.3667, 3.8917, 1.1),
        },
    },
    "Benin City": {
        "state_center": (6.3350, 5.6037),
        "areas": {
            "New Benin Market": (6.3400, 5.6250, 1.3),
            "Ring Road": (6.3333, 5.6167, 1.1),
            "Uselu": (6.3667, 5.5833, 1.0),
        },
    },
    "Aba": {
        "state_center": (5.1066, 7.3667),
        "areas": {
            "Ariaria Market": (5.1167, 7.3667, 1.5),
            "Ogbor Hill": (5.1000, 7.3833, 1.0),
        },
    },
    "Kaduna": {
        "state_center": (10.5105, 7.4165),
        "areas": {
            "Kaduna Central Market": (10.5222, 7.4383, 1.3),
            "Barnawa": (10.4667, 7.4333, 1.0),
        },
    },
    "Jos": {
        "state_center": (9.8965, 8.8583),
        "areas": {
            "Terminus Market": (9.9167, 8.8833, 1.2),
            "Bukuru": (9.7833, 8.8500, 1.0),
        },
    },
    "Onitsha": {
        "state_center": (6.1667, 6.7833),
        "areas": {
            "Onitsha Main Market": (6.1500, 6.7833, 1.5),
            "Fegge": (6.1333, 6.7833, 1.0),
        },
    },
}


def find_area(location_text: str):
    """
    Case-insensitive substring search for a named area across the
    gazetteer.

    Args:
        location_text: Free-text location description from a report.

    Returns:
        tuple | None: (state, area_name, lat, lng, density_weight) if
        found, else None.
    """
    if not location_text:
        return None

    needle = location_text.strip().lower()

    for state, payload in NIGERIA_GAZETTEER.items():
        if state.lower() in needle:
            for area_name, (lat, lng, weight) in payload["areas"].items():
                if area_name.lower() in needle:
                    return state, area_name, lat, lng, weight

        for area_name, (lat, lng, weight) in payload["areas"].items():
            if area_name.lower() in needle:
                return state, area_name, lat, lng, weight

    return None


def find_state_center(state_text: str):
    """
    Look up a state's approximate center coordinates by name.

    Args:
        state_text: A state name (case-insensitive, may be partial).

    Returns:
        tuple | None: (state, lat, lng) if matched, else None.
    """
    if not state_text:
        return None

    needle = state_text.strip().lower()
    for state, payload in NIGERIA_GAZETTEER.items():
        if state.lower() in needle or needle in state.lower():
            lat, lng = payload["state_center"]
            return state, lat, lng

    return None