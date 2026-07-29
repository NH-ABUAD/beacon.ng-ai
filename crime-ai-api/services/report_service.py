"""
Report submission orchestration service.

Wires the existing translation/classification pipeline
(services/groq_service.py, untouched) together with the new
verification, geocoding, persistence, and clustering layers.
This is the only new code that sits "in front of" the existing
Groq pipeline — the pipeline itself is reused as-is.
"""

from datetime import datetime, timedelta, timezone

from config import Config
from models import db
from models.report import CrimeReport, ReportSource
from services.geocoding_service import get_geocoder
from services.groq_service import classify_crime_report
from services.verification_service import assign_initial_verification, is_likely_duplicate
from services.cluster_service import recompute_clusters_for_state
from utils.geo import is_within_nigeria


class ReportSubmissionError(ValueError):
    """Raised for validation failures during report submission."""


def submit_report(
    description: str,
    latitude: float | None = None,
    longitude: float | None = None,
    location_text: str | None = None,
    state_hint: str | None = None,
    source: str = ReportSource.USER_APP,
) -> dict:
    """
    Full pipeline for a new crime report: classify (existing Groq
    pipeline), resolve location (GPS or geocoded text), verify,
    persist, and trigger cluster recomputation for the affected state.

    Args:
        description: Raw report text, any supported language.
        latitude: GPS latitude, if the client supplied coordinates.
        longitude: GPS longitude, if the client supplied coordinates.
        location_text: Free-text location, used if coordinates weren't
            supplied (e.g. USSD/call-center intake).
        state_hint: Optional state name to disambiguate geocoding.
        source: One of the ReportSource constants.

    Returns:
        dict: The persisted report's serialized representation, plus
        a note on whether clustering was triggered.

    Raises:
        ReportSubmissionError: If location cannot be resolved, or
            coordinates fall outside Nigeria, or the report is a
            likely duplicate.
        RuntimeError / ValueError: Propagated from the existing Groq
            classification pipeline on failure.
    """
    classification = classify_crime_report(description)

    resolved_lat, resolved_lng, resolved_state, resolved_lga = _resolve_location(
        latitude, longitude, location_text, state_hint
    )

    if not is_within_nigeria(resolved_lat, resolved_lng):
        raise ReportSubmissionError(
            "Resolved coordinates fall outside Nigeria's expected bounds."
        )

    if is_likely_duplicate(resolved_lat, resolved_lng, classification["crime_type"]):
        raise ReportSubmissionError(
            "A near-identical report at this location was submitted very recently."
        )

    verification_status, verification_confidence = assign_initial_verification(source)

    report = CrimeReport(
        original_report=classification["original_report"],
        translated_report=classification["translated_report"],
        detected_language=classification["detected_language"],
        crime_type=classification["crime_type"],
        severity=classification["severity"],
        recommended_dispatch_unit=classification["recommended_dispatch_unit"],
        latitude=resolved_lat,
        longitude=resolved_lng,
        state=resolved_state,
        lga=resolved_lga,
        location_text=location_text,
        source=source,
        verification_status=verification_status,
        verification_confidence=verification_confidence,
        expires_at=datetime.now(timezone.utc) + timedelta(days=Config.MAX_REPORT_AGE_DAYS),
    )

    db.session.add(report)
    db.session.commit()

    # Synchronous for simplicity at current expected volume. At higher
    # throughput, this should be pushed to a background job queue
    # (see architecture doc §12) instead of blocking the request.
    recompute_clusters_for_state(resolved_state)

    result = report.to_dict()
    result["clusters_recomputed_for_state"] = resolved_state
    return result


def _resolve_location(
    latitude: float | None,
    longitude: float | None,
    location_text: str | None,
    state_hint: str | None,
) -> tuple[float, float, str, str | None]:
    """
    Resolve a report's coordinates and administrative area, either
    directly from supplied GPS coordinates or via geocoding of free
    text.

    Returns:
        tuple: (latitude, longitude, state, lga)

    Raises:
        ReportSubmissionError: If neither coordinates nor a resolvable
            location_text were supplied.
    """
    if latitude is not None and longitude is not None:
        state = state_hint or "Unknown"
        return latitude, longitude, state, None

    if location_text:
        geocoder = get_geocoder()
        result = geocoder.geocode(location_text, state_hint=state_hint)
        if result is None:
            raise ReportSubmissionError(
                f"Could not resolve location from text: '{location_text}'."
            )
        return result.latitude, result.longitude, result.state, result.lga

    raise ReportSubmissionError(
        "Either (latitude, longitude) or location_text must be provided."
    )