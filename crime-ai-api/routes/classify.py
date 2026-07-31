# routes/classify.py
"""
Route handlers for the crime classification endpoints.

Responsible for request validation, delegating to the service
layer (text classification and audio transcription + classification),
and formatting HTTP responses.
"""

from flask import Blueprint, request
from pathlib import Path
from config import Config
from services.groq_service import (
    classify_crime_report,
    classify_spoken_report,
    is_allowed_audio_file,
)
from utils.response import error_response, success_response
from flasgger import swag_from

classify_bp = Blueprint("classify", __name__)
DOCS = Path(__file__).resolve().parent.parent / "docs"

@classify_bp.route("/classify", methods=["POST"])
@swag_from(str(DOCS / 'classify.yml'))
def classify_report():
    """
    Classify a crime report using the Groq LLM.

    Expects a JSON body:
        { "description": "<crime report text>" }

    Returns:
        JSON response containing crime_type, severity, and
        recommended_dispatch_unit, or an error message with an
        appropriate HTTP status code.
    """
    payload = request.get_json(silent=True)

    if payload is None:
        return error_response("Request body must be valid JSON.", 400)

    description = payload.get("description")

    if description is None:
        return error_response("Field 'description' is required.", 400)

    if not isinstance(description, str) or not description.strip():
        return error_response("Field 'description' cannot be empty.", 400)

    try:
        classification = classify_crime_report(description.strip())
        return success_response(classification, 200)

    except ValueError as validation_error:
        return error_response(str(validation_error), 422)

    except RuntimeError as service_error:
        return error_response(str(service_error), 502)

    except Exception as unexpected_error:
        return error_response(
            f"An unexpected error occurred: {str(unexpected_error)}", 500
        )


@classify_bp.route("/classify-audio", methods=["POST"])
@swag_from('../docs/classify_audio.yml',)
def classify_spoken_report_route():
    """
    Classify a spoken crime report submitted as an audio file.

    Expects a multipart/form-data request with a single file field
    named 'audio'. The audio is transcribed via Groq's Whisper
    endpoint, then run through the existing text classification
    pipeline (language detection, translation, classification).

    Supported audio formats: flac, mp3, mp4, mpeg, mpga, m4a, ogg,
    wav, webm.

    Returns:
        JSON response containing the transcribed text, original and
        translated report, crime_type, severity, and
        recommended_dispatch_unit, or an error message with an
        appropriate HTTP status code.
    """
    if "audio" not in request.files:
        return error_response(
            "No audio file provided. Attach it under the 'audio' field.", 400
        )

    audio_file = request.files["audio"]

    if audio_file.filename == "":
        return error_response("No audio file selected.", 400)

    if not is_allowed_audio_file(audio_file.filename):
        return error_response(
            "Unsupported audio format. Allowed formats: flac, mp3, mp4, "
            "mpeg, mpga, m4a, ogg, wav, webm.",
            400,
        )

    audio_file.seek(0, 2)
    file_size_mb = audio_file.tell() / (1024 * 1024)
    audio_file.seek(0)

    if file_size_mb > Config.MAX_AUDIO_SIZE_MB:
        return error_response(
            f"Audio file too large. Maximum allowed size is "
            f"{Config.MAX_AUDIO_SIZE_MB}MB.",
            400,
        )

    try:
        classification = classify_spoken_report(audio_file, audio_file.filename)
        return success_response(classification, 200)

    except ValueError as validation_error:
        return error_response(str(validation_error), 422)

    except RuntimeError as service_error:
        return error_response(str(service_error), 502)

    except Exception as unexpected_error:
        return error_response(
            f"An unexpected error occurred: {str(unexpected_error)}", 500
        )