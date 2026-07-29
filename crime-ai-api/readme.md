# Crime Report Classification API

A Flask REST API that uses the Groq API (LLM inference) to automatically
classify incoming crime reports by **crime type**, **severity level**,
and **recommended dispatch unit** — helping police administrators triage
reports quickly.

This is a backend-only service. No frontend, no authentication, no
database, and no model training are included by design.

## Tech Stack

- Python 3.12+
- Flask
- Flask-CORS
- Groq Python SDK
- python-dotenv

## Project Structure