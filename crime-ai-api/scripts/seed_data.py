"""
Seed data generator: populates the database with realistic, but
synthetic, Nigerian crime reports so hotspots are visible before real
user reports accumulate.

Run via the Flask CLI command registered in app.py:
    flask seed-db
"""

import random
from datetime import datetime, timedelta, timezone

from config import Config
from data.nigeria_gazetteer import NIGERIA_GAZETTEER
from models import db
from models.report import CrimeReport, ReportSource, VerificationStatus
from prompts.classifier_prompt import CRIME_TYPES, SEVERITY_LEVELS, DISPATCH_UNITS

# Crime types weighted toward more common urban offenses for a more
# realistic distribution than a uniform random pick.
CRIME_TYPE_WEIGHTS = {
    "Theft": 5, "Burglary": 4, "Armed Robbery": 3, "Assault": 3,
    "Vandalism": 2, "Fraud": 2, "Cybercrime": 2, "Traffic Incident": 2,
    "Public Disturbance": 2, "Domestic Violence": 2, "Drug Offense": 1,
    "Kidnapping": 1, "Missing Person": 1, "Sexual Assault": 1,
    "Murder": 1, "Fire Incident": 1, "Terrorism": 1,
}

SAMPLE_DESCRIPTIONS = {
    "Theft": "Someone stole my phone near the market.",
    "Burglary": "My shop was broken into overnight and goods were taken.",
    "Armed Robbery": "Armed men robbed shoppers at gunpoint near the motor park.",
    "Assault": "A fight broke out and one person was injured.",
    "Vandalism": "Unknown persons damaged shop shutters along the road.",
    "Fraud": "I was scammed by someone posing as a bank agent.",
    "Cybercrime": "My bank account was hacked and money was withdrawn.",
    "Traffic Incident": "There was a serious accident at the junction.",
    "Public Disturbance": "A large crowd is causing disturbance near the market.",
    "Domestic Violence": "A neighbor is being assaulted by their partner.",
    "Drug Offense": "Suspicious drug activity was seen behind the market stalls.",
    "Kidnapping": "A child was reported missing after leaving school.",
    "Missing Person": "An elderly man has not returned home since yesterday.",
    "Sexual Assault": "A woman reported being assaulted while walking home at night.",
    "Murder": "A body was found near the riverbank this morning.",
    "Fire Incident": "A fire broke out in a row of shops at the market.",
    "Terrorism": "An explosion was heard near the central bus station.",
}


def _weighted_crime_type() -> str:
    """Pick a crime type using the configured weighting."""
    types = list(CRIME_TYPE_WEIGHTS.keys())
    weights = list(CRIME_TYPE_WEIGHTS.values())
    return random.choices(types, weights=weights, k=1)[0]


def _severity_for_crime_type(crime_type: str) -> str:
    """
    Assign a plausible severity for a given crime type — e.g. Murder
    is never 'Low', minor Vandalism is rarely 'Critical'.
    """
    severity_bias = {
        "Murder": ["Critical", "Critical", "High"],
        "Armed Robbery": ["Critical", "High", "High"],
        "Kidnapping": ["Critical", "High"],
        "Terrorism": ["Critical"],
        "Sexual Assault": ["Critical", "High"],
        "Vandalism": ["Low", "Medium"],
        "Fraud": ["Medium", "Low"],
        "Missing Person": ["Medium", "High"],
        "Traffic Incident": ["High", "Medium"],
    }
    options = severity_bias.get(crime_type, ["Medium", "High", "Low"])
    return random.choice(options)


def _dispatch_unit_for_crime_type(crime_type: str) -> str:
    """Assign a plausible dispatch unit for a given crime type."""
    mapping = {
        "Armed Robbery": "Armed Response Unit",
        "Kidnapping": "Anti-Kidnapping Squad",
        "Cybercrime": "Cybercrime Unit",
        "Fraud": "Cybercrime Unit",
        "Traffic Incident": "Traffic Police",
        "Fire Incident": "Fire Service",
        "Domestic Violence": "Domestic Violence Unit",
        "Drug Offense": "Drug Enforcement Unit",
        "Murder": "Criminal Investigation Department (CID)",
        "Sexual Assault": "Criminal Investigation Department (CID)",
    }
    return mapping.get(crime_type, random.choice(DISPATCH_UNITS))


def _random_jitter(lat: float, lng: float, spread_meters: float = 300) -> tuple[float, float]:
    """Apply a small random offset around a base coordinate."""
    meters_per_degree = 111_320.0
    d_lat = random.uniform(-spread_meters, spread_meters) / meters_per_degree
    d_lng = random.uniform(-spread_meters, spread_meters) / meters_per_degree
    return lat + d_lat, lng + d_lng


def _random_past_timestamp(max_age_days: int) -> datetime:
    """
    Generate a timestamp spread across the max age window, weighted
    toward more recent dates, so seed data decays out naturally as it
    ages — matching the transition design in the architecture doc.
    """
    age_days = random.triangular(0, max_age_days, max_age_days * 0.3)
    return datetime.now(timezone.utc) - timedelta(days=age_days)


def generate_seed_reports(reports_per_density_unit: int = 15) -> int:
    """
    Generate and insert seed CrimeReport rows across all gazetteer
    areas, biased by each area's density_weight so busier areas get
    proportionally more synthetic reports.

    Args:
        reports_per_density_unit: Base report count per unit of
            density_weight (e.g. weight 1.5 → ~1.5x this many reports).

    Returns:
        int: Total number of seed reports created.
    """
    total_created = 0

    for state, payload in NIGERIA_GAZETTEER.items():
        for area_name, (lat, lng, density_weight) in payload["areas"].items():
            count = max(3, int(reports_per_density_unit * density_weight))

            for _ in range(count):
                crime_type = _weighted_crime_type()
                severity = _severity_for_crime_type(crime_type)
                report_lat, report_lng = _random_jitter(lat, lng)

                report = CrimeReport(
                    original_report=SAMPLE_DESCRIPTIONS.get(crime_type, "Crime reported."),
                    translated_report=SAMPLE_DESCRIPTIONS.get(crime_type, "Crime reported."),
                    detected_language="English",
                    crime_type=crime_type,
                    severity=severity,
                    recommended_dispatch_unit=_dispatch_unit_for_crime_type(crime_type),
                    latitude=report_lat,
                    longitude=report_lng,
                    state=state,
                    lga=area_name,
                    location_text=f"{area_name}, {state}",
                    source=ReportSource.SEED,
                    verification_status=VerificationStatus.UNVERIFIED,
                    verification_confidence=Config.SEED_BASELINE_CONFIDENCE,
                    created_at=_random_past_timestamp(Config.MAX_REPORT_AGE_DAYS),
                    expires_at=datetime.now(timezone.utc)
                    + timedelta(days=Config.MAX_REPORT_AGE_DAYS),
                )
                db.session.add(report)
                total_created += 1

    db.session.commit()
    return total_created