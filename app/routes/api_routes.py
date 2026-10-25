from datetime import datetime
from flask import Blueprint, jsonify, request
from app.models import db, ParkingZone, ParkingSlot, Booking
from app.services.pricing_service import (
    get_system_wide_stats,
    get_all_zones_pricing_summary,
    get_zone_pricing_data,
    PRICING_TIERS
)
from app.services.allocation_service import (
    allocate_slot,
    auto_allocate_slot,
    cancel_booking_by_reference
)

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint for deployment monitoring (Render, Railway, etc.)."""
    dialect = db.session.bind.dialect.name if db.session.bind else "unknown"
    return jsonify({
        "status": "healthy",
        "service": "Concurrency-Safe Urban Parking Allocator With Surge Analytics",
        "version": "2.0.0",
        "database_engine": dialect,
        "timestamp": datetime.utcnow().isoformat()
    }), 200


@api_bp.route("/status", methods=["GET"])
def get_status():
    """Retrieve system-wide parking facility occupancy and operational statistics."""
    try:
        stats = get_system_wide_stats()
        return jsonify({"success": True, "data": stats}), 200
    except Exception as err:
        return jsonify({"success": False, "error": "FETCH_FAILED", "message": str(err)}), 500


@api_bp.route("/zones", methods=["GET"])
def get_zones():
    """Retrieve all active parking zones with live surge rates and availability."""
    try:
        summaries = get_all_zones_pricing_summary()
        return jsonify({"success": True, "count": len(summaries), "data": summaries}), 200
    except Exception as err:
        return jsonify({"success": False, "error": "FETCH_FAILED", "message": str(err)}), 500


@api_bp.route("/zones/<int:zone_id>/slots", methods=["GET"])
def get_zone_slots(zone_id):
    """Retrieve all parking slots within a specific zone."""
    zone = db.session.get(ParkingZone, zone_id)
    if not zone:
        return jsonify({"success": False, "error": "NOT_FOUND", "message": "Zone not found"}), 404

    slots = zone.slots.order_by(ParkingSlot.slot_number.asc()).all()
    pricing = get_zone_pricing_data(zone)

    return jsonify({
        "success": True,
        "zone": zone.to_dict(),
        "pricing": pricing,
        "slots": [s.to_dict() for s in slots]
    }), 200


@api_bp.route("/pricing", methods=["GET"])
def get_pricing():
    """Retrieve live surge pricing rules, thresholds, and current zone tariffs."""
    try:
        summaries = get_all_zones_pricing_summary()
        return jsonify({
            "success": True,
            "tiers": PRICING_TIERS,
            "zones": summaries
        }), 200
    except Exception as err:
        return jsonify({"success": False, "error": "FETCH_FAILED", "message": str(err)}), 500


@api_bp.route("/book", methods=["POST"])
def book_parking_slot():
    """
    Concurrency-Safe slot booking endpoint.
    JSON payload:
    {
        "slot_id": 1,
        "driver_name": "Rohan Sharma",
        "vehicle_number": "KA-01-AB-1234",
        "contact_number": "+91-9876543210" (optional)
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
    driver_name = payload.get("driver_name")
    vehicle_number = payload.get("vehicle_number")
    contact_number = payload.get("contact_number")

    if slot_id is None:
        return jsonify({
            "success": False,
            "error": "MISSING_SLOT_ID",
            "message": "Parking slot ID is required."
        }), 400

    try:
        slot_id = int(slot_id)
    except (ValueError, TypeError):
        return jsonify({
            "success": False,
            "error": "INVALID_SLOT_ID",
            "message": "Slot ID must be an integer."
        }), 400

    success, result, status_code = allocate_slot(
        slot_id=slot_id,
        driver_name=driver_name,
        vehicle_number=vehicle_number,
        contact_number=contact_number
    )

    return jsonify({"success": success, **result}), status_code


@api_bp.route("/auto-allocate", methods=["POST"])
def auto_allocate():
    """
    Automatic slot allocation endpoint.
    JSON payload:
    {
        "zone_id": 1,
        "driver_name": "Priya Patel",
        "vehicle_number": "DL-08-XY-9876",
        "slot_type": "Standard" (optional),
        "contact_number": "+91-9988776655" (optional)
    }
    """
    payload = request.get_json(silent=True)
    if not payload or not isinstance(payload, dict):
        return jsonify({
            "success": False,
            "error": "INVALID_JSON",
            "message": "Request body must be a valid JSON object."
        }), 400

    zone_id = payload.get("zone_id")
    driver_name = payload.get("driver_name")
    vehicle_number = payload.get("vehicle_number")
    slot_type = payload.get("slot_type", "Standard")
    contact_number = payload.get("contact_number")

    if zone_id is None:
        return jsonify({
            "success": False,
            "error": "MISSING_ZONE_ID",
            "message": "Zone ID is required for automatic allocation."
        }), 400

    try:
        zone_id = int(zone_id)
    except (ValueError, TypeError):
        return jsonify({
            "success": False,
            "error": "INVALID_ZONE_ID",
            "message": "Zone ID must be an integer."
        }), 400

    success, result, status_code = auto_allocate_slot(
        zone_id=zone_id,
        driver_name=driver_name,
        vehicle_number=vehicle_number,
        slot_type=slot_type,
        contact_number=contact_number
    )

    return jsonify({"success": success, **result}), status_code


@api_bp.route("/cancel", methods=["POST"])
def cancel_booking():
    """
    Cancel an active booking by reference and free the parking slot.
    JSON payload:
    {
        "booking_reference": "BKG-20261025-ABCD1234"
    }
    """
    payload = request.get_json(silent=True)
    if not payload or not isinstance(payload, dict):
        return jsonify({
            "success": False,
            "error": "INVALID_JSON",
            "message": "Request body must be a valid JSON object."
        }), 400

    bkg_ref = payload.get("booking_reference")
    success, result, status_code = cancel_booking_by_reference(bkg_ref)

    return jsonify({"success": success, **result}), status_code


@api_bp.route("/analytics/data", methods=["GET"])
def get_analytics_data():
    """
    Structured data payload formatted specifically for Chart.js rendering.
    """
    try:
        zone_summaries = get_all_zones_pricing_summary()

        zone_names = [z["zone_name"] for z in zone_summaries]
        zone_codes = [z["zone_code"] for z in zone_summaries]
        total_capacities = [z["total_slots"] for z in zone_summaries]
        occupied_counts = [z["occupied_slots"] for z in zone_summaries]
        available_counts = [z["available_slots"] for z in zone_summaries]
        multipliers = [z["multiplier"] for z in zone_summaries]
        hourly_rates = [z["effective_rate"] for z in zone_summaries]
        occupancy_pcts = [z["occupancy_percentage"] for z in zone_summaries]

        # Hourly simulated utilization trend (08:00 to 20:00)
        hours = ["08:00", "10:00", "12:00", "14:00", "16:00", "18:00", "20:00"]
        # Realistic urban curve: rising at lunch and evening rush
        utilization_trend = [35, 62, 85, 78, 88, 92, 58]

        return jsonify({
            "success": True,
            "data": {
                "zones": {
                    "names": zone_names,
                    "codes": zone_codes,
                    "capacities": total_capacities,
                    "occupied": occupied_counts,
                    "available": available_counts,
                    "multipliers": multipliers,
                    "hourly_rates": hourly_rates,
                    "occupancy_percentages": occupancy_pcts
                },
                "trends": {
                    "hours": hours,
                    "utilization": utilization_trend
                },
                "timestamp": datetime.utcnow().isoformat()
            }
        }), 200
    except Exception as err:
        return jsonify({"success": False, "error": "ANALYTICS_FAILED", "message": str(err)}), 500


@api_bp.route("/history", methods=["GET"])
def get_history():
    """Retrieve recent booking transactions audit trail."""
    try:
        limit = request.args.get("limit", default=25, type=int)
        limit = max(1, min(limit, 100))
        bookings = Booking.query.order_by(Booking.booked_at.desc()).limit(limit).all()
        return jsonify({
            "success": True,
            "count": len(bookings),
            "data": [b.to_dict() for b in bookings]
        }), 200
    except Exception as err:
        return jsonify({"success": False, "error": "HISTORY_FAILED", "message": str(err)}), 500
