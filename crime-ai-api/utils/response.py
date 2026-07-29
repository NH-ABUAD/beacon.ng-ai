"""
Utility functions for building consistent JSON API responses.
"""

from typing import Any, Tuple

from flask import jsonify


def success_response(data: Any, status_code: int = 200) -> Tuple[Any, int]:
    """
    Build a standardized success response.

    Args:
        data: The payload to return under the 'data' key.
        status_code: HTTP status code to return.

    Returns:
        Tuple of (Flask JSON response, status code).
    """
    return jsonify({"success": True, "data": data}), status_code


def error_response(message: str, status_code: int = 400) -> Tuple[Any, int]:
    """
    Build a standardized error response.

    Args:
        message: A human-readable error message.
        status_code: HTTP status code to return.

    Returns:
        Tuple of (Flask JSON response, status code).
    """
    return jsonify({"success": False, "error": message}), status_code