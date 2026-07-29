"""
Service layer responsible for communicating with the Groq API.

Handles two responsibilities:
1. Transcribing spoken crime reports into text using Groq's Whisper
   endpoint.
2. Detecting language, translating to English, and classifying crime
   reports using Groq's chat completion endpoint.
"""

import json

from groq import Groq, GroqError

from config import Config
from prompts.classifier_prompt import build_classification_prompt

ALLOWED_CRIME_TYPES = {
    "Armed Robbery", "Theft", "Burglary", "Kidnapping", "Assault",
    "Domestic Violence", "Murder", "Sexual Assault", "Fraud",
    "Cybercrime", "Drug Offense", "Terrorism", "Vandalism",
    "Traffic Incident", "Missing Person", "Public Disturbance",
    "Fire Incident", "Unknown",
}

ALLOWED_SEVERITIES = {"Critical", "High", "Medium", "Low"}
DEFAULT_SEVERITY = "Medium"

REQUIRED_KEYS = {
    "detected_language",
    "translated_report",
    "crime_type",
    "severity",
    "recommended_dispatch_unit",
}

# Audio formats supported by Groq's Whisper transcription endpoint.
ALLOWED_AUDIO_EXTENSIONS = {
    "flac", "mp3", "mp4", "mpeg", "mpga", "m4a", "ogg", "wav", "webm",
}

_client = None


def _get_client() -> Groq:
    """
    Lazily initialize and return a singleton Groq client instance.

    Returns:
        Groq: An authenticated Groq API client.
    """
    global _client
    if _client is None:
        Config.validate()
        _client = Groq(api_key=Config.GROQ_API_KEY)
    return _client


def transcribe_audio(file_stream, filename: str) -> str:
    """
    Transcribe a spoken crime report into text using Groq's Whisper
    transcription endpoint.

    Whisper handles multilingual speech natively, so the audio does
    not need to be in English — the raw transcription (in whatever
    language was spoken) is returned as-is and later handled by the
    existing language detection and translation step in the
    classification prompt.

    Args:
        file_stream: A file-like object containing the audio bytes.
        filename: The original filename, used to hint the audio format.

    Returns:
        str: The transcribed text.

    Raises:
        RuntimeError: If the Groq transcription request fails.
        ValueError: If the transcription result is empty.
    """
    client = _get_client()

    try:
        transcription = client.audio.transcriptions.create(
            file=(filename, file_stream.read()),
            model=Config.WHISPER_MODEL,
            response_format="text",
        )
    except GroqError as groq_error:
        raise RuntimeError(
            f"Groq transcription request failed: {str(groq_error)}"
        ) from groq_error
    except Exception as network_error:
        raise RuntimeError(
            f"Failed to reach Groq API for transcription: {str(network_error)}"
        ) from network_error

    transcribed_text = str(transcription).strip()

    if not transcribed_text:
        raise ValueError("Transcription returned empty text. Audio may be silent or unclear.")

    return transcribed_text


def classify_crime_report(description: str) -> dict:
    """
    Send a crime report description (in any supported language) to
    the Groq LLM, which detects the language, translates it to
    English, and classifies it in a single call.

    Args:
        description: The raw crime report text submitted by the client,
            in English, Yoruba, Hausa, Igbo, Nigerian Pidgin, or another
            language.

    Returns:
        dict: A dictionary with keys 'original_report', 'detected_language',
        'translated_report', 'crime_type', 'severity', and
        'recommended_dispatch_unit'.

    Raises:
        RuntimeError: If the Groq API call fails.
        ValueError: If the model response is not valid or well-formed JSON.
    """
    client = _get_client()
    system_prompt = build_classification_prompt()

    try:
        completion = client.chat.completions.create(
            model=Config.MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": description},
            ],
            temperature=0.2,
            max_tokens=500,
            response_format={"type": "json_object"},
        )
    except GroqError as groq_error:
        raise RuntimeError(f"Groq API request failed: {str(groq_error)}") from groq_error
    except Exception as network_error:
        raise RuntimeError(
            f"Failed to reach Groq API: {str(network_error)}"
        ) from network_error

    raw_content = completion.choices[0].message.content

    result = _parse_and_validate(raw_content)
    result["original_report"] = description

    return _order_response(result)


def classify_spoken_report(file_stream, filename: str) -> dict:
    """
    Full pipeline for a spoken crime report: transcribe the audio,
    then run the existing text classification pipeline on the
    transcription.

    Args:
        file_stream: A file-like object containing the audio bytes.
        filename: The original filename, used to hint the audio format.

    Returns:
        dict: The same structure as classify_crime_report(), plus a
        'transcribed_text' field showing the raw Whisper output.

    Raises:
        RuntimeError: If transcription or classification fails via Groq.
        ValueError: If transcription or classification output is invalid.
    """
    transcribed_text = transcribe_audio(file_stream, filename)
    result = classify_crime_report(transcribed_text)
    result["transcribed_text"] = transcribed_text
    return result


def _parse_and_validate(raw_content: str) -> dict:
    """
    Parse the raw LLM output as JSON and validate its structure.

    Invalid or unrecognized enum-like values (crime_type, severity)
    are coerced to safe defaults rather than raising, since the
    translation step adds an extra point of variability in model
    output. Missing structural fields (language, translation, or
    dispatch unit) still raise, since there is no safe default for
    those.

    Args:
        raw_content: The raw string content returned by the LLM.

    Returns:
        dict: A validated dictionary containing language detection,
        translation, and classification fields.

    Raises:
        ValueError: If the content is not valid JSON, is missing
        required keys, or is missing essential non-enum fields.
    """
    if not raw_content or not raw_content.strip():
        raise ValueError("Received empty response from the model.")

    try:
        data = json.loads(raw_content)
    except json.JSONDecodeError as parse_error:
        raise ValueError(
            f"Model returned invalid JSON: {str(parse_error)}"
        ) from parse_error

    if not isinstance(data, dict):
        raise ValueError("Model response must be a JSON object.")

    missing_keys = REQUIRED_KEYS - data.keys()
    if missing_keys:
        raise ValueError(f"Model response missing keys: {', '.join(missing_keys)}")

    detected_language = str(data.get("detected_language", "")).strip()
    translated_report = str(data.get("translated_report", "")).strip()
    crime_type = str(data.get("crime_type", "")).strip()
    severity = str(data.get("severity", "")).strip()
    dispatch_unit = str(data.get("recommended_dispatch_unit", "")).strip()

    if not detected_language:
        raise ValueError("Model did not return a detected language.")

    if not translated_report:
        raise ValueError("Model did not return a translated report.")

    if crime_type not in ALLOWED_CRIME_TYPES:
        crime_type = "Unknown"

    if severity not in ALLOWED_SEVERITIES:
        severity = DEFAULT_SEVERITY

    if not dispatch_unit:
        raise ValueError("Model did not return a recommended dispatch unit.")

    return {
        "detected_language": detected_language,
        "translated_report": translated_report,
        "crime_type": crime_type,
        "severity": severity,
        "recommended_dispatch_unit": dispatch_unit,
    }


def _order_response(result: dict) -> dict:
    """
    Return the classification result with keys in a consistent,
    predictable order matching the documented API response.

    Args:
        result: The unordered result dictionary.

    Returns:
        dict: The result dictionary with keys ordered for readability.
    """
    return {
        "original_report": result["original_report"],
        "detected_language": result["detected_language"],
        "translated_report": result["translated_report"],
        "crime_type": result["crime_type"],
        "severity": result["severity"],
        "recommended_dispatch_unit": result["recommended_dispatch_unit"],
    }


def is_allowed_audio_file(filename: str) -> bool:
    """
    Check whether a filename has a supported audio extension.

    Args:
        filename: The name of the uploaded file.

    Returns:
        bool: True if the extension is supported, False otherwise.
    """
    if "." not in filename:
        return False
    extension = filename.rsplit(".", 1)[1].lower()
    return extension in ALLOWED_AUDIO_EXTENSIONS