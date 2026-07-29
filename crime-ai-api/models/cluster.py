"""
Cluster, ClusterMembership, and RiskScoreLog models.

Clusters are *derived* snapshots recomputed by the cluster engine —
never hand-edited. Each recomputation for a region creates a new
"current" snapshot and retires the previous one, while RiskScoreLog
preserves history for trend analysis.
"""

import uuid
from datetime import datetime, timezone

from models import db


class RiskLevel:
    """String constants for cluster risk classification."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


def _generate_uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Cluster(db.Model):
    """A detected hotspot — a density-based grouping of crime reports."""

    __tablename__ = "clusters"

    id = db.Column(db.String(36), primary_key=True, default=_generate_uuid)

    center_lat = db.Column(db.Float, nullable=False)
    center_lng = db.Column(db.Float, nullable=False)
    radius_meters = db.Column(db.Float, nullable=False)

    risk_level = db.Column(db.String(16), nullable=False, index=True)
    risk_score = db.Column(db.Float, nullable=False)

    report_count = db.Column(db.Integer, nullable=False)
    crime_breakdown = db.Column(db.JSON, nullable=False, default=dict)

    state = db.Column(db.String(64), nullable=False, index=True)
    lga = db.Column(db.String(128), nullable=True, index=True)

    computed_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    is_current = db.Column(db.Boolean, nullable=False, default=True, index=True)

    memberships = db.relationship(
        "ClusterMembership", backref="cluster", cascade="all, delete-orphan"
    )

    def to_geojson_feature(self) -> dict:
        """
        Serialize this cluster as a GeoJSON Feature, ready for Leaflet
        or Mapbox GL consumption without further transformation.

        Returns:
            dict: A GeoJSON Feature object.
        """
        return {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [self.center_lng, self.center_lat],
            },
            "properties": {
                "cluster_id": self.id,
                "risk_level": self.risk_level,
                "score": round(self.risk_score, 2),
                "radius_meters": round(self.radius_meters, 1),
                "report_count": self.report_count,
                "crime_breakdown": self.crime_breakdown,
                "state": self.state,
                "lga": self.lga,
                "computed_at": self.computed_at.isoformat(),
            },
        }


class ClusterMembership(db.Model):
    """Join table linking a cluster snapshot to its member reports."""

    __tablename__ = "cluster_memberships"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    cluster_id = db.Column(
        db.String(36), db.ForeignKey("clusters.id"), nullable=False, index=True
    )
    report_id = db.Column(
        db.String(36), db.ForeignKey("crime_reports.id"), nullable=False, index=True
    )
    distance_from_center_meters = db.Column(db.Float, nullable=False)


class RiskScoreLog(db.Model):
    """
    Append-only audit trail of risk score changes for a geographic
    cluster identity over time. Powers /api/hotspots/{id}/history and
    trend analysis.
    """

    __tablename__ = "risk_score_logs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    cluster_id = db.Column(
        db.String(36), db.ForeignKey("clusters.id"), nullable=False, index=True
    )
    score = db.Column(db.Float, nullable=False)
    risk_level = db.Column(db.String(16), nullable=False)
    report_count_at_time = db.Column(db.Integer, nullable=False)
    computed_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    def to_dict(self) -> dict:
        """Serialize this log entry to a JSON-friendly dictionary."""
        return {
            "score": round(self.score, 2),
            "risk_level": self.risk_level,
            "report_count": self.report_count_at_time,
            "computed_at": self.computed_at.isoformat(),
        }