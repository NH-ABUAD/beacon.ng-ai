"""
Route handlers for crime report submission and retrieval — the new
write path that feeds the hotspot system. Distinct from
routes/classify.py, which remains a stateless classification-only
endpoint used exactly as before.
"""

from flask import Blueprint, request

from models import db
from models.report import CrimeReport
from services.report_service import ReportSubmissionError, submit_report
from utils.response import error_response, success_response

reports_bp = Blueprint("reports", __name__)


@reports_bp.route("/reports", methods=["POST"])
def create_report():
    """
    Submit a new crime report, running it through the existing
    translation/classification pipeline plus verification, geocoding,
    persistence, and cluster recomputation.

    Expects a JSON body:
        {
            "description": "<crime report text>",
            "latitude": <float>,        # optional if location_text given
            "longitude": <float>,       # optional if location_text given
            "location_text": "<str>",   # optional if lat/lng given
            "state_hint": "<str>",      # optional, aids geocoding
            "source": "user_app"        # optional, defaults to user_app
        }

    Returns:
        JSON response with the persisted report, or an error with an
        appropriate HTTP status code.
    """
    payload = request.get_json(silent=True)

    if payload is None:
        return error_response("Request body must be valid JSON.", 400)

    description = payload.get("description")
    if not isinstance(description, str) or not description.strip():
        return error_response("Field 'description' cannot be empty.", 400)

    try:
        result = submit_report(
            description=description.strip(),
            latitude=payload.get("latitude"),
            longitude=payload.get("longitude"),
            location_text=payload.get("location_text"),
            state_hint=payload.get("state_hint"),
            source=payload.get("source", "user_app"),
        )
        return success_response(result, 201)

    except ReportSubmissionError as submission_error:
        return error_response(str(submission_error), 400)

    except ValueError as validation_error:
        return error_response(str(validation_error), 422)

    except RuntimeError as service_error:
        return error_response(str(service_error), 502)

    except Exception as unexpected_error:
        return error_response(
            f"An unexpected error occurred: {str(unexpected_error)}", 500
        )


@reports_bp.route("/reports/<report_id>", methods=["GET"])
def get_report(report_id: str):
    """
    Fetch a single crime report by its ID.

    Returns:
        JSON response with the report, or a 404 if not found.
    """
    report = db.session.get(CrimeReport, report_id)
    if report is None:
        return error_response("Report not found.", 404)

    return success_response(report.to_dict(), 200)