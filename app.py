"""
app.py - Flask Web Application for Concurrency-Safe Urban Parking Allocator.

Provides the web dashboard interface and RESTful API endpoints for:
- Parking slot status and live occupancy metrics
- Concurrency-safe slot booking
- Booking cancellation and slot release
- Dynamic surge pricing analytics
- Audit history of bookings
"""

import os
from flask import Flask, render_template, jsonify, request
from database import (
    init_db,
    get_all_slots,
    get_parking_stats,
    book_slot,
    cancel_booking,
    get_recent_history,
    get_db_path,
    TOTAL_CONFIGURED_SLOTS
)
from pricing import get_surge_pricing


def create_app(test_config=None) -> Flask:
    """Application factory for Flask app."""
    app = Flask(__name__, template_folder="templates", static_folder="static")

    # Configuration defaults
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "urban-parking-secret-key-2026"),
        DATABASE_PATH=os.environ.get("DATABASE_PATH", get_db_path()),
        JSON_AS_ASCII=False  # Support UTF-8 Rupee symbol ₹ cleanly in JSON
    )

    if test_config:
        app.config.update(test_config)

    # Initialize database tables and slots on app creation
    # Guarantees initialization runs even under Gunicorn production workers
    with app.app_context():
        init_db(app.config["DATABASE_PATH"])

    # --- HTML Routes ---

    @app.route("/")
    def index():
        """Serve the main interactive parking management dashboard."""
        return render_template("index.html")

    # --- REST API Endpoints ---

    @app.route("/api/health", methods=["GET"])
    def health_check():
        """Health check endpoint for deployment platforms (Render, Railway, etc.)."""
        return jsonify({
            "status": "healthy",
            "service": "Concurrency-Safe Urban Parking Allocator",
            "version": "1.0.0"
        }), 200

    @app.route("/api/status", methods=["GET"])
    def api_status():
        """Retrieve high-level parking facility metrics and surge pricing."""
        try:
            stats = get_parking_stats(app.config["DATABASE_PATH"])
            return jsonify({
                "success": True,
                "data": stats
            }), 200
        except Exception as err:
            return jsonify({
                "success": False,
                "error": "STATS_FETCH_FAILED",
                "message": "Failed to calculate parking metrics."
            }), 500

    @app.route("/api/slots", methods=["GET"])
    def api_slots():
        """Retrieve list of all parking slots with live availability and active booking."""
        try:
            slots = get_all_slots(app.config["DATABASE_PATH"])
            return jsonify({
                "success": True,
                "total": len(slots),
                "data": slots
            }), 200
        except Exception as err:
            return jsonify({
                "success": False,
                "error": "SLOTS_FETCH_FAILED",
                "message": "Failed to retrieve parking slots."
            }), 500

    @app.route("/api/pricing", methods=["GET"])
    def api_pricing():
        """Retrieve real-time surge pricing analytics and occupancy tier rules."""
        try:
            stats = get_parking_stats(app.config["DATABASE_PATH"])
            pricing_data = stats["pricing"]
            return jsonify({
                "success": True,
                "data": pricing_data
            }), 200
        except Exception as err:
            return jsonify({
                "success": False,
                "error": "PRICING_FETCH_FAILED",
                "message": "Failed to retrieve surge pricing data."
            }), 500

    @app.route("/api/book", methods=["POST"])
    def api_book():
        """
        Concurrency-Safe slot booking endpoint.
        Expects JSON payload:
        {
            "slot_id": "P01",
            "user_name": "Rohan Sharma",
            "vehicle_number": "KA-01-AB-1234"
        }
        """
        payload = request.get_json(silent=True)
        if not payload or not isinstance(payload, dict):
            return jsonify({
                "success": False,
                "error": "INVALID_JSON",
                "message": "Request body must be a valid JSON object."
            }), 400

        slot_id = payload.get("slot_id")
        user_name = payload.get("user_name")
        vehicle_number = payload.get("vehicle_number")

        success, result, status_code = book_slot(
            slot_id=slot_id,
            user_name=user_name,
            vehicle_number=vehicle_number,
            db_path=app.config["DATABASE_PATH"]
        )

        return jsonify({
            "success": success,
            **result
        }), status_code

    @app.route("/api/cancel", methods=["POST"])
    def api_cancel():
        """
        Cancel an active parking booking and free the slot.
        Expects JSON payload:
        {
            "booking_id": "BKG-20261025-ABCD1234"
        }
        """
        payload = request.get_json(silent=True)
        if not payload or not isinstance(payload, dict):
            return jsonify({
                "success": False,
                "error": "INVALID_JSON",
                "message": "Request body must be a valid JSON object."
            }), 400

        booking_id = payload.get("booking_id")
        success, result, status_code = cancel_booking(
            booking_id=booking_id,
            db_path=app.config["DATABASE_PATH"]
        )

        return jsonify({
            "success": success,
            **result
        }), status_code

    @app.route("/api/history", methods=["GET"])
    def api_history():
        """Retrieve recent parking transactions and cancellations."""
        try:
            limit = request.args.get("limit", default=20, type=int)
            limit = max(1, min(limit, 100))  # Bound between 1 and 100
            history = get_recent_history(limit=limit, db_path=app.config["DATABASE_PATH"])
            return jsonify({
                "success": True,
                "count": len(history),
                "data": history
            }), 200
        except Exception as err:
            return jsonify({
                "success": False,
                "error": "HISTORY_FETCH_FAILED",
                "message": "Failed to retrieve booking history."
            }), 500

    return app


# Global WSGI application handle for Gunicorn and Render
app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    print(f"Starting Urban Parking Allocator server on http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
