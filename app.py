"""
app.py — Flask application entry point for Sloth Summarizer.

Routes:
  GET  /          → Serve the single-page frontend
  POST /summarize → Accept text or PDF, return summarization result
  GET  /health    → Uptime check for Render.com and monitoring tools
"""

import logging
import os
import time
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_from_directory
from flask_cors import CORS

from summarizer import extract_text_from_pdf, summarize

# ─── App setup ────────────────────────────────────────────────────────────────

load_dotenv()  # Reads .env in development; harmless in production

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static",
)

CORS(app)

# Max upload: 10 MB
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_hf_api_key() -> str:
    """Retrieve the HuggingFace API key from environment. Raises on missing."""
    key = os.environ.get("HF_API_KEY", "").strip()
    if not key:
        raise EnvironmentError(
            "HF_API_KEY is not set. Add it to your .env file or Render environment variables."
        )
    return key


def _validate_summarize_inputs(format_type: str, length: str) -> None:
    """Raise ValueError with a friendly message if inputs are out of range."""
    valid_formats = {"paragraph", "bullets", "numbered", "tldr"}
    valid_lengths = {"short", "medium", "long"}

    if format_type not in valid_formats:
        raise ValueError(f"🦥 Unknown format '{format_type}'. Choose: {', '.join(sorted(valid_formats))}")
    if length not in valid_lengths:
        raise ValueError(f"🦥 Unknown length '{length}'. Choose: {', '.join(sorted(valid_lengths))}")


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    """Serve the single-page frontend application."""
    return send_from_directory("templates", "index.html")


@app.route("/health", methods=["GET"])
def health():
    """
    Simple health-check endpoint.
    Used by Render, UptimeRobot, or any uptime monitoring service.
    """
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat() + "Z"})


@app.route("/summarize", methods=["POST"])
def summarize_endpoint():
    """
    Main summarization endpoint.

    Accepts two content types:
      1. application/json   → {"text": "...", "format": "paragraph", "length": "medium"}
      2. multipart/form-data → file field "pdf", plus form fields "format" and "length"

    Returns JSON:
      {
        "summary":               str,
        "word_count":            int,
        "char_count":            int,
        "original_word_count":   int,
        "time_taken":            float   # seconds
      }
    """
    request_start = time.time()

    try:
        hf_api_key = _get_hf_api_key()
    except EnvironmentError as exc:
        logger.error("HF_API_KEY missing: %s", exc)
        return jsonify({"error": str(exc)}), 500

    # ── Branch: JSON text input ────────────────────────────────────────────────
    if request.is_json:
        body = request.get_json(silent=True) or {}
        text = (body.get("text") or "").strip()
        format_type = (body.get("format") or "paragraph").strip().lower()
        length = (body.get("length") or "medium").strip().lower()

        if not text:
            return jsonify({"error": "🦥 No text provided. Paste something for the sloth to chew on!"}), 400

        if len(text) < 100:
            return jsonify({
                "error": "🦥 Text is too short! Give the sloth at least 100 characters to work with."
            }), 400

    # ── Branch: Multipart form (PDF upload) ───────────────────────────────────
    elif "pdf" in request.files:
        pdf_file = request.files["pdf"]
        format_type = (request.form.get("format") or "paragraph").strip().lower()
        length = (request.form.get("length") or "medium").strip().lower()

        if pdf_file.filename == "":
            return jsonify({"error": "🦥 No file selected. Drop a PDF on the sloth!"}), 400

        if not pdf_file.filename.lower().endswith(".pdf"):
            return jsonify({"error": "🦥 Only PDF files are supported right now!"}), 400

        file_bytes = pdf_file.read()
        if not file_bytes:
            return jsonify({"error": "🦥 That file is empty. Try another PDF?"}), 400

        try:
            text = extract_text_from_pdf(file_bytes)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        if len(text.strip()) < 100:
            return jsonify({
                "error": (
                    "🦥 Extracted text is too short. "
                    "The PDF might be image-based or mostly blank."
                )
            }), 400

    else:
        return jsonify({
            "error": "🦥 Please send either JSON text or a PDF file. The sloth is confused!"
        }), 400

    # ── Validate format + length params ───────────────────────────────────────
    try:
        _validate_summarize_inputs(format_type, length)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    # ── Log the request ────────────────────────────────────────────────────────
    logger.info(
        "Summarize request | format=%s | length=%s | input_chars=%d",
        format_type,
        length,
        len(text),
    )

    # ── Run summarization ──────────────────────────────────────────────────────
    try:
        result = summarize(text, format_type, length, hf_api_key)
        logger.info(
            "Summarize success | time_taken=%.2fs | output_words=%d",
            result["time_taken"],
            result["word_count"],
        )
        return jsonify(result), 200

    except ValueError as exc:
        logger.warning("Summarize error (user-facing): %s", exc)
        return jsonify({"error": str(exc)}), 400

    except Exception as exc:
        logger.exception("Unexpected error during summarization: %s", exc)
        return jsonify({
            "error": (
                "🦥 Something went wrong on our end. "
                "The sloth is investigating. Please try again!"
            )
        }), 500


# ─── Error handlers ───────────────────────────────────────────────────────────

@app.errorhandler(413)
def file_too_large(exc):
    """Friendly error when the uploaded file exceeds MAX_CONTENT_LENGTH."""
    return jsonify({
        "error": "🦥 That file is too big! Maximum allowed size is 10 MB. Try a smaller PDF."
    }), 413


@app.errorhandler(404)
def not_found(exc):
    return jsonify({"error": "🦥 Page not found."}), 404


@app.errorhandler(405)
def method_not_allowed(exc):
    return jsonify({"error": "🦥 Method not allowed."}), 405


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
