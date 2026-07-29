"""
Verification service: assigns an initial verification status and
confidence score to a newly submitted report.

This is intentionally a lightweight heuristic layer for the MVP —
not a human review workflow. It exists as a clean seam where manual
review, ML-based fraud detection, or crowd-corroboration could be
plugged in later without touching the clustering or scoring engines,
which only ever consume `verification_status` / `verification_confidence`.
"""

from datetime import datetime, timedelta, timezone

from config import Config
from models import db
from models.report import CrimeReport, VerificationStatus


def assign_initial_verification(source: str) -> tuple[str, float]:
    """
    Determine the initial verification status and confidence for a
    newly submitted report based on its source.

    Args:
        source: One of the ReportSource constants.

    Returns:
        tuple[str, float]: (verification_status, verification_confidence)
    """
    from models.report import ReportSource

    if source == ReportSource.SEED:
        return VerificationStatus.UNVERIFIED, Config.SEED_BASELINE_CONFIDENCE

    return VerificationStatus.UNVERIFIED, Config.UNVERIFIED_BASELINE_CONFIDENCE


def is_likely_duplicate(latitude: float, longitude: float, crime_type: str,
                          window_minutes: int = 30, radius_degrees: float = 0.002) -> bool:
    """
    Cheap duplicate/spam check: has a very similar report (same crime
    type, near-identical coordinates) been submitted in the last
    `window_minutes`? Used to reject mass/duplicate submissions before
    they ever reach the database or clustering engine.

    Args:
        latitude, longitude: Coordinates of the incoming report.
        crime_type: Classified crime type of the incoming report.
        window_minutes: Time window to check for duplicates.
        radius_degrees: Approximate coordinate tolerance (~200m).

    Returns:
        bool: True if a near-identical recent report exists.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)

    existing = (
        db.session.query(CrimeReport)
        .filter(
            CrimeReport.crime_type == crime_type,
            CrimeReport.created_at >= cutoff,
            CrimeReport.latitude.between(latitude - radius_degrees, latitude + radius_degrees),
            CrimeReport.longitude.between(longitude - radius_degrees, longitude + radius_degrees),
        )
        .first()
    )
    return existing is not None


def verify_report(report: CrimeReport, approve: bool) -> CrimeReport:
    """
    Manually verify or reject a report (e.g. via an admin action).
    Updates confidence to the configured verified/rejected baseline.

    Args:
        report: The CrimeReport to update.
        approve: True to verify, False to reject.

    Returns:
        CrimeReport: The updated report (not yet committed).
    """
    if approve:
        report.verification_status = VerificationStatus.VERIFIED
        report.verification_confidence = Config.VERIFIED_CONFIDENCE
    else:
        report.verification_status = VerificationStatus.REJECTED
        report.verification_confidence = 0.0
        report.is_active = False

    return report