"""
Entry point for the Crime Report Classification + Hotspot Detection
API. Extends the original classification-only app with database
initialization, the new report/hotspot blueprints, and a seed-data
CLI command — all additive, existing routes untouched.
"""

from flask import Flask
from flask_cors import CORS
from sqlalchemy import text

from config import Config
from models import db
from routes.classify import classify_bp
from routes.hotspots import hotspots_bp
from routes.reports import reports_bp
from flasgger import Swagger

swagger_template = {
        "swagger": "2.0",
        "info": {
            "title": "Crime AI API",
            "description": (
                "REST API for AI-powered crime classification, crime report "
                "submission, and hotspot detection."
            ),
            "version": "1.0.0",
            "contact": {
                "name": "Crime AI Team"
            },
        },
        "basePath": "/api",
        "schemes": ["http", "https"],
    }

swagger_config = {
    "headers": [],
    "specs": [
        {
            "endpoint": "apispec",
            "route": "/apispec.json",
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/docs/",
}

def create_app() -> Flask:
    """
    Application factory that creates and configures the Flask app.

    Returns:
        Flask: A fully configured Flask application instance.
    """
    app = Flask(__name__)

    app.config.from_object(Config)
    Swagger(app, template=swagger_template, )

    if Config.CORS_ORIGINS.strip() == "*":
        CORS(app)
    else:
        CORS(app, origins=[origin.strip() for origin in Config.CORS_ORIGINS.split(",") if origin.strip()])
    db.init_app(app)

    app.register_blueprint(classify_bp, url_prefix="/api")
    app.register_blueprint(reports_bp, url_prefix="/api")
    app.register_blueprint(hotspots_bp, url_prefix="/api")

    if Config.ENABLE_RATE_LIMITING:
        _init_rate_limiting(app)

    with app.app_context():
        db.create_all()

    _register_cli_commands(app)

    if Config.ENABLE_SCHEDULER:
        _start_scheduler(app)

    @app.route("/health", methods=["GET"])
    def health_check():
        """Health check for Render and upstream services."""
        try:
            db.session.execute(text("SELECT 1"))
            return {"success": True, "message": "Crime AI API is running"}, 200
        except Exception as exc:
            return {
                "success": False,
                "message": "Crime AI API is up but the database is unavailable",
                "error": str(exc),
            }, 503

    print("\nRegistered routes:")
    for rule in app.url_map.iter_rules():
        print(rule)
    for rule in app.url_map.iter_rules():
        print(rule.endpoint)
    print(app.url_map)
    return app


def _init_rate_limiting(app: Flask) -> None:
    """
    Attach rate limiting to the report submission endpoint, guarding
    against mass/bot submissions. Off by default via
    Config.ENABLE_RATE_LIMITING.
    """
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address

    limiter = Limiter(get_remote_address, app=app, default_limits=[])
    limiter.limit(Config.RATE_LIMIT_REPORT_SUBMISSION)(
        app.view_functions["reports.create_report"]
    )


def _register_cli_commands(app: Flask) -> None:
    """Register Flask CLI commands, e.g. `flask seed-db`."""

    @app.cli.command("seed-db")
    def seed_db():
        """Populate the database with realistic Nigerian seed crime reports."""
        from scripts.seed_data import generate_seed_reports
        from services.cluster_service import recompute_all_clusters

        count = generate_seed_reports()
        print(f"Created {count} seed reports.")

        recompute_all_clusters()
        print("Initial cluster computation complete.")


def _start_scheduler(app: Flask) -> None:
    """
    Start a background job that periodically recomputes clusters for
    every state, as a safety net alongside the recompute-on-write
    behavior in report_service.submit_report(). Off by default via
    Config.ENABLE_SCHEDULER.
    """
    from apscheduler.schedulers.background import BackgroundScheduler

    from services.cluster_service import recompute_all_clusters

    scheduler = BackgroundScheduler()

    def _job():
        with app.app_context():
            recompute_all_clusters()

    scheduler.add_job(_job, "interval", minutes=Config.RECLUSTER_INTERVAL_MINUTES)
    scheduler.start()


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=Config.DEBUG)