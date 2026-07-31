# routes/hotspots.py
"""
Route handlers for hotspot querying: GeoJSON cluster output, cluster
detail, cluster history, aggregate statistics, and a raw heatmap
point feed. All read-only — clusters are only ever written by
services/cluster_service.py.
"""

from flask import Blueprint, jsonify, request

from models import db
from models.cluster import Cluster, RiskScoreLog
from models.report import CrimeReport
from services.risk_service import report_weight
from utils.response import error_response
from flasgger import swag_from

hotspots_bp = Blueprint("hotspots", __name__)


@swag_from('../docs/list_hotspots.yml')
@hotspots_bp.route("/hotspots", methods=["GET"])
def list_hotspots():
    """
    Return current hotspot clusters as a GeoJSON FeatureCollection.

    Query params:
        state: filter by state name
        lga: filter by LGA name
        risk_level: filter by 'low' | 'medium' | 'high'

    Returns:
        GeoJSON FeatureCollection, directly usable by Leaflet/Mapbox.
    """
    query = db.session.query(Cluster).filter(Cluster.is_current.is_(True))

    state = request.args.get("state")
    lga = request.args.get("lga")
    risk_level = request.args.get("risk_level")

    if state:
        query = query.filter(Cluster.state == state)
    if lga:
        query = query.filter(Cluster.lga == lga)
    if risk_level:
        query = query.filter(Cluster.risk_level == risk_level)

    clusters = query.all()

    return jsonify(
        {
            "type": "FeatureCollection",
            "features": [c.to_geojson_feature() for c in clusters],
        }
    ), 200

@swag_from('../docs/get_hotspot.yml')
@hotspots_bp.route("/hotspots/<cluster_id>", methods=["GET"])
def get_hotspot(cluster_id: str):
    """
    Return a single cluster as a GeoJSON Feature.

    Returns:
        JSON response with the cluster feature, or a 404 if not found.
    """
    cluster = db.session.get(Cluster, cluster_id)
    if cluster is None:
        return error_response("Cluster not found.", 404)

    return jsonify(cluster.to_geojson_feature()), 200


@swag_from('../docs/get_hotspot_history.yml')
@hotspots_bp.route("/hotspots/<cluster_id>/history", methods=["GET"])
def get_hotspot_history(cluster_id: str):
    """
    Return the score history for a cluster over time, sourced from
    RiskScoreLog.

    Returns:
        JSON list of historical score entries, oldest first.
    """
    cluster = db.session.get(Cluster, cluster_id)
    if cluster is None:
        return error_response("Cluster not found.", 404)

    logs = (
        db.session.query(RiskScoreLog)
        .filter(RiskScoreLog.cluster_id == cluster_id)
        .order_by(RiskScoreLog.computed_at.asc())
        .all()
    )

    return jsonify({"cluster_id": cluster_id, "history": [log.to_dict() for log in logs]}), 200


@swag_from('../docs/hotspot_stats.yml')
@hotspots_bp.route("/hotspots/stats", methods=["GET"])
def hotspot_stats():
    """
    Return aggregate hotspot statistics: total current clusters and a
    breakdown by risk level and by state.

    Returns:
        JSON summary object.
    """
    clusters = db.session.query(Cluster).filter(Cluster.is_current.is_(True)).all()

    by_risk_level: dict = {"low": 0, "medium": 0, "high": 0}
    by_state: dict = {}

    for c in clusters:
        by_risk_level[c.risk_level] = by_risk_level.get(c.risk_level, 0) + 1
        by_state[c.state] = by_state.get(c.state, 0) + 1

    return jsonify(
        {
            "total_clusters": len(clusters),
            "by_risk_level": by_risk_level,
            "by_state": by_state,
        }
    ), 200

@swag_from('../docs/heatmap.yml')
@hotspots_bp.route("/heatmap", methods=["GET"])
def heatmap():
    """
    Return raw weighted report points for a smooth heatmap layer, as
    an alternative to discrete clusters. Weight = severity × time
    decay × verification confidence, matching the same formula used
    for clustering, so the heatmap and the cluster view stay visually
    consistent.

    Query params:
        state: filter by state name

    Returns:
        JSON list of {latitude, longitude, weight} points.
    """
    query = db.session.query(CrimeReport).filter(CrimeReport.is_active.is_(True))

    state = request.args.get("state")
    if state:
        query = query.filter(CrimeReport.state == state)

    reports = query.all()

    points = [
        {
            "latitude": r.latitude,
            "longitude": r.longitude,
            "weight": round(report_weight(r), 3),
        }
        for r in reports
    ]

    return jsonify({"points": points}), 200
