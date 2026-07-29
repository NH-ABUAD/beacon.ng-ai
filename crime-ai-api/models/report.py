"""
CrimeReport model — the atomic unit of the hotspot detection system.

Every submitted report (real or seed) is stored here after passing
through the existing Groq translation/classification pipeline.
Clusters are always derived from this table, never the other way
around.
"""

import uuid
from datetime import datetime, timezone

from models import db


class ReportSource:
    """String constants for report origin. Not a DB enum for portability."""
    USER_APP = "user_app"
    USSD = "ussd"
    CALL_CENTER = "call_center"
    SEED = "seed"
    PARTNER = "partner"

    ALL = {USER_APP, USSD, CALL_CENTER, SEED, PARTNER}


class VerificationStatus:
    """String constants for report verification state."""
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    REJECTED = "rejected"
    FLAGGED = "flagged"

    ALL = {UNVERIFIED, VERIFIED, REJECTED, FLAGGED}


def _generate_uuid() -> str:
    """Generate a UUID4 string for use as a primary key."""
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    """Return the current UTC time. Centralized for testability."""
    return datetime.now(timezone.utc)


class CrimeReport(db.Model):
    """A single crime report, real or seeded, after classification."""

    __tablename__ = "crime_reports"

    id = db.Column(db.String(36), primary_key=True, default=_generate_uuid)

    # --- Fields reused directly from the existing classification pipeline ---
    original_report = db.Column(db.Text, nullable=False)
    translated_report = db.Column(db.Text, nullable=False)
    detected_language = db.Column(db.String(64), nullable=False)
    crime_type = db.Column(db.String(64), nullable=False, index=True)
    severity = db.Column(db.String(16), nullable=False, index=True)
    recommended_dispatch_unit = db.Column(db.String(128), nullable=False)

    # --- Geography ---
    latitude = db.Column(db.Float, nullable=False, index=True)
    longitude = db.Column(db.Float, nullable=False, index=True)
    state = db.Column(db.String(64), nullable=False, index=True)
    lga = db.Column(db.String(128), nullable=True, index=True)
    location_text = db.Column(db.String(255), nullable=True)

    # --- Provenance & trust ---
    source = db.Column(db.String(32), nullable=False, default=ReportSource.USER_APP)
    verification_status = db.Column(
        db.String(16), nullable=False, default=VerificationStatus.UNVERIFIED, index=True
    )
    verification_confidence = db.Column(db.Float, nullable=False, default=0.5)

    # --- Lifecycle ---
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow, index=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)

    def age_in_days(self) -> float:
        """
        Compute the age of this report in days, used for time decay.

        Returns:
            float: Age in days (fractional).
        """
        created = self.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        delta = _utcnow() - created
        return delta.total_seconds() / 86400.0

    def to_dict(self) -> dict:
        """Serialize this report to a JSON-friendly dictionary."""
        return {
            "id": self.id,
            "original_report": self.original_report,
            "translated_report": self.translated_report,
            "detected_language": self.detected_language,
            "crime_type": self.crime_type,
            "severity": self.severity,
            "recommended_dispatch_unit": self.recommended_dispatch_unit,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "state": self.state,
            "lga": self.lga,
            "location_text": self.location_text,
            "source": self.source,
            "verification_status": self.verification_status,
            "verification_confidence": self.verification_confidence,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_active": self.is_active,
        }