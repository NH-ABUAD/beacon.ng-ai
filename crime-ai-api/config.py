"""
Application configuration loaded from environment variables.

Extended for the Crime Hotspot Detection System: adds database,
clustering, risk scoring, and decay configuration on top of the
existing Groq settings. No existing keys were removed or renamed.
"""

import json
import os

from dotenv import load_dotenv

load_dotenv()


def _normalize_database_url(url: str) -> str:
    """Render and other hosts often provide postgres:// URLs; SQLAlchemy needs postgresql://."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


class Config:
    """Central configuration object for the Flask application."""

    # --- Existing Groq / classification config (unchanged) ---
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    MODEL: str = os.getenv("MODEL", "llama-3.3-70b-versatile")
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "whisper-large-v3")
    MAX_AUDIO_SIZE_MB: int = int(os.getenv("MAX_AUDIO_SIZE_MB", "25"))
    DEBUG: bool = os.getenv("FLASK_DEBUG", "False").lower() == "true"

    # --- Database ---
    SQLALCHEMY_DATABASE_URI: str = _normalize_database_url(
        os.getenv("DATABASE_URL", "sqlite:///crime_hotspots.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False

    # --- CORS (comma-separated origins, or "*" for all) ---
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "*")

    # --- Clustering (DBSCAN) ---
    # eps is a neighborhood radius in meters. Distinct per state because
    # urban density (Lagos) and rural density (e.g. rural Kaduna) differ
    # enormously — a single global eps would either merge all of Lagos
    # into one cluster or fail to ever cluster sparser states.
    CLUSTER_EPS_METERS_DEFAULT: float = float(os.getenv("CLUSTER_EPS_METERS_DEFAULT", "1200"))
    CLUSTER_EPS_METERS_BY_STATE: dict = json.loads(
        os.getenv(
            "CLUSTER_EPS_METERS_BY_STATE",
            '{"Lagos": 500, "Abuja": 700, "Port Harcourt": 600, "Kano": 800}',
        )
    )
    CLUSTER_MIN_SAMPLES: int = int(os.getenv("CLUSTER_MIN_SAMPLES", "3"))

    # --- Time decay ---
    DECAY_HALF_LIFE_DAYS: float = float(os.getenv("DECAY_HALF_LIFE_DAYS", "7"))
    MAX_REPORT_AGE_DAYS: int = int(os.getenv("MAX_REPORT_AGE_DAYS", "60"))

    # --- Risk scoring ---
    SEVERITY_WEIGHTS: dict = json.loads(
        os.getenv(
            "SEVERITY_WEIGHTS",
            '{"Critical": 10, "High": 6, "Medium": 3, "Low": 1}',
        )
    )
    RISK_THRESHOLD_HIGH: float = float(os.getenv("RISK_THRESHOLD_HIGH", "25"))
    RISK_THRESHOLD_MEDIUM: float = float(os.getenv("RISK_THRESHOLD_MEDIUM", "10"))

    # --- Seed data / real-data transition ---
    SEED_BASELINE_CONFIDENCE: float = float(os.getenv("SEED_BASELINE_CONFIDENCE", "0.6"))
    UNVERIFIED_BASELINE_CONFIDENCE: float = float(
        os.getenv("UNVERIFIED_BASELINE_CONFIDENCE", "0.5")
    )
    VERIFIED_CONFIDENCE: float = float(os.getenv("VERIFIED_CONFIDENCE", "0.9"))

    # --- Background jobs / rate limiting (off by default) ---
    ENABLE_SCHEDULER: bool = os.getenv("ENABLE_SCHEDULER", "False").lower() == "true"
    RECLUSTER_INTERVAL_MINUTES: int = int(os.getenv("RECLUSTER_INTERVAL_MINUTES", "15"))
    ENABLE_RATE_LIMITING: bool = os.getenv("ENABLE_RATE_LIMITING", "False").lower() == "true"
    RATE_LIMIT_REPORT_SUBMISSION: str = os.getenv("RATE_LIMIT_REPORT_SUBMISSION", "10/hour")

    @staticmethod
    def validate():
        """
        Validate that required environment variables are present.

        Raises:
            ValueError: If GROQ_API_KEY is not set.
        """
        if not Config.GROQ_API_KEY:
            raise ValueError(
                "GROQ_API_KEY is not set. Please add it to your .env file."
            )