"""
Clustering engine: groups active, non-expired crime reports into
geographic hotspots using DBSCAN with a haversine distance metric.

DBSCAN was chosen over k-means (requires pre-specifying cluster count
— wrong fit when hotspots should emerge organically) and over HDBSCAN
(adds complexity for density-adaptivity that per-state eps tuning
already covers at this scale). See the architecture document for the
full rationale.

Recomputation is scoped per state, not global, so a change in one
state doesn't force recalculating the whole country.
"""

from datetime import datetime, timedelta, timezone

import numpy as np
from sklearn.cluster import DBSCAN

from config import Config
from models import db
from models.cluster import Cluster, ClusterMembership, RiskScoreLog
from models.report import CrimeReport
from services.risk_service import (
    compute_cluster_score,
    crime_breakdown,
    report_weight,
    score_to_risk_level,
)
from utils.geo import EARTH_RADIUS_METERS, haversine_distance_meters


def _active_reports_for_state(state: str) -> list[CrimeReport]:
    """
    Fetch all active, non-expired, non-rejected reports for a state
    that are within the configured maximum age window.

    Args:
        state: The Nigerian state to scope the query to.

    Returns:
        list[CrimeReport]: Eligible reports for clustering.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=Config.MAX_REPORT_AGE_DAYS)

    return (
        db.session.query(CrimeReport)
        .filter(
            CrimeReport.state == state,
            CrimeReport.is_active.is_(True),
            CrimeReport.verification_status != "rejected",
            CrimeReport.created_at >= cutoff,
        )
        .all()
    )


def _eps_radians_for_state(state: str) -> float:
    """
    Resolve the DBSCAN eps parameter (neighborhood radius) for a
    state, in radians, as required by sklearn's haversine metric.

    Args:
        state: The Nigerian state.

    Returns:
        float: eps in radians.
    """
    eps_meters = Config.CLUSTER_EPS_METERS_BY_STATE.get(
        state, Config.CLUSTER_EPS_METERS_DEFAULT
    )
    return eps_meters / EARTH_RADIUS_METERS


def recompute_clusters_for_state(state: str) -> list[Cluster]:
    """
    Recompute all hotspot clusters for a given state from its current
    active reports, replacing the previous "current" snapshot.

    Steps:
    1. Fetch eligible reports.
    2. Run DBSCAN (haversine metric) with per-report sample weights
       derived from time decay × verification confidence, so recent,
       verified reports contribute more to density than old or
       unverified ones.
    3. For each resulting cluster, compute centroid, radius, risk
       score, risk level, and crime breakdown.
    4. Retire the previous "current" clusters for this state and
       persist the new snapshot, logging each score to RiskScoreLog.

    Args:
        state: The Nigerian state to recompute.

    Returns:
        list[Cluster]: The newly computed, persisted clusters.
    """
    reports = _active_reports_for_state(state)

    if len(reports) < Config.CLUSTER_MIN_SAMPLES:
        _retire_current_clusters(state)
        db.session.commit()
        return []

    coords_radians = np.radians(
        np.array([[r.latitude, r.longitude] for r in reports])
    )
    sample_weights = np.array([report_weight(r) for r in reports])

    eps = _eps_radians_for_state(state)
    labels = DBSCAN(
        eps=eps,
        min_samples=Config.CLUSTER_MIN_SAMPLES,
        metric="haversine",
        algorithm="ball_tree",
    ).fit_predict(coords_radians, sample_weight=sample_weights)

    _retire_current_clusters(state)

    new_clusters = []
    unique_labels = sorted(set(labels) - {-1})  # -1 is DBSCAN's "noise" label

    for label in unique_labels:
        member_indices = [i for i, l in enumerate(labels) if l == label]
        member_reports = [reports[i] for i in member_indices]

        cluster = _build_cluster(state, member_reports)
        db.session.add(cluster)
        db.session.flush()  # assign cluster.id before creating memberships

        for report in member_reports:
            distance = haversine_distance_meters(
                cluster.center_lat, cluster.center_lng, report.latitude, report.longitude
            )
            db.session.add(
                ClusterMembership(
                    cluster_id=cluster.id,
                    report_id=report.id,
                    distance_from_center_meters=distance,
                )
            )

        db.session.add(
            RiskScoreLog(
                cluster_id=cluster.id,
                score=cluster.risk_score,
                risk_level=cluster.risk_level,
                report_count_at_time=cluster.report_count,
            )
        )

        new_clusters.append(cluster)

    db.session.commit()
    return new_clusters


def _build_cluster(state: str, member_reports: list[CrimeReport]) -> Cluster:
    """
    Construct a Cluster row (not yet persisted) from its member reports.

    Args:
        state: The state this cluster belongs to.
        member_reports: CrimeReport rows assigned to this cluster.

    Returns:
        Cluster: A new, unsaved Cluster instance.
    """
    center_lat = sum(r.latitude for r in member_reports) / len(member_reports)
    center_lng = sum(r.longitude for r in member_reports) / len(member_reports)

    radius = max(
        haversine_distance_meters(center_lat, center_lng, r.latitude, r.longitude)
        for r in member_reports
    )

    score = compute_cluster_score(member_reports)
    risk_level = score_to_risk_level(score)

    lga_counts: dict = {}
    for r in member_reports:
        if r.lga:
            lga_counts[r.lga] = lga_counts.get(r.lga, 0) + 1
    dominant_lga = max(lga_counts, key=lga_counts.get) if lga_counts else None

    return Cluster(
        center_lat=center_lat,
        center_lng=center_lng,
        radius_meters=max(radius, 50.0),  # floor so single tight clusters aren't a 0m dot
        risk_level=risk_level,
        risk_score=score,
        report_count=len(member_reports),
        crime_breakdown=crime_breakdown(member_reports),
        state=state,
        lga=dominant_lga,
        is_current=True,
    )


def _retire_current_clusters(state: str) -> None:
    """
    Mark all currently-active clusters for a state as no longer
    current, ahead of inserting a fresh snapshot. Rows are kept (not
    deleted) so RiskScoreLog history remains intact.

    Args:
        state: The state whose clusters should be retired.
    """
    db.session.query(Cluster).filter(
        Cluster.state == state, Cluster.is_current.is_(True)
    ).update({"is_current": False})


def recompute_all_clusters() -> None:
    """
    Recompute clusters for every state that currently has active
    reports. Used by the scheduled safety-net job and by the seed
    data CLI command after bulk-loading reports.
    """
    states = [
        row[0]
        for row in db.session.query(CrimeReport.state)
        .filter(CrimeReport.is_active.is_(True))
        .distinct()
        .all()
    ]
    for state in states:
        recompute_clusters_for_state(state)