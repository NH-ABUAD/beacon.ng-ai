"""
Risk scoring engine: converts a set of crime reports belonging to a
cluster into a single weighted risk score, and maps that score onto
a Low / Medium / High risk level.

All weights and thresholds are read from Config — nothing here is a
hardcoded magic number, so tuning the formula never requires a code
change.
"""

import math

from config import Config
from models.cluster import RiskLevel
from models.report import CrimeReport


def time_decay_weight(age_days: float) -> float:
    """
    Exponential decay weight for a report's contribution to a
    cluster's score, based on its age.

    decay(age) = e^(-lambda * age_days), where lambda is derived from
    the configured half-life so that at `DECAY_HALF_LIFE_DAYS` old,
    a report contributes exactly half its original weight.

    Args:
        age_days: Age of the report in days.

    Returns:
        float: A weight in (0, 1].
    """
    half_life = Config.DECAY_HALF_LIFE_DAYS
    decay_lambda = math.log(2) / half_life
    return math.exp(-decay_lambda * age_days)


def report_weight(report: CrimeReport) -> float:
    """
    Compute a single report's weighted contribution to its cluster's
    risk score: severity weight × time decay × verification confidence.

    Args:
        report: The CrimeReport to weigh.

    Returns:
        float: The report's weighted contribution.
    """
    severity_weight = Config.SEVERITY_WEIGHTS.get(report.severity, 1)
    decay = time_decay_weight(report.age_in_days())
    return severity_weight * decay * report.verification_confidence


def compute_cluster_score(reports: list[CrimeReport]) -> float:
    """
    Compute the total weighted risk score for a set of reports
    belonging to one cluster.

    Args:
        reports: All CrimeReport rows currently assigned to the cluster.

    Returns:
        float: The cluster's raw risk score.
    """
    return sum(report_weight(r) for r in reports)


def score_to_risk_level(score: float) -> str:
    """
    Map a raw cluster score onto a Low / Medium / High risk level
    using configured thresholds.

    Args:
        score: The cluster's raw risk score.

    Returns:
        str: One of RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH.
    """
    if score >= Config.RISK_THRESHOLD_HIGH:
        return RiskLevel.HIGH
    if score >= Config.RISK_THRESHOLD_MEDIUM:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def crime_breakdown(reports: list[CrimeReport]) -> dict:
    """
    Build a count of crime types within a cluster, e.g.
    {"Armed Robbery": 4, "Theft": 9}.

    Args:
        reports: All CrimeReport rows belonging to the cluster.

    Returns:
        dict: Crime type -> count.
    """
    breakdown: dict = {}
    for r in reports:
        breakdown[r.crime_type] = breakdown.get(r.crime_type, 0) + 1
    return breakdown